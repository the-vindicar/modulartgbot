"""Реализует периодический анализ новых файлов."""
import asyncio
import datetime
import logging

from api import aiobatch, log_ticker
from modules.moodle import MoodleAdapter
from .models import FileDataRepository
from .digests import DigestManager, FileComparisonConfig


async def scheduler(
        log: logging.Logger,
        cfg: FileComparisonConfig,
        repo: FileDataRepository,
        m: MoodleAdapter
):
    """Реализует периодические анализ и сравнение новых файлов."""
    manager = DigestManager(cfg, m, log)
    async with manager:
        while True:
            log.debug('Looking for files to process...')
            try:
                max_age = (
                    datetime.timedelta(days=cfg.ignore_files_older_than_days)
                    if cfg.ignore_files_older_than_days else None
                )
                async with log_ticker(log, 'Идёт загрузка работ (прошло {})...', 30):
                    missing_digest_stream = repo.stream_files_with_missing_digests(
                        available_digest_types=manager.available_digests,
                        max_age=max_age,
                        max_size=cfg.ignore_files_larger_than
                    )
                    new_digest_stream = manager.extract_digests(missing_digest_stream)
                    digest_count, warning_count = 0, 0
                    async for new_digests, new_warnings in new_digest_stream:
                        digest_count += len(new_digests)
                        warning_count += len(new_warnings)
                        await repo.store_digests(new_digests)
                        await repo.store_warnings(new_warnings)
                if digest_count > 0 or warning_count > 0:
                    log.info('Stored %d new digests and %d new warnings.', digest_count, warning_count)
                else:
                    log.debug('No new digests or warnings to store.')
                async with log_ticker(log, 'Идёт сравнение работ (прошло {})...', 30):
                    missing_comparison_stream = repo.stream_missing_comparisons(max_age_diff=max_age)
                    new_comparison_stream = manager.compare_digests(missing_comparison_stream)
                    comp_count = 0
                    async for batch in aiobatch(new_comparison_stream, manager.batch_size):
                        comp_count += len(batch)
                        await repo.store_comparisons(batch)
                if comp_count > 0:
                    log.info('Stored %d new comparisons.', comp_count)
                else:
                    log.debug('No new comparisons to store.')
            except Exception as err:
                log.critical('Unexpected error', exc_info=err)
            await asyncio.sleep(cfg.refresh_interval_seconds)
