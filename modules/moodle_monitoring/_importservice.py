import typing as t
import datetime
import zoneinfo

import asyncpg

from modules.moodle import Moodle

from ._config import MoodleMonitorConfig
from .data_layer import *


__all__ = ['ImportService']


class ImportService:
    """Занимается загрузкой сведений из инстанса Moodle и их сохранением в базу данных."""
    def __init__(self, cfg: MoodleMonitorConfig, m: Moodle, conn: asyncpg.Connection):
        self.cfg = cfg
        self.moodle = m
        self.conn = conn
        self.servertz = zoneinfo.ZoneInfo(self.cfg.server_timezone)

    def get_datetime(self, item: dict[str, t.Any], key: str) -> t.Optional[datetime.datetime]:
        value: t.Optional[int] = item.get(key, None)
        return datetime.datetime.fromtimestamp(value, self.servertz).astimezone(datetime.timezone.utc) \
            if value is not None else None

    async def stream_available_courses(self) -> t.AsyncIterable[Course]:
        offset, limit = 0, self.cfg.courses.chunk_size
        while True:
            raw_course_data = await self.moodle.function \
                .core_course_get_enrolled_courses_by_timeline_classification(
                    classification='inprogress' if self.cfg.courses.load_inprogress_only else 'all',
                    offset=offset, limit=limit)
            raw_courses = raw_course_data.get('courses', [])
            if not raw_courses:
                break
            offset = raw_course_data['nextoffset']
            for item in raw_courses:
                starts = self.get_datetime(item, 'startdate')
                ends = self.get_datetime(item, 'enddate')
                if self.cfg.courses.ignore_no_ending_date and ends is None:
                    continue
                cid = item['id']
                teachers = [p async for p in self.stream_users_with_cap(cid, self.cfg.courses.teachers_have_capability)]
                all_users = [p async for p in self.stream_users_with_cap(cid)]
                students = [u for u in all_users if u not in teachers]
                c = Course(id=cid, shortname=item['shortname'], fullname=item['fullname'],
                           starts=starts, ends=ends, students=tuple(students), teachers=tuple(teachers))
                yield c

    async def stream_users_with_cap(self,
                                    course_id: int, user_capability: str = ''
                                    ) -> t.AsyncIterable[Participant]:
        options = [
            {'name': 'userfields', 'value': 'id, fullname, email, roles, groups'}
        ]
        if user_capability:
            options.append({'name': 'withcapability', 'value': user_capability})
        offset, limit = 0, self.cfg.participants.chunk_size
        while True:
            limits = [
                {'name': 'limitfrom', 'value': offset},
                {'name': 'limitnumber', 'value': limit},
            ]
            raw_users = await self.moodle.function.get_enrolled_users_with_capability(
                courseid=course_id, options=options + limits
            )
            if not raw_users:
                break
            offset += len(raw_users)
            for raw_user in raw_users:
                p = Participant(
                    user=User(id=raw_user['id'], name=raw_user['fullname'], email=raw_user['email']),
                    groups=tuple([Group(id=g['id'], name=g['name']) for g in raw_user['groups']])
                )
                yield p

    async def stream_assignments(self, course_ids: t.Iterable[int]) -> t.AsyncIterable[Assignment]:
        response = await self.moodle.function.mod_assign_get_assignments(
            key='courses', courseids=list(course_ids), includenotenrolledcourses=0
        )
        for course in response['courses']:
            raw_assigns = course['assignments']
            if not raw_assigns:
                continue
            for raw_assign in raw_assigns:
                a = Assignment(
                    id=raw_assign['id'],
                    name=raw_assign['name'],
                    course_id=raw_assign['course'],
                    opening=self.get_datetime(raw_assign, 'allowsubmissionsfromdate'),
                    closing=self.get_datetime(raw_assign, 'duedate'),
                    cutoff=self.get_datetime(raw_assign, 'cutoffdate')
                )
                yield a

    async def stream_submissions(self, assignment_id: int, submitted_after: datetime.datetime
                                 ) -> t.AsyncIterable[Submission]:
        responce = await self.moodle.function.mod_assign_get_submissions(
            assignmentids=[assignment_id],
            since=submitted_after
        )
        for raw_assign in responce['assignments']:
            assign_id = raw_assign['assignmentid']
            raw_subs = raw_assign.get('submissions', [])
            if not raw_subs:
                continue
            for raw_sub in raw_subs:
                sub_id = raw_sub['id']
                user_id = raw_sub['userid']
                files = []
                for plugin in raw_sub.get('plugins', []):
                    if plugin['type'] == 'file':
                        for area in plugin['fileareas']:
                            if area['area'] == 'submission_files':
                                for raw_file in area['files']:
                                    file = SubmittedFile(
                                        submission_id=sub_id,
                                        filename=raw_file['filename'],
                                        mimetype=raw_file['mimetype'],
                                        filesize=raw_file['filesize'],
                                        url=raw_file['fileurl'],
                                        uploaded=self.get_datetime(raw_file, 'timemodified')
                                    )
                                    files.append(file)
                s = Submission(
                    id=sub_id,
                    assignment_id=assign_id,
                    user_id=user_id,
                    updated=self.get_datetime(raw_sub, 'timemodified'),
                    files=tuple(files)
                )
                yield s
