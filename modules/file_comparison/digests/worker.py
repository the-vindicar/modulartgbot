"""
Класс, управляющий плагинами для извлечения и сравнения выжимок из файлов.
Этот код будет выполняться в рамках рабочего потока или процесса, что накладывает ряд ограничений.
"""
import typing as t
import dataclasses
import gzip
import importlib
import logging
import logging.handlers
import multiprocessing
import threading
import os
from pathlib import Path

# noinspection PyProtectedMember
from .plugins._base import DigestExtractorABC, DigestComparerABC
from ..models import FileToCompute, DigestPair


__all__ = ['ComputeDigestResponse', 'ComputeSimilarityResponse', 'Worker']


@dataclasses.dataclass
class ComputeDigestResponse:
    """Отклик при извлечении дайджестов из файла."""
    file: FileToCompute
    gzipped_digests: dict[str, t.Optional[bytes]]
    warnings: dict[str, str]
    errors: list[t.Union[Exception, str]]


@dataclasses.dataclass
class ComputeSimilarityResponse:
    """Отклик при расчёте сходства дайджестов."""
    older_id: int
    newer_id: int
    digest_type: str
    similarity: t.Optional[float]
    error: t.Optional[Exception]


class Worker:
    """
    Этот класс обеспечивает подготовку и использование плагинов в дочерних процессах.
    Следует иметь ввиду, что его методы уже выполняются в дочерних процессах, поэтому его инициализация
    отложена - она выполняется не в конструкторе.

    Также этот класс отвечает за сжатие и распаковку выжимок из файлов перед использованием. Вне класса должны
    быть видны только сжатые выжимки, а плагинам для работы с типами дайджестов - только распакованные.
    """
    @staticmethod
    def get_classes() -> tuple[list[t.Type[DigestExtractorABC]], list[t.Type[DigestComparerABC]]]:
        """Загружает дайджест-плагины и находит все актуальные классы плагинов."""
        extractors: list[t.Type[DigestExtractorABC]] = []
        comparers: list[t.Type[DigestComparerABC]] = []
        package_name = __name__.rpartition('.')[0]
        for item in (Path(__file__).parent / 'plugins').glob('*'):
            if not (
                    (
                            item.is_file() and item.suffix.lower() == '.py' and
                            (not item.name.startswith('_') and not item.name.startswith('.'))
                    ) or
                    (
                            item.is_dir() and (item / '__init__.py').is_file()
                    )
            ):
                continue
            importkey = f'{package_name}.plugins.{item.stem}'
            module = importlib.import_module(importkey)
            for attrname in dir(module):
                if attrname.startswith('_'):
                    continue
                attr = getattr(module, attrname)
                if isinstance(attr, type):
                    if issubclass(attr, DigestExtractorABC) and attr is not DigestExtractorABC:
                        extractors.append(attr)
                    if issubclass(attr, DigestComparerABC) and attr is not DigestComparerABC:
                        comparers.append(attr)
        return extractors, comparers

    def __init__(self, settings: dict[str, dict[str, t.Any]]):
        self._extractors: list[DigestExtractorABC] = []
        self._comparers: list[DigestComparerABC] = []
        self._settings = settings.copy()
        self._log: t.Optional[logging.Logger] = None
        self._initialized = False
        print(f'Worker @{os.getpid()}/{threading.get_native_id()} __init__()')

    def initializer(self, log_name: str, log_queue: multiprocessing.Queue) -> None:
        """Импортирует и инициализирует плагины в дочерних процессах."""
        self._log = logging.getLogger(log_name)
        self._log.handlers.clear()
        formatter = logging.Formatter(
            '@%(process)d: %(message)s'
        )
        handler = logging.handlers.QueueHandler(log_queue)
        handler.setFormatter(formatter)
        handler.setLevel(logging.DEBUG)
        self._log.addHandler(handler)
        self._log.setLevel(logging.DEBUG)

        extractors, comparers = self.get_classes()
        for cls in extractors:
            try:
                instance = cls()
                instance.initialize(self._settings.get(instance.name(), {}))
            except Exception as err:
                self._log.critical('Failed to initialize extractor %s', cls.__name__, exc_info=err)
            else:
                self._log.debug('Extractor %s (%s) ready.', cls.__name__, instance.name())
                self._extractors.append(instance)
        for cls in comparers:
            try:
                instance = cls()
            except Exception as err:
                self._log.critical('Failed to initialize comparer %s', cls.__name__, exc_info=err)
            else:
                self._log.debug('Comparer %s ready.', cls.__name__)
                self._comparers.append(instance)
        self._initialized = True
        self._log.debug(f'Worker @{os.getpid()}/{threading.get_native_id()}/{id(self)} completed initialization\n{repr(self.__dict__)}')

    def extract_digests(self, file: FileToCompute, content: bytes) -> ComputeDigestResponse:
        """Обрабатывает один файл и извлекает из него все возможные дайджесты.

        :param file: Описание обрабатываемого файла.
        :param content: Содержимое обрабатываемого файла.
        :return: Результат обработки файла."""
        if not self._initialized:
            raise RuntimeError('Initializer has not been run for worker '
                               f'{os.getpid()}/{threading.get_native_id()}/{id(self)}\n{repr(self.__dict__)}')
        digests: dict[str, t.Optional[bytes]] = {n: None for n in file.digest_types}
        warns = {}
        errors = []
        for plugin in self._extractors:
            try:
                if not file.digest_types.isdisjoint(plugin.digest_types()):
                    if plugin.can_process_file(file.file_name, file.mimetype, file.file_size):
                        try:
                            pdigests, pwarns = plugin.process_file(file.file_name, file.mimetype, content)
                        except Exception as err:
                            self._log.error('Extractor %s failed to process file %s ( %s ).',
                                            plugin.name(), file.file_name, file.file_url, exc_info=err)
                            errors.append(err)
                        else:
                            for digest_type, digest_data in pdigests.items():
                                if digest_data is not None:
                                    digest_data = gzip.compress(digest_data, compresslevel=9)
                                else:
                                    self._log.warning('Extractor %s failed to return digest %s for file %s ( %s ).',
                                                      plugin.name(), digest_type, file.file_name, file.file_url)
                                digests[digest_type] = digest_data
                            warns.update(pwarns)
                    else:
                        self._log.debug('Skipping extractor %s because it says it cannot process file %s ( %s ).',
                                        plugin.name(), file.file_name, file.file_url)
                else:
                    self._log.debug('Skipping extractor %s because it does not provide required digest types.',
                                    plugin.name())
            except Exception as err:
                self._log.critical('can_process() failed in extractor %s!',
                                   plugin.__class__.__name__, exc_info=err)
                errors.append(err)
        return ComputeDigestResponse(file, digests, warns, errors)

    def compare_digests(self, pair: DigestPair) -> ComputeSimilarityResponse:
        """Сравнивает два дайджеста и возвращает степень сходства от 0(нет сходства) до 1(идентичные).

        :param pair: Описание пары сравниваемых файлов.
        :return: Тип дайджеста; ID старого файла; ID нового файла;
        степень сходства или объект исключения (при ошибке)."""
        if not self._initialized:
            raise RuntimeError('Initializer has not been run for worker '
                               f'@{os.getpid()}/{threading.get_native_id()}/{id(self)}\n{repr(self.__dict__)}')
        for plugin in self._comparers:
            if pair.digest_type in plugin.digest_types():
                try:
                    older_content = gzip.decompress(pair.older_content)
                    newer_content = gzip.decompress(pair.newer_content)
                    similarity = plugin.compare_digests(pair.digest_type,
                                                        pair.older_id, older_content,
                                                        pair.newer_id, newer_content)
                except Exception as err:
                    self._log.error('Comparer %s failed to compare two digests of type %s',
                                    plugin.__class__.__name__, pair.digest_type, exc_info=err)
                    return ComputeSimilarityResponse(
                        digest_type=pair.digest_type,
                        older_id=pair.older_id,
                        newer_id=pair.newer_id,
                        similarity=None,
                        error=err
                    )
                else:
                    self._log.debug('Comparer %s compared two digests of type %s',
                                    plugin.__class__.__name__, pair.digest_type)
                    return ComputeSimilarityResponse(
                        digest_type=pair.digest_type,
                        older_id=pair.older_id,
                        newer_id=pair.newer_id,
                        similarity=similarity,
                        error=None
                    )
            else:
                self._log.debug('Ignoring comparer %s because it does not handle digest %s',
                                plugin.__class__.__name__, pair.digest_type)
        self._log.critical('Noone knows how to compare digest type %s', pair.digest_type)
        return ComputeSimilarityResponse(
            digest_type=pair.digest_type,
            older_id=pair.older_id,
            newer_id=pair.newer_id,
            similarity=None,
            error=ValueError(f'Noone knows how to compare digest type of {pair.digest_type}')
        )
