"""Содержит логику, необходимую для периодического опроса сервера Moodle на предмет изменений в нём."""
import typing as t
import asyncio
import collections
import datetime
import logging

from modules.moodle import MoodleAdapter, course_id, assignment_id
from api import IntervalScheduler, aiobatch
from ._config import MoodleMonitorConfig
from .datalayer import MoodleRepository


_T = t.TypeVar('_T')


class Scheduler:
    """Реализует периодический опрос сервера Moodle и кэширует результаты в БД.
    Распределяет запросы по интервалу времени, чтобы снизить пиковую нагрузку."""
    def __init__(self, cfg: MoodleMonitorConfig, log: logging.Logger,
                 moodle: MoodleAdapter, repo: MoodleRepository):
        self.__moodle = moodle
        self.__repo = repo
        self.__cfg = cfg
        self.__log = log
        self.wakeup = asyncio.Event()
        self.__update_courses = IntervalScheduler[None](
            duration=datetime.timedelta(seconds=self.__cfg.courses.update_interval_seconds),
            batch_size=1, alignment=0.0
        )
        self.__update_assignments = IntervalScheduler[course_id](
            duration=datetime.timedelta(seconds=self.__cfg.assignments.update_interval_seconds),
            batch_size=self.__cfg.assignments.update_course_batch_size,
            alignment=1.0
        )
        self.__update_open_submissions = IntervalScheduler[assignment_id](
            duration=datetime.timedelta(seconds=self.__cfg.submissions.update_open_interval_seconds),
            batch_size=self.__cfg.submissions.update_open_batch_size,
            alignment=1.0
        )
        self.__update_deadline_submissions = IntervalScheduler[assignment_id](
            duration=datetime.timedelta(seconds=self.__cfg.submissions.update_deadline_interval_seconds),
            batch_size=self.__cfg.submissions.update_deadline_batch_size,
            alignment=1.0
        )

    async def scheduler_task(self) -> t.NoReturn:
        """Выполняет бесконечный цикл ожидания и опроса сервера Moodle на предмет изменений."""
        while True:
            # TODO: вернуть обратно правильное время. Это только для тестирования!
            # now = datetime.datetime.now(datetime.timezone.utc)
            now = datetime.datetime(2025, 5, 26, 12, 0, 0, tzinfo=datetime.timezone.utc)
            await self._check_courses(now)
            await self._check_assignments(now)
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
                    batch_size=self.__cfg.courses.db_batch_size
                )
                async for chunk in aiobatch(course_stream, self.__cfg.courses.db_batch_size):
                    await self.__repo.store_courses(chunk, now)
            except Exception as err:
                self.__log.error('Failed to update courses!', exc_info=err)
            else:
                self.__log.debug('Courses updated successfully.')

    async def _check_assignments(self, now: datetime.datetime) -> None:
        """Проверяет, нет ли измений в заданиях отслеживаемых курсов."""
        if self.__update_assignments.is_empty():
            try:
                course_ids = await self.__repo.get_open_course_ids(now, with_dates_only=False)
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
                known_assignments: dict[course_id, list[assignment_id]] = collections.defaultdict(list)
                async for chunk in aiobatch(assign_stream, self.__cfg.assignments.db_batch_size):
                    for a in chunk:
                        known_assignments[a.course_id].append(a.id)
                    await self.__repo.store_assignments(chunk)
                await self.__repo.drop_assignments_except_for(known_assignments)
            except Exception as err:
                self.__log.error('Failed to update assignments!', exc_info=err)
            else:
                self.__log.info('Assignments updated successfully for course(s) %s',
                                ', '.join(f'#{cid}({len(assigns)})' for cid, assigns in known_assignments.items()))

    async def _check_submissions_active(self, now: datetime.datetime) -> None:
        """Проверяет, нет ли новых ответов на задания, которые завершаются ещё не скоро."""
        if self.__update_open_submissions.is_empty():
            try:
                assigns = await self.__repo.get_active_assignment_ids_not_ending_soon(
                    now=now,
                    before=datetime.timedelta(seconds=self.__cfg.assignments.deadline_before_seconds),
                    after=datetime.timedelta(seconds=self.__cfg.assignments.deadline_after_seconds)
                )
            except Exception as err:
                self.__log.error('Failed to get active assignments!', exc_info=err)
            else:
                self.__log.debug('Tracking %d open non-deadline assignments.', len(assigns))
                self.__update_open_submissions.set_queried_objects(assigns, now)
        assign_ids = self.__update_open_submissions.pop_triggered_objects(now)
        if assign_ids:
            await self._update_submissions_for(assign_ids)

    async def _check_submissions_deadline(self, now: datetime.datetime) -> None:
        """Проверяет, нет ли новых ответов на задания, которые скоро завершатся."""
        if self.__update_deadline_submissions.is_empty():
            try:
                assigns = await self.__repo.get_active_assignment_ids_ending_soon(
                    now=now,
                    before=datetime.timedelta(seconds=self.__cfg.assignments.deadline_before_seconds),
                    after=datetime.timedelta(seconds=self.__cfg.assignments.deadline_after_seconds),
                    )
            except Exception as err:
                self.__log.error('Failed to get active assignments!', exc_info=err)
            else:
                self.__log.debug('Tracking %d open deadline assignments.', len(assigns))
                self.__update_deadline_submissions.set_queried_objects(assigns, now)
            assign_ids = self.__update_deadline_submissions.pop_triggered_objects(now)
            if assign_ids:
                await self._update_submissions_for(assign_ids)

    async def _update_submissions_for(self, assign_ids: t.Collection[assignment_id]):
        """Скачивает и сохраняет ответы на указанные задания."""
        try:
            subtimes = await self.__repo.get_last_submission_times(assign_ids)
            for aid, lastsub in subtimes.items():
                self.__log.debug('Updating submissions for assignment #%d...', aid)
                start_time = lastsub + datetime.timedelta(seconds=1) if lastsub is not None else None
                assign_stream = self.__moodle.stream_submissions(aid, submitted_after=start_time)
                total = 0
                async for chunk in aiobatch(assign_stream, self.__cfg.submissions.db_batch_size):
                    total += len(chunk)
                    await self.__repo.store_submissions(chunk)
                self.__log.debug('Found %d new submissions for assignment #%d.', total, aid)
        except Exception as err:
            self.__log.error('Failed to update submissions!', exc_info=err)
