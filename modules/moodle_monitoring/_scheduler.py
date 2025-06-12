import typing as t
import asyncio
import collections
import datetime
import logging

import asyncpg

from modules.moodle import MoodleAdapter, course_id, assignment_id, role_id
from api import IntervalScheduler
from ._config import MoodleMonitorConfig
from ._data_layer import *


_T = t.TypeVar('_T')


async def aiobatch(src: t.AsyncIterable[_T], batch_size: int) -> t.AsyncIterable[list[_T]]:
    """Группирует содержимое асинхронного генератора `src` в пакеты по `batch_size` элементов."""
    batch_list = []
    async for item in src:
        batch_list.append(item)
        if len(batch_list) >= batch_size:
            yield batch_list
            batch_list.clear()
    if batch_list:
        yield batch_list


class Scheduler:
    def __init__(self, cfg: MoodleMonitorConfig, log: logging.Logger,
                 moodle: MoodleAdapter, conn: asyncpg.Connection):
        self.__moodle = moodle
        self.__conn = conn
        self.__cfg = cfg
        self.__log = log
        self.wakeup = asyncio.Event()
        self.__update_courses = IntervalScheduler[None](
            duration=datetime.timedelta(seconds=self.__cfg.courses.update_interval_seconds),
            batch_size=1, offset=0.0
        )
        self.__update_assignments = IntervalScheduler[course_id](
            duration=datetime.timedelta(seconds=self.__cfg.assignments.update_interval_seconds),
            batch_size=self.__cfg.assignments.update_course_batch_size,
            offset=1.0
        )
        self.__update_open_submissions = IntervalScheduler[assignment_id](
            duration=datetime.timedelta(seconds=self.__cfg.submissions.update_open_interval_seconds),
            batch_size=self.__cfg.submissions.update_open_batch_size,
            offset=1.0
        )
        self.__update_deadline_submissions = IntervalScheduler[assignment_id](
            duration=datetime.timedelta(seconds=self.__cfg.submissions.update_deadline_interval_seconds),
            batch_size=self.__cfg.submissions.update_deadline_batch_size,
            offset=1.0
        )

    async def scheduler_task(self) -> t.NoReturn:
        while True:
            #now = datetime.datetime.now(datetime.timezone.utc)
            now = datetime.datetime(2025, 5, 26, 12, 0, 0, tzinfo=datetime.timezone.utc)
            self.__log.warning('COURSES')
            await self._check_courses(now)
            self.__log.warning('ASSIGNS')
            await self._check_assignments(now)
            self.__log.warning('SUBS')
            await self._check_submissions_deadline(now)
            await self._check_submissions_active(now)
            try:
                self.wakeup.clear()
                await asyncio.wait_for(self.wakeup.wait(), self.__cfg.wakeup_interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def _check_courses(self, now: datetime.datetime) -> None:
        if self.__update_courses.is_empty():
            self.__update_courses.set_queried_objects([None], now)
        c = self.__update_courses.pop_triggered_objects(now)
        if c:
            try:
                self.__log.debug('Updating courses we are subscribed to...')
                course_stream = self.__moodle.stream_enrolled_courses(
                    in_progress_only=self.__cfg.courses.load_inprogress_only,
                    teacher_role_ids=[role_id(r) for r in self.__cfg.courses.teacher_role_ids],
                    batch_size=self.__cfg.courses.db_batch_size
                )
                async for chunk in aiobatch(course_stream, self.__cfg.courses.db_batch_size):
                    async with self.__conn.transaction(readonly=False):
                        await store_courses(self.__conn, chunk)
            except Exception as err:
                self.__log.error('Failed to update courses!', exc_info=err)
            else:
                self.__log.debug('Courses updated successfully.')

    async def _check_assignments(self, now: datetime.datetime) -> None:
        if self.__update_assignments.is_empty():
            try:
                async with self.__conn.transaction(readonly=True):
                    course_ids = await get_open_course_ids(self.__conn, now, with_dates_only=False)
            except Exception as err:
                self.__log.error('Failed to get open courses!', exc_info=err)
            else:
                self.__log.debug('%d open courses found, tracking: %s', len(course_ids),
                                 ', '.join(f'#{cid}' for cid in course_ids))
                self.__update_assignments.set_queried_objects(course_ids, now)
        course_ids = self.__update_assignments.pop_triggered_objects(now)
        if course_ids:
            try:
                self.__log.debug('Updating assignments for courses %s',
                                 ', '.join(f'#{cid}' for cid in course_ids))
                assign_stream = self.__moodle.stream_assignments(course_ids)
                total = collections.defaultdict(int)
                async for chunk in aiobatch(assign_stream, self.__cfg.assignments.db_batch_size):
                    for a in chunk:
                        total[a.course_id] += 1
                    async with self.__conn.transaction(readonly=False):
                        await store_assignments(self.__conn, chunk)
            except Exception as err:
                self.__log.error('Failed to update assignments!', exc_info=err)
            else:
                self.__log.info('Assignments updated successfully for course(s) %s',
                                ', '.join(f'#{cid}({count})' for cid, count in total.items()))

    async def _check_submissions_active(self, now: datetime.datetime) -> None:
        if self.__update_open_submissions.is_empty():
            try:
                async with self.__conn.transaction(readonly=True):
                    assigns = await get_active_assignments_ending_later(
                        self.__conn, now=now,
                        before=datetime.timedelta(seconds=self.__cfg.assignments.deadline_before_seconds),
                        after=datetime.timedelta(seconds=self.__cfg.assignments.deadline_after_seconds)
                    )
            except Exception as err:
                self.__log.error('Failed to get active assignments!', exc_info=err)
            else:
                if assigns:
                    self.__log.debug('Tracking %d open non-deadline assignments.', len(assigns))
                self.__update_open_submissions.set_queried_objects(assigns, now)
        assign_ids = self.__update_open_submissions.pop_triggered_objects(now)
        if assign_ids:
            await self._update_submissions_for(assign_ids)

    async def _check_submissions_deadline(self, now: datetime.datetime) -> None:
        if self.__update_deadline_submissions.is_empty():
            try:
                async with self.__conn.transaction(readonly=True):
                    assigns = await get_active_assignments_ending_soon(
                        self.__conn, now=now,
                        before=datetime.timedelta(seconds=self.__cfg.assignments.deadline_before_seconds),
                        after=datetime.timedelta(seconds=self.__cfg.assignments.deadline_after_seconds),
                        )
            except Exception as err:
                self.__log.error('Failed to get active assignments!', exc_info=err)
            else:
                if assigns:
                    self.__log.debug('Tracking %d open deadline assignments.', len(assigns))
                self.__update_deadline_submissions.set_queried_objects(assigns, now)
            assign_ids = self.__update_deadline_submissions.pop_triggered_objects(now)
            if assign_ids:
                await self._update_submissions_for(assign_ids)

    async def _update_submissions_for(self, assign_ids: t.Collection[assignment_id]):
        try:
            async with self.__conn.transaction(readonly=True):
                subtimes = await get_last_submission_times(self.__conn, assign_ids)
            for aid, lastsub in subtimes.items():
                self.__log.debug('Updating submissions for assignment #%d...', aid)
                start_time = lastsub + datetime.timedelta(seconds=1) if lastsub is not None else None
                assign_stream = self.__moodle.stream_submissions(aid, submitted_after=start_time)
                total = 0
                async for chunk in aiobatch(assign_stream, self.__cfg.submissions.db_batch_size):
                    total += len(chunk)
                    async with self.__conn.transaction(readonly=False):
                        await store_submissions(self.__conn, chunk)
                self.__log.debug('Found %d new submissions for assignment #%d.', total, aid)
        except Exception as err:
            self.__log.error('Failed to update submissions!', exc_info=err)
