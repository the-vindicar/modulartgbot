"""Класс, контролирующий процесс извлечения и сравнения выжимок из файлов."""
import typing as t
import asyncio
import concurrent.futures
import datetime
import logging
import logging.handlers
import multiprocessing

from api import aiobatch
from modules.moodle import MoodleAdapter, MoodleError, WebServerError
from .config import FileComparisonConfig
from ..models import FileToCompute, DigestPair, FileComparison, FileDigest, FileWarning
from .worker import (
    ComputeDigestResponse, ComputeSimilarityResponse,
    get_classes, initializer, extract_digests, compare_digests
)


class DigestManager:
    """Создаёт пул процессов и управляет ими."""
    def __init__(self, cfg: FileComparisonConfig, m: MoodleAdapter, log: logging.Logger):
        self.cfg = cfg
        self._moodle = m
        self._log = log
        available_digest_types: set[str] = set()
        available_names: set[str] = set()
        extractors, comparers = get_classes()
        for cls in extractors:
            available_digest_types.update(cls.digest_types())
            name = cls.plugin_name()
            available_names.add(name)
            self._log.debug('Found extractor %s (%s), it computes %s',
                            cls.__name__, name, ', '.join(cls.digest_types()))
        for cls in comparers:
            self._log.debug('Found comparer %s, it compares %s',
                            cls.__name__, ', '.join(cls.digest_types()))
        for k in list(cfg.plugin_settings.keys()):
            if k not in available_names:
                log.warning('Plugin %s not found, ignoring settings.', k)
                del cfg.plugin_settings[k]
        self._available_digests = frozenset(available_digest_types)
        self._pool: t.Optional[concurrent.futures.Executor] = None
        self._log_queue: multiprocessing.Queue = multiprocessing.Queue()
        self._listener = logging.handlers.QueueListener(self._log_queue, *logging.root.handlers,
                                                        respect_handler_level=True)
        self.batch_size: int = 4

    async def __aenter__(self) -> t.Self:
        self._pool = concurrent.futures.ProcessPoolExecutor(
            max_workers=None,
            initializer=initializer,
            initargs=(self._log.name+'.worker', self._log.level, self._log_queue, self.cfg.plugin_settings))
        self._listener.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._pool.shutdown(wait=True, cancel_futures=True)
        self._listener.stop()

    @property
    def available_digests(self) -> frozenset[str]:
        """Список доступных дайджестов."""
        return self._available_digests

    async def extract_digests(
            self, missing_files: t.AsyncIterable[FileToCompute]
    ) -> t.AsyncIterable[tuple[list[FileDigest], list[FileWarning]]]:
        """Обрабатывает файлы, у которых недостаёт дайджестов."""
        if self._pool is None:
            raise RuntimeError('Manager is not initialized. Did you forget `async with`?')
        loop = asyncio.get_running_loop()
        futures: list[asyncio.Future[ComputeDigestResponse]] = []
        now = datetime.datetime.now(datetime.timezone.utc)
        max_age = (datetime.timedelta(days=self.cfg.ignore_files_older_than_days)
                   if self.cfg.ignore_files_older_than_days else None)
        async for file_batch in aiobatch(missing_files, self.batch_size):  # обрабатываем файлы порциями
            futures.clear()
            for file in file_batch:
                if not file.digest_types:
                    self._log.warning('Ignoring file %s due because it specified no missing digests.',
                                      file.file_url)
                    continue
                if self.cfg.ignore_files_larger_than and file.file_size > self.cfg.ignore_files_larger_than:
                    self._log.info('Ignoring file %s due to its large size of %d bytes.',
                                   file.file_url, file.file_size)
                    yield file.make_empty_digests(), []
                    continue
                age = now - file.file_uploaded
                if max_age and age > max_age:
                    self._log.info('Ignoring file %s because it is too old (uploaded %s ago).',
                                   file.file_url, age)
                    yield file.make_empty_digests(), []
                    continue
                try:
                    dlresponse = await self._moodle.get_download_response(file.file_url)
                    self._log.debug('Downloading file %s from %s', file.file_name, file.file_url)
                    async with dlresponse:
                        content = await dlresponse.read()  # скачиваем файл
                    self._log.debug('Processing file %s using executor %s',
                                    file.file_name, type(self._pool).__name__)
                    future = loop.run_in_executor(  # планируем извлечение дайджеста в дочернем процессе
                        self._pool, extract_digests,
                        file, content
                    )
                    del content
                except WebServerError as err:
                    self._log.warning('Failed to download file %s ( %s ) due to webserver error: %s',
                                      file.file_name, file.file_url, err)
                except MoodleError as err:
                    self._log.warning('Failed to download file %s: %s', file.file_name, err)
                    if err.errorcode == 404:  # если файл не найден, игнорируем его в будущем
                        self._log.warning('Ignoring file %s in the future', file.file_name)
                        yield file.make_empty_digests(), []
                except Exception as err:
                    self._log.error('Unexpected error when processing file %s ( %s )',
                                    file.file_name, file.file_url, exc_info=err)
                else:
                    futures.append(future)  # собираем future для всех файлов в один список
            self._log.debug('Waiting for %d files to process...', len(futures))
            for response in await asyncio.gather(*futures, return_exceptions=True):  # перебираем результаты
                response: t.Union[Exception, ComputeDigestResponse]
                if isinstance(response, Exception):
                    self._log.warning('Unexpected error while processing files', exc_info=response)
                    continue
                for err in response.errors:
                    if isinstance(err, Exception):
                        self._log.warning('Failed to create digest for file %s ( %s )',
                                          response.file.file_name, response.file.file_url, exc_info=err)
                    else:
                        self._log.debug('File %s ( %s ): %s',
                                        response.file.file_name, response.file.file_url, err)
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
                self._log.debug('Received %d digests and %d warnings for file %s',
                                len(digests), len(warnings), response.file.file_name)
                yield digests, warnings

    async def compare_digests(self, missing_comps: t.AsyncIterable[DigestPair]) -> t.AsyncIterable[FileComparison]:
        """Сравнивает пары дайджестов и возвращает результаты сравнений."""
        if self._pool is None:
            raise RuntimeError('Manager is not initialized. Did you forget `async with`?')
        loop = asyncio.get_running_loop()
        futures: list[asyncio.Future[ComputeSimilarityResponse]] = []
        async for comp_batch in aiobatch(missing_comps, self.batch_size):  # обрабатываем пары порциями
            futures.clear()
            for pair in comp_batch:
                self._log.debug('Comparing %s for %s and %s using executor %s',
                                pair.digest_type, pair.older_id, pair.newer_id, type(self._pool).__name__)
                future = loop.run_in_executor(  # планируем сравнение дайджестов в дочернем процессе
                    self._pool, compare_digests,
                    pair
                )
                futures.append(future)
            if not futures:
                break
            for response in await asyncio.gather(*futures, return_exceptions=True):
                response: t.Union[Exception, ComputeSimilarityResponse]
                if isinstance(response, Exception):
                    self._log.warning('Unexpected error while comparing digests', exc_info=response)
                    continue
                if response.similarity is None:
                    self._log.warning('Failed to compare two files using digest "%s"',
                                      response.digest_type, exc_info=response.error)
                else:
                    yield FileComparison(older_file_id=response.older_id, older_digest_type=response.digest_type,
                                         newer_file_id=response.newer_id, newer_digest_type=response.digest_type,
                                         similarity_score=float(response.similarity))
