import typing as t
import datetime
import re

import aiohttp

from ._classes import *


__all__ = ['KSUTimetableAdapter']


class KSUTimetableAdapter:
    def __init__(self):
        self.base_url = 'https://eios-po.kosgos.ru/'
        self.session = aiohttp.ClientSession()

    async def __aenter__(self) -> t.Self:
        await self.session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.__aexit__(exc_type, exc_val, exc_tb)

    async def download_teacher_ids(self, teacher_names: list[str]) -> dict[str, int]:
        result = {}
        now = datetime.datetime.now()
        year = now.year if now.month > 7 else now.year - 1
        async with self.session.get(f'{self.base_url}api/raspTeacherlist?year={year}-{year+1}') as r:
            reply = await r.json()
        short_name_regexp = re.compile(r'^\s*(.+?)\s+(\w)\.\s*(\w)\.\s*$', re.I)
        full_name_regexp = re.compile(r'^\s*(.+?)\s+(\w)\w+\s+(\w)\w+\s*$', re.I)
        shortnames: dict[tuple, str] = {
            (m.group(1), m.group(2), m.group(3)): name
            for name, m in zip(teacher_names, map(short_name_regexp.match, teacher_names))
            if m is not None
        }
        fullname_ids: dict[tuple, int] = {
            (m.group(1), m.group(2), m.group(3)): int(itemid)
            for itemid, m in map(lambda i: (i['id'], full_name_regexp.match(i['name'])), reply['data'])
            if m is not None
        }
        for key, name in shortnames.items():
            full_id = fullname_ids.get(key, None)
            if full_id is not None:
                result[name] = full_id
        return result

    async def download_room_ids(self) -> dict[str, int]:
        async with self.session.get(f'{self.base_url}api/raspAudlist') as r:
            reply = await r.json()
        return {item['name']: int(item['id']) for item in reply['data']}

    async def download_teacher_timetable(self, teacher_id: int) -> Timetable:
        start, end, desired_semester = self._get_date_range()
        url = f'{self.base_url}api/Rasp?idTeacher={teacher_id}&sdate={start:%Y-%m-%d}&edate={end:%Y-%m-%d}'
        async with self.session.get(url) as r:
            reply = await r.json()
        data: list[dict[str, t.Any]] = reply['data']['rasp']
        timetable = self._analyze_timetable(data, desired_semester)
        return timetable

    async def download_room_timetable(self, room_id: int) -> Timetable:
        start, end, desired_semester = self._get_date_range()
        url = f'{self.base_url}api/Rasp?idAudLine={room_id}&sdate={start:%Y-%m-%d}&edate={end:%Y-%m-%d}'
        async with self.session.get(url) as r:
            reply = await r.json()
        data: list[dict[str, t.Any]] = reply['data']['rasp']
        timetable = self._analyze_timetable(data, desired_semester)
        return timetable

    @staticmethod
    def _get_date_range() -> tuple[datetime.date, datetime.date, int]:
        now: datetime.date = datetime.datetime.now().date()
        if now.weekday() == 6:
            now += datetime.timedelta(days=1)
        start_monday: datetime.date = now - datetime.timedelta(days=now.weekday())
        end_sunday: datetime.date = start_monday + datetime.timedelta(days=13)
        desired_semester = 2 if 2 <= start_monday.month <= 6 else 1
        return start_monday, end_sunday, desired_semester

    @staticmethod
    def _analyze_timetable(data: list[dict[str, t.Any]], desired_semester) -> Timetable:
        timetable = Timetable()
        for item in data:
            semester_code = int(item['код_Семестра'])
            if semester_code != desired_semester:
                continue
            week_number = int(item['типНедели'])
            lesson_week_type = week_number % 2 + 1  # 1...2
            lesson_dow_number = int(item['деньНедели'])  # 1...6
            period_number = int(item['номерЗанятия'])  # 1...N
            lesson_room = str(item['аудитория'])
            lesson_teacher = str(item['преподаватель'])
            lesson_groups = str(item['группа'])
            lesson_course = str(item['дисциплина'])
            lesson_type, lesson_course = lesson_course.split(' ', 1)
            for suffix, subgroup in Timetable.SUBGROUPS.items():
                if lesson_course.endswith(suffix):
                    lesson_course = lesson_course[:-len(suffix)]
                    lesson_groups += subgroup
                    break
            else:
                lesson_groups = Timetable.fix_groups(lesson_groups)
            lesson = Lesson(
                room=lesson_room,
                teacher=lesson_teacher,
                course=lesson_course,
                type=lesson_type,
                groups=lesson_groups
            )
            slot = timetable.slots[lesson_dow_number - 1][period_number - 1]
            if lesson_week_type == 1:
                slot.above = lesson
            else:
                slot.below = lesson
            if slot.above is not None and slot.below is not None and slot.above == slot.below:
                slot.above, slot.below, slot.both = None, None, slot.above
        return timetable
