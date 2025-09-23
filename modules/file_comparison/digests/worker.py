"""
Модуль, управляющий плагинами для извлечения и сравнения выжимок из файлов.
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


__all__ = ['ComputeDigestResponse', 'ComputeSimilarityResponse',
           'get_classes', 'initializer', 'extract_digests', 'compare_digests']


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


extractors: list[DigestExtractorABC] = []
comparers: list[DigestComparerABC] = []
log: t.Optional[logging.Logger] = logging.getLogger()
is_initialized = False


def get_classes() -> tuple[list[t.Type[DigestExtractorABC]], list[t.Type[DigestComparerABC]]]:
    """Загружает дайджест-плагины и находит все актуальные классы плагинов."""
    extractors_classes: list[t.Type[DigestExtractorABC]] = []
    comparer_classes: list[t.Type[DigestComparerABC]] = []
    package_name = __name__.rpartition('.')[0]
    for item in (Path(__file__).parent / 'plugins').glob('*'):
        if not (  # мы пропускаем всё, что не попадает в следующие категории:
                (       # .py файлы, не начинающиеся с подчёркивания или точки
                        item.is_file() and item.suffix.lower() == '.py' and
                        (not item.name.startswith('_') and not item.name.startswith('.'))
                ) or
                (       # каталоги, содержащие файл __init__.py
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
                    extractors_classes.append(attr)
                if issubclass(attr, DigestComparerABC) and attr is not DigestComparerABC:
                    comparer_classes.append(attr)
    return extractors_classes, comparer_classes


def initializer(log_name: str, log_level: int, log_queue: multiprocessing.Queue, settings: dict[str, dict[str, t.Any]]):
    """Импортирует и инициализирует плагины в дочерних процессах."""
    global extractors, comparers, log, is_initialized
    log = logging.getLogger(log_name)
    log.handlers.clear()
    formatter = logging.Formatter(
        '@%(process)d: %(message)s'
    )
    handler = logging.handlers.QueueHandler(log_queue)
    handler.setFormatter(formatter)
    handler.setLevel(log_level)
    log.addHandler(handler)
    log.setLevel(log_level)

    extractor_classes, comparer_classes = get_classes()
    for cls in extractor_classes:
        try:
            instance = cls()
            name = instance.plugin_name()
            instance.initialize(log.getChild(name), settings.get(name, {}))
        except Exception as err:
            log.critical('Failed to initialize extractor %s', cls.__name__, exc_info=err)
        else:
            log.debug('Extractor %s (%s) ready.', cls.__name__, instance.plugin_name())
            extractors.append(instance)
    for cls in comparer_classes:
        try:
            instance = cls()
            name = instance.plugin_name()
            instance.initialize(log.getChild(name), settings.get(name, {}))
        except Exception as err:
            log.critical('Failed to initialize comparer %s', cls.__name__, exc_info=err)
        else:
            log.debug('Comparer %s ready.', cls.__name__)
            comparers.append(instance)
    is_initialized = True
    log.debug(f'Worker @{os.getpid()}/{threading.get_native_id()} completed initialization')


def extract_digests(file: FileToCompute, content: bytes) -> ComputeDigestResponse:
    """Обрабатывает один файл и извлекает из него все возможные дайджесты.

    :param file: Описание обрабатываемого файла.
    :param content: Содержимое обрабатываемого файла.
    :return: Результат обработки файла."""
    if not is_initialized:
        raise RuntimeError('Initializer has not been run for worker '
                           f'{os.getpid()}/{threading.get_native_id()}')
    digests: dict[str, t.Optional[bytes]] = {n: None for n in file.digest_types}
    warns = {}
    errors = []
    for plugin in extractors:
        try:
            if not file.digest_types.isdisjoint(plugin.digest_types()):
                if plugin.can_process_file(file.file_name, file.mimetype, file.file_size):
                    try:
                        pdigests, pwarns = plugin.process_file(file.file_name, file.mimetype, content)
                    except Exception as err:
                        log.error('Extractor %s failed to process file %s ( %s ).',
                                  plugin.plugin_name(), file.file_name, file.file_url, exc_info=err)
                        errors.append(err)
                    else:
                        for digest_type, digest_data in pdigests.items():
                            if digest_data is not None:
                                digest_data = gzip.compress(digest_data, compresslevel=9)
                            else:
                                log.warning('Extractor %s failed to return digest %s for file %s ( %s ).',
                                            plugin.plugin_name(), digest_type, file.file_name, file.file_url)
                            digests[digest_type] = digest_data
                        warns.update(pwarns)
                else:
                    log.debug('Skipping extractor %s because it says it cannot process file %s ( %s ).',
                              plugin.plugin_name(), file.file_name, file.file_url)
            else:
                log.debug('Skipping extractor %s because it does not provide required digest types.',
                          plugin.plugin_name())
        except Exception as err:
            log.critical('can_process() failed in extractor %s!',
                         plugin.__class__.__name__, exc_info=err)
            errors.append(err)
    return ComputeDigestResponse(file, digests, warns, errors)


def compare_digests(pair: DigestPair) -> ComputeSimilarityResponse:
    """Сравнивает два дайджеста и возвращает степень сходства от 0(нет сходства) до 1(идентичные).

    :param pair: Описание пары сравниваемых файлов.
    :return: Тип дайджеста; ID старого файла; ID нового файла;
    степень сходства или объект исключения (при ошибке)."""
    if not is_initialized:
        raise RuntimeError('Initializer has not been run for worker '
                           f'@{os.getpid()}/{threading.get_native_id()}')
    for plugin in comparers:
        if pair.digest_type in plugin.digest_types():
            try:
                older_content = gzip.decompress(pair.older_content)
                newer_content = gzip.decompress(pair.newer_content)
                similarity = plugin.compare_digests(pair.digest_type,
                                                    pair.older_id, older_content,
                                                    pair.newer_id, newer_content)
            except Exception as err:
                log.error('Comparer %s failed to compare two digests of type %s',
                          plugin.__class__.__name__, pair.digest_type, exc_info=err)
                return ComputeSimilarityResponse(
                    digest_type=pair.digest_type,
                    older_id=pair.older_id,
                    newer_id=pair.newer_id,
                    similarity=None,
                    error=err
                )
            else:
                log.debug('Comparer %s compared two digests of type %s: %.1f%% similarity',
                          plugin.__class__.__name__, pair.digest_type, similarity * 100)
                return ComputeSimilarityResponse(
                    digest_type=pair.digest_type,
                    older_id=pair.older_id,
                    newer_id=pair.newer_id,
                    similarity=similarity,
                    error=None
                )
        else:
            log.debug('Ignoring comparer %s because it does not handle digest %s',
                      plugin.__class__.__name__, pair.digest_type)
    log.critical('Noone knows how to compare digest type %s', pair.digest_type)
    return ComputeSimilarityResponse(
        digest_type=pair.digest_type,
        older_id=pair.older_id,
        newer_id=pair.newer_id,
        similarity=None,
        error=ValueError(f'Noone knows how to compare digest type of {pair.digest_type}')
    )
