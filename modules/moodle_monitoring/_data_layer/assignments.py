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
    await conn.execute('''INSERT INTO MoodleAssignments
    (id, course_id, name, opening, closing, cutoff) VALUES ($1, $2, $3, $4, $5, $6)
    ON CONFLICT (id) DO UPDATE SET
        name = EXCLUDED.name, opening = EXCLUDED.opening, closing = EXCLUDED.closing, cutoff = EXCLUDED.cutoff
    ''', raw_assigns)


class OpenAssignments(t.NamedTuple):
    deadline: tuple[assignment_id, ...]
    non_deadline: tuple[assignment_id, ...]


async def get_active_assignment_ids_with_deadlines(
        conn: asyncpg.Connection, now: datetime.datetime,
        before: datetime.timedelta, after: datetime.timedelta,
        with_dates_only: bool = False) -> OpenAssignments:
    nowts = ts2int(now)
    query = 'SELECT id, closing, cutoff FROM MoodleAssignments '
    if with_dates_only:
        query += 'WHERE ((closing IS NOT NULL) AND (closing > $1)) OR ((cutoff IS NOT NULL) AND (cutoff > $1))'
    else:
        query += 'WHERE ((closing IS NULL) OR (closing > $1)) AND ((cutoff IS NULL) OR (cutoff > $1))'
    deadline, non_deadline = [], []
    async with conn.cursor(query, nowts) as cursor:
        async for aid, closing, cutoff in cursor:
            closing: t.Optional[int]
            cutoff: t.Optional[int]
            if closing is not None and closing <= nowts:
                closing = None
            if cutoff is not None and cutoff <= nowts:
                cutoff = None
            assign_dl = int2ts(closing or cutoff)
            if (assign_dl is not None) and (assign_dl - before <= now <= assign_dl + after):
                deadline.append(aid)
            else:
                non_deadline.append(aid)
    return OpenAssignments(deadline=tuple(deadline), non_deadline=tuple(non_deadline))


async def load_assignments(conn: asyncpg.Connection, ids: t.Iterable[assignment_id]) -> list[Assignment]:
    query = 'SELECT id, course_id, name, opening, closing, cutoff FROM MoodleAssignments WHERE id = ANY($1::int[])'
    results = []
    async with conn.cursor(query, list(ids)) as cursor:
        async for aid, cid, name, opening, closing, cutoff in cursor:
            a = Assignment(id=aid, course_id=cid, name=name,
                           opening=int2ts(opening), closing=int2ts(closing), cutoff=int2ts(cutoff))
            results.append(a)
    return results
