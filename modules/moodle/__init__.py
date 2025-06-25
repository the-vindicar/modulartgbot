"""Предоставляет обёртку для доступа к серверу Moodle."""
from typing import Iterable, AsyncIterable, Optional
import datetime
import dataclasses
import logging
import os
import zoneinfo

from ._classes import *
from .moodle import Moodle, MoodleError

from api import CoreAPI


class MoodleAdapter(Moodle):
    """Адаптер, расширяющий базовый класс для работы с Moodle методами для работы с набором упрощённых DTO."""
    async def stream_enrolled_courses(self,
                                      in_progress_only: bool = True,
                                      batch_size: int = 10,
                                      ) -> AsyncIterable[Course]:
        """Возвращает поток объектов-курсов, на которые мы подписаны, соответствующих условиям.
        :param in_progress_only: Если True, возвращать нужно только курсы, которые уже начались, но ещё не закончились.
        :param batch_size: Сколько курсов запрашивать за один запрос.
        :returns: Асинхронный поток экземпляров класса :class:`Course`."""
        offset, limit = 0, batch_size
        while True:
            raw_course_data = await self.function.core_course_get_enrolled_courses_by_timeline_classification(
                classification='inprogress' if in_progress_only else 'all',
                offset=offset, limit=limit)
            raw_courses = raw_course_data.courses
            if not raw_courses:
                break
            offset = raw_course_data.nextoffset
            for item in raw_courses:
                starts = self.timestamp2datetime(item.startdate)
                ends = self.timestamp2datetime(item.enddate)
                cid = item.id
                participants = [p async for p in self.stream_users(cid)]
                c = Course(id=cid, shortname=item.shortname, fullname=item.fullname,
                           starts=starts, ends=ends, participants=tuple(participants))
                yield c

    async def stream_users(self,
                           courseid: course_id,
                           batch_size: int = 50
                           ) -> AsyncIterable[Participant]:
        """Возвращает поток объектов-участников данного курса.
        :param courseid: Идентификатор курса, для которого мы загружаем участников.
        :param batch_size: Сколько участников запрашивать за один запрос.
        :returns: Асинхронный поток экземпляров класса :class:`Participant`."""
        options = [
            {'name': 'userfields', 'value': 'id, fullname, email, roles, groups'}
        ]
        offset, limit = 0, batch_size
        while True:
            limits = [
                {'name': 'limitfrom', 'value': offset},
                {'name': 'limitnumber', 'value': limit},
            ]
            raw_users = await self.function.core_enrol_get_enrolled_users(
                courseid=courseid, options=options + limits
            )
            if not raw_users:
                break
            offset += len(raw_users)
            for raw_user in raw_users:
                p = Participant(
                    user=User(id=raw_user.id, name=raw_user.fullname, email=raw_user.email),
                    roles=tuple([Role(id=r.roleid, name=r.name) for r in raw_user.roles or ()]),
                    groups=tuple([Group(id=g.id, name=g.name) for g in raw_user.groups or ()]),
                )
                yield p

    async def stream_assignments(self, course_ids: Iterable[course_id]) -> AsyncIterable[Assignment]:
        """Возвращает поток объектов-заданий (assignment), имеющихся в данных курсах.
        :param course_ids: Идентификаторы курсов, из которых мы загружаем задания.
        :returns: Асинхронный поток экземпляров класса :class:`Assignment`."""
        response = await self.function.mod_assign_get_assignments(
            courseids=list(course_ids), includenotenrolledcourses=True
        )
        for course in response.courses:
            raw_assigns = course.assignments
            if not raw_assigns:
                continue
            for raw_assign in raw_assigns:
                a = Assignment(
                    id=raw_assign.id,
                    name=raw_assign.name,
                    course_id=raw_assign.course,
                    opening=self.timestamp2datetime(raw_assign.allowsubmissionsfromdate),
                    closing=self.timestamp2datetime(raw_assign.duedate),
                    cutoff=self.timestamp2datetime(raw_assign.cutoffdate)
                )
                yield a

    async def stream_submissions(self, assignmentid: assignment_id,
                                 submitted_after: Optional[datetime.datetime] = None,
                                 submitted_before: Optional[datetime.datetime] = None
                                 ) -> AsyncIterable[Submission]:
        """Возвращает поток объектов-ответов на указанное задание.
        :param assignmentid: Идентификатор задания, для которого мы загружаем ответы.
        :param submitted_after: Дата и время, позднее которого (включительно) ответ был загружен.
        :param submitted_before: Дата и время, ранее которого (включительно) ответ был загружен.
        :returns: Асинхронный поток экземпляров класса :class:`Submission`."""
        responce = await self.function.mod_assign_get_submissions(
            assignmentids=[assignmentid],
            since=int(submitted_after.astimezone(self.timezone).timestamp()) if submitted_after is not None else 0,
            before=int(submitted_before.astimezone(self.timezone).timestamp()) if submitted_before is not None else 0,
        )
        for raw_assign in responce.assignments:
            assign_id = raw_assign.assignmentid
            raw_subs = raw_assign.submissions
            if not raw_subs:
                continue
            for raw_sub in raw_subs:
                sub_id = raw_sub.id
                uid = raw_sub.userid
                files = []
                for plugin in raw_sub.plugins or ():
                    if plugin.type == 'file':
                        for area in plugin.fileareas:
                            if area.area == 'submission_files':
                                for raw_file in area.files:
                                    file = SubmittedFile(
                                        submission_id=sub_id,
                                        filename=raw_file.filename,
                                        mimetype=raw_file.mimetype,
                                        filesize=raw_file.filesize,
                                        url=raw_file.fileurl,
                                        uploaded=self.timestamp2datetime(raw_file.timemodified)
                                    )
                                    files.append(file)
                s = Submission(
                    id=sub_id,
                    assignment_id=assign_id,
                    user_id=uid,
                    updated=self.timestamp2datetime(raw_sub.timemodified),
                    status=raw_sub.status,
                    files=tuple(files)
                )
                yield s


__all__ = [
    'MoodleAdapter', 'MoodleError',
    'user_id', 'course_id', 'assignment_id', 'group_id', 'role_id', 'submission_id',
    'User', 'Group', 'Role', 'Course', 'Participant', 'Assignment', 'Submission', 'SubmittedFile'
]
requires = []
provides = [MoodleAdapter]


async def lifetime(api: CoreAPI):
    """Тело модуля."""
    @dataclasses.dataclass
    class MoodleConfig:
        """Конфигурация связи с сервером Moodle."""
        base_url: str
        user: str
        pwd: str = None
        timezone: str = 'Europe/Moscow'

    log = logging.getLogger(name=f'modules.moodle')

    cfg = await api.config.load('moodle', MoodleConfig)
    moodle_instance = MoodleAdapter(cfg.base_url, cfg.user, os.getenv('MOODLE_PWD', cfg.pwd), log=log)
    moodle_instance.timezone = zoneinfo.ZoneInfo(cfg.timezone)
    async with moodle_instance:
        try:
            await moodle_instance.login()
        except Exception:
            log.error('Failed to connect to moodle instance at %s as %s',
                      moodle_instance.base_url, cfg.user, exc_info=True)
            raise
        else:
            log.info('Connected to moodle instance at %s as %s',
                     moodle_instance.base_url, cfg.user)

        api.register_api_provider(moodle_instance, MoodleAdapter)
        yield
        log.info('Disconnected from moodle instance at %s', moodle_instance.base_url)
