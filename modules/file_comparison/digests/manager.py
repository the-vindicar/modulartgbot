"""Класс, управляющий плагинами для извлечения и сравнения выжимок из файлов."""
import typing as t
import asyncio
import concurrent.futures
import datetime
import dataclasses
import importlib
import gzip
import logging
from pathlib import Path

from api import aiobatch
from modules.moodle import MoodleAdapter, MoodleError
from .base import DigestExtractorABC, DigestComparerABC
from .config import FileComparisonConfig
from ..models import FileToCompute, DigestPair, FileComparison, FileDigest, FileWarning


@dataclasses.dataclass
class ComputeDigestResponse:
    """Отклик при извлечении дайджестов из файла."""
    file: FileToCompute
    gzipped_digests: dict[str, t.Optional[bytes]]
    warnings: dict[str, str]
    errors: list[Exception]


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
        for item in (Path(__file__) / 'plugins').parent.glob('*'):
            if not (item.is_file() and item.suffix.lower() == '.py' and
                    (not item.name.startswith('_') and not item.name.startswith('.'))):
                continue
            elif not (item.is_dir() and (item / '__init__.py').is_file()):
                continue
            importkey = f'{__name__}.plugins.{item.stem}'
            module = importlib.import_module(importkey)
            for attrname in dir(module):
                attr = getattr(module, attrname)
                if isinstance(attr, type):
                    if issubclass(attr, DigestExtractorABC):
                        extractors.append(attr)
                    if issubclass(attr, DigestComparerABC):
                        comparers.append(attr)
        return extractors, comparers

    def __init__(self, settings: dict[str, dict[str, t.Any]]):
        self._extractors: list[DigestExtractorABC] = []
        self._comparers: list[DigestComparerABC] = []
        self._settings = settings.copy()

    def initializer(self) -> None:
        """Импортирует и инициализирует плагины в дочерних процессах."""
        extractors, comparers = self.get_classes()
        for cls in extractors:
            try:
                instance = cls()
                instance.initialize(self._settings.get(instance.name(), {}))
            except Exception as err:
                print(err)
            else:
                self._extractors.append(instance)

    def extract_digests(self, file: FileToCompute, content: bytes) -> ComputeDigestResponse:
        """Обрабатывает один файл и извлекает из него все возможные дайджесты.

        :param file: Описание обрабатываемого файла.
        :param content: Содержимое обрабатываемого файла.
        :return: Результат обработки файла."""
        digests: dict[str, t.Optional[bytes]] = {n: None for n in file.digest_types}
        warns = {}
        errors = []
        for plugin in self._extractors:
            try:
                if (not file.digest_types.isdisjoint(plugin.digest_types()) and
                        plugin.can_process_file(file.file_name, file.mimetype, file.file_size)):
                    pdigests, pwarns = plugin.process_file(file.file_name, file.mimetype, content)
                    for digest_type, digest_data in pdigests:
                        if digest_data is not None:
                            digest_data = gzip.compress(digest_data, compresslevel=9)
                        digests[digest_type] = digest_data
                    warns.update(pwarns)
            except Exception as err:
                errors.append(err)
        return ComputeDigestResponse(file, digests, warns, errors)

    def compare_digests(self, pair: DigestPair) -> ComputeSimilarityResponse:
        """Сравнивает два дайджеста и возвращает степень сходства от 0(нет сходства) до 1(идентичные).

        :param pair: Описание пары сравниваемых файлов.
        :return: Тип дайджеста; ID старого файла; ID нового файла;
        степень сходства или объект исключения (при ошибке)."""
        for plugin in self._comparers:
            if pair.digest_type in plugin.digest_types():
                try:
                    older_content = gzip.decompress(pair.older_content)
                    newer_content = gzip.decompress(pair.newer_content)
                    similarity = plugin.compare_digests(pair.digest_type,
                                                        pair.older_id, older_content,
                                                        pair.newer_id, newer_content)
                except Exception as err:
                    return ComputeSimilarityResponse(
                        digest_type=pair.digest_type,
                        older_id=pair.older_id,
                        newer_id=pair.newer_id,
                        similarity=None,
                        error=err
                    )
                else:
                    return ComputeSimilarityResponse(
                        digest_type=pair.digest_type,
                        older_id=pair.older_id,
                        newer_id=pair.newer_id,
                        similarity=similarity,
                        error=None
                    )
        return ComputeSimilarityResponse(
            digest_type=pair.digest_type,
            older_id=pair.older_id,
            newer_id=pair.newer_id,
            similarity=None,
            error=ValueError(f'Noone knows how to compare digest type of {pair.digest_type}')
        )


class DigestManager:
    """Создаёт пул процессов и управляет ими."""
    def __init__(self, cfg: FileComparisonConfig, m: MoodleAdapter, log: logging.Logger):
        self.cfg = cfg
        self._moodle = m
        self._log = log
        available_digest_types: set[str] = set()
        available_names: set[str] = set()
        extractors, _ = Worker.get_classes()
        for cls in extractors:
            available_digest_types.update(cls.digest_types())
            available_names.add(cls.name())
        for k in list(cfg.plugin_settings.keys()):
            if k not in available_names:
                log.warning('Plugin %s not found, ignoring settings.', k)
                del cfg.plugin_settings[k]
        self._available_digests = frozenset(available_digest_types)
        self._worker = Worker(cfg.plugin_settings)
        self._pool: t.Optional[concurrent.futures.Executor] = None
        self.batch_size: int = 4

    async def __aenter__(self) -> t.Self:
        self._pool = concurrent.futures.ProcessPoolExecutor(max_workers=None,
                                                            initializer=self._worker.initializer)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._pool.shutdown(wait=True, cancel_futures=True)

    @property
    def available_digests(self) -> frozenset[str]:
        """Список доступных дайджестов."""
        return self._available_digests

    async def extract_digests(
            self, missing_files: t.AsyncIterable[FileToCompute]
    ) -> t.AsyncIterable[tuple[list[FileDigest], list[FileWarning]]]:
        """Обрабатывает файлы, у которых недостаёт дайджестов."""
        loop = asyncio.get_running_loop()
        futures: list[asyncio.Future[ComputeDigestResponse]] = []
        now = datetime.datetime.now(datetime.timezone.utc)
        max_age = (datetime.timedelta(days=self.cfg.ignore_files_older_than_days)
                   if self.cfg.ignore_files_older_than_days else None)
        async for file_batch in aiobatch(missing_files, self.batch_size):  # обрабатываем файлы порциями
            futures.clear()
            for file in file_batch:
                if self.cfg.ignore_files_larger_than and file.file_size > self.cfg.ignore_files_larger_than:
                    self._log.info('Ignoring file %s due to its large size of %d bytes.',
                                   file.file_url, file.file_size)
                    continue
                age = now - file.file_uploaded
                if max_age and age > max_age:
                    self._log.info('Ignoring file %s because it is too old (uploaded %s ago).',
                                   file.file_url, age)
                try:
                    response = await self._moodle.get_download_response(file.file_url)
                    self._log.debug('Downloading file %s from %s', file.file_name, file.file_url)
                    async with response:
                        content = await response.read()  # скачиваем файл
                    future = loop.run_in_executor(  # планируем извлечение дайджеста в дочернем процессе
                        self._pool, self._worker.extract_digests,
                        file, content
                    )
                    del content
                    futures.append(future)  # собираем future для всех файлов в один список
                except MoodleError:
                    self._log.warning('Failed to download file %s ( %s )',
                                      file.file_name, file.file_url)
                except Exception as err:
                    self._log.error('Unexpected error when processing file %s ( %s )',
                                    file.file_name, file.file_url, exc_info=err)
            if not futures:
                break
            for item in asyncio.as_completed(futures):  # перебираем файлы в порядке их обработки
                response = await item  # ждем, когда обработается очередной файл
                for err in response.errors:
                    self._log.warning('Failed to create digest for file %s ( %s )',
                                      response.file.file_name, response.file.file_url, exc_info=err)
                digests = [
                    FileDigest(
                        file_id=response.file.file_id,
                        digest_type=digest_type,
                        user_id=response.file.user_id,
                        user_name=response.file.user_name,
                        assignment_id=response.file.assignment_id,
                        submission_id=response.file.submission_id,
                        file_name=response.file.file_name,
                        file_url=response.file.file_url,
                        file_uploaded=response.file.file_uploaded,
                        created=datetime.datetime.now(datetime.timezone.utc),
                        content=digest_content
                    )
                    for digest_type, digest_content in response.gzipped_digests.items()
                ]
                warnings = [
                    FileWarning(
                        file_id=response.file.file_id,
                        warning_type=warn_type,
                        warning_info=warn_content
                    )
                    for warn_type, warn_content in response.warnings.items()
                ]
                yield digests, warnings

    async def compare_digests(self, missing_comps: t.AsyncIterable[DigestPair]) -> t.AsyncIterable[FileComparison]:
        """Сравнивает пары дайджестов и возвращает результаты сравнений."""
        loop = asyncio.get_running_loop()
        futures: list[asyncio.Future[ComputeSimilarityResponse]] = []
        async for comp_batch in aiobatch(missing_comps, self.batch_size):  # обрабатываем пары порциями
            futures.clear()
            for pair in comp_batch:
                future = loop.run_in_executor(  # планируем сравнение дайджестов в дочернем процессе
                    self._pool, self._worker.compare_digests,
                    pair
                )
                futures.append(future)
            if not futures:
                break
            for item in asyncio.as_completed(futures):  # перебираем сравнения в порядке их обработки
                response = await item  # ждем, когда обработается очередное сравнение
                if response.similarity is None:
                    self._log.warning('Failed to compare two files using digest "%s"',
                                      response.digest_type, exc_info=response.error)
                else:
                    yield FileComparison(older_file_id=response.older_id, older_digest_type=response.digest_type,
                                         newer_file_id=response.newer_id, newer_digest_type=response.digest_type,
                                         similarity_score=float(response.similarity))
