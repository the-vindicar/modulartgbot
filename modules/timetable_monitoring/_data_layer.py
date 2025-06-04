import datetime
import typing as t
import logging

import asyncpg

from ._classes import *


__all__ = [
    'create_tables',
    'store_teacher_timetable', 'load_teacher_timetable',
    'store_room_timetable', 'load_room_timetable',
    'load_update_timestamps', 'bump_update_timestamp'
]


async def create_tables(conn: asyncpg.Connection, log: logging.Logger) -> None:
    try:
        await conn.execute('''CREATE TABLE IF NOT EXISTS TeacherTimetableCache(
            week INTEGER NOT NULL,
            day INTEGER NOT NULL,
            period INTEGER NOT NULL,
            teacher TEXT NOT NULL,
            room TEXT NOT NULL,
            course TEXT NOT NULL,
            course_type TEXT NOT NULL,
            groups TEXT NOT NULL,
            PRIMARY KEY (teacher, day, period, week)
            )''')

        await conn.execute('''CREATE INDEX IF NOT EXISTS TeacherTimetableCache_Teachers 
            ON TeacherTimetableCache(teacher)''')

        await conn.execute('''CREATE TABLE IF NOT EXISTS RoomTimetableCache(
            week INTEGER NOT NULL,
            day INTEGER NOT NULL,
            period INTEGER NOT NULL,
            teacher TEXT NOT NULL,
            room TEXT NOT NULL,
            course TEXT NOT NULL,
            course_type TEXT NOT NULL,
            groups TEXT NOT NULL,
            PRIMARY KEY (room, day, period, week)
            )''')

        await conn.execute('''CREATE INDEX IF NOT EXISTS RoomTimetableCache_Rooms 
            ON RoomTimetableCache(room)''')

        await conn.execute('''CREATE TABLE IF NOT EXISTS TeacherUpdateTimes(
            teacher TEXT PRIMARY KEY,
            update_timestamp INTEGER NOT NULL
        )''')
    except Exception:
        log.critical('Failed to create tables!', exc_info=True)
    else:
        log.debug('Tables created successfully.')


async def store_teacher_timetable(conn: asyncpg.Connection, teacher: str, timetable: Timetable) -> None:
    data = [
        (week, day, period, teacher, lesson.room, lesson.course, lesson.type, lesson.groups)
        for day, period, week, lesson in timetable.iterate()
    ]
    await conn.execute('''DELETE FROM TeacherTimetableCache WHERE (teacher = $1)''', teacher)
    await conn.executemany('''INSERT INTO TeacherTimetableCache(
        week, day, period, teacher, room, course, course_type, groups
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)''', data)


async def load_teacher_timetable(conn: asyncpg.Connection, teacher: str) -> Timetable:
    timetable = Timetable()
    total_lines = 0
    cursor = conn.cursor('''SELECT week, day, period, room, course, course_type, groups 
    FROM TeacherTimetableCache WHERE (teacher = $1)''', teacher)
    async with cursor:
        async for week, day, period, room, course, ltype, groups in cursor:
            total_lines += 1
            slot = timetable.slots[day][period]
            lesson = Lesson(room=room, teacher=teacher, course=course, type=ltype, groups=groups)
            if week == 1:
                slot.above = lesson
            elif week == 2:
                slot.below = lesson
            else:
                slot.both = lesson
    return timetable


async def store_room_timetable(conn: asyncpg.Connection, room: str, timetable: Timetable) -> None:
    data = [
        (week, day, period, room, lesson.teacher, lesson.course, lesson.type, lesson.groups)
        for day, period, week, lesson in timetable.iterate()
    ]
    await conn.execute('''DELETE FROM RoomTimetableCache WHERE (room = $1)''', room)
    await conn.executemany('''INSERT INTO RoomTimetableCache(
        week, day, period, room, teacher, course, course_type, groups
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)''', data)


async def load_room_timetable(conn: asyncpg.Connection, room: str) -> t.Optional[Timetable]:
    timetable = Timetable()
    total_lines = 0
    cursor = conn.cursor('''SELECT week, day, period, teacher, course, course_type, groups 
    FROM RoomTimetableCache WHERE (room = $1)''', room)
    async with cursor:
        async for week, day, period, teacher, course, ltype, groups in cursor:
            total_lines += 1
            slot = timetable.slots[day][period]
            lesson = Lesson(room=room, teacher=teacher, course=course, type=ltype, groups=groups)
            if week == 1:
                slot.above = lesson
            elif week == 2:
                slot.below = lesson
            else:
                slot.both = lesson
    return timetable  # if total_lines > 0 else None


async def load_update_timestamps(conn: asyncpg.Connection) -> dict[str, datetime.datetime]:
    result = {}
    cursor = conn.cursor('''SELECT teacher, update_timestamp FROM TeacherUpdateTimes''')
    async with cursor:
        async for teacher, timestamp in cursor:
            result[teacher] = datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc)
    return result


async def bump_update_timestamp(conn: asyncpg.Connection, teacher: str, timestamp: datetime.datetime) -> None:
    await conn.execute(
        '''INSERT INTO TeacherUpdateTimes(teacher, update_timestamp)
        VALUES ($1, $2) ON CONFLICT (teacher) DO UPDATE SET update_timestamp = EXCLUDED.update_timestamp''',
        teacher, int(timestamp.astimezone(datetime.timezone.utc).timestamp())
    )