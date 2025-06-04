import datetime
import typing as t

import asyncpg

from .moodle_classes import Assignment, ts2int, int2ts


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


async def get_active_assignment_ids_with_deadlines(conn: asyncpg.Connection, with_dates_only: bool = False
                                                   ) -> dict[int, t.Optional[datetime.datetime]]:
    now = ts2int(datetime.datetime.now(datetime.timezone.utc))
    query = 'SELECT (id, closing, cutoff) FROM MoodleAssignments '
    if with_dates_only:
        query += 'WHERE ((closing IS NOT NULL) AND (closing > $1)) OR ((cutoff IS NOT NULL) AND (cutoff > $1))'
    else:
        query += 'WHERE ((closing IS NULL) OR (closing > $1)) AND ((cutoff IS NULL) OR (cutoff > $1))'
    results = {}
    async with conn.cursor(query, now) as cursor:
        async for aid, closing, cutoff in cursor:
            if closing is not None and closing <= now:
                closing = None
            if cutoff is not None and cutoff <= now:
                cutoff = None
            results[aid] = int2ts(closing or cutoff)
    return results


async def load_assignments(conn: asyncpg.Connection, ids: t.Iterable[int]) -> list[Assignment]:
    query = 'SELECT (id, course_id, name, opening, closing, cutoff) FROM MoodleAssignments WHERE id = ANY($1::int[])'
    results = []
    async with conn.cursor(query, list(ids)) as cursor:
        async for aid, cid, name, opening, closing, cutoff in cursor:
            a = Assignment(id=aid, course_id=cid, name=name,
                           opening=int2ts(opening), closing=int2ts(closing), cutoff=int2ts(cutoff))
            results.append(a)
    return results
