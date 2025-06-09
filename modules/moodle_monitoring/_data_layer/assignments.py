import typing as t
import logging
import datetime

import asyncpg

from modules.moodle import assignment_id, Assignment
from .utils import ts2int, int2ts


log = logging.getLogger('modules.moodlemon.assignments')


async def create_tables_assignments(conn: asyncpg.Connection) -> None:
    await conn.execute('''CREATE TABLE IF NOT EXISTS MoodleAssignments (
        id INTEGER PRIMARY KEY,
        course_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        opening INTEGER NULL,
        closing INTEGER NULL,
        cutoff INTEGER NULL,
        FOREIGN KEY (course_id) REFERENCES MoodleCourses (id) ON DELETE CASCADE
    )''')
    await conn.execute('''CREATE INDEX IF NOT EXISTS MoodleAssignments_Opening ON MoodleAssignments(opening)''')
    await conn.execute('''CREATE INDEX IF NOT EXISTS MoodleAssignments_Closing ON MoodleAssignments(closing)''')
    await conn.execute('''CREATE INDEX IF NOT EXISTS MoodleAssignments_Cutoff ON MoodleAssignments(cutoff)''')


async def store_assignments(conn: asyncpg.Connection, assignments: t.Collection[Assignment]) -> None:
    raw_assigns = [
        (a.id, a.course_id, a.name, ts2int(a.opening), ts2int(a.closing), ts2int(a.cutoff))
        for a in assignments
    ]
    await conn.executemany('''INSERT INTO MoodleAssignments
    (id, course_id, name, opening, closing, cutoff) VALUES ($1, $2, $3, $4, $5, $6)
    ON CONFLICT (id) DO UPDATE SET
        name = EXCLUDED.name, opening = EXCLUDED.opening, closing = EXCLUDED.closing, cutoff = EXCLUDED.cutoff
    ''', raw_assigns)


async def get_active_assignments_ending_soon(
        conn: asyncpg.Connection,
        now: datetime.datetime, before: datetime.timedelta, after: datetime.timedelta) -> list[assignment_id]:
    """Загружает все индентификаторы заданий (assignment), которые скоро завершаются.
    Под "завершаются" понимается либо ожидаемый срок сдачи задания (проверяемый интервал `now-before...now+after`),
    либо срок полного закрытия задания (проверяемый интервал `now-before...now+after`).
    Как минимум один из этих сроков должен быть указан для задания.
    :param conn: Соединение с БД
    :param now: Какой момент времени считается "сейчас".
    :param before: За какой интервал времени до завершения задания оно считается "скоро завершающимся".
    :param after: В какой интервал времени после срока сдачи задания оно считается "скоро завершающимся".
    :return: Список идентификаторов заданий.
    """
    beforets = ts2int(now - before)
    afterts = ts2int(now + after)
    nowts = ts2int(now)
    query = '''SELECT id FROM MoodleAssignments WHERE 
    ((closing IS NOT NULL) OR (cutoff IS NOT NULL)) AND 
    ((opening IS NULL) OR (opening <= $3)) AND
    ((closing is NULL) OR ((closing >= $1) AND (closing <= $2))) AND 
    ((cutoff is NULL) OR ((cutoff >= $1) AND (cutoff <= $2))) 
    '''
    cursor = conn.cursor(query, beforets, afterts, nowts)
    deadline = [aid async for (aid,) in cursor]
    return deadline


async def get_active_assignments_ending_later(
        conn: asyncpg.Connection,
        now: datetime.datetime, before: datetime.timedelta, after: datetime.timedelta) -> list[assignment_id]:
    """Загружает все идентификаторы заданий (assignment), которые открыты, но завершаются НЕ в ближайшее время.
    Под "завершаются" понимается либо ожидаемый срок сдачи задания (проверяемый интервал `now-before...now+after`),
    либо срок полного закрытия задания (проверяемый интервал `now-before...now+after`).
    Если у задания не указан срок открытия, то оно считается открытым.
    :param conn: Соединение с БД
    :param now: Какой момент времени считается "сейчас".
    :param before: За какой интервал времени до завершения задания оно считается "скоро завершающимся".
    :param after: В какой интервал времени после срока сдачи задания оно считается "скоро завершающимся".
    :return: Список идентификаторов заданий.
    """
    beforets = ts2int(now - before)
    afterts = ts2int(now + after)
    nowts = ts2int(now)

    query = '''SELECT id FROM MoodleAssignments WHERE
    ((opening IS NULL) OR (opening <= $3)) AND
    ((closing IS NULL) OR (closing > $2) OR (closing < $1)) AND 
    ((cutoff IS NULL) OR (cutoff > $2))
    '''
    cursor = conn.cursor(query, beforets, afterts, nowts)
    active = [aid async for (aid,) in cursor]
    return active


async def load_assignments(conn: asyncpg.Connection, ids: t.Iterable[assignment_id]) -> list[Assignment]:
    query = 'SELECT id, course_id, name, opening, closing, cutoff FROM MoodleAssignments WHERE id = ANY($1::int[])'
    results = []
    cursor = conn.cursor(query, list(ids))
    async for aid, cid, name, opening, closing, cutoff in cursor:
        a = Assignment(id=aid, course_id=cid, name=name,
                       opening=int2ts(opening), closing=int2ts(closing), cutoff=int2ts(cutoff))
        results.append(a)
    return results
