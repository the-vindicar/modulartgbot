import datetime
import typing as t

import asyncpg

from modules.moodle import Submission, SubmittedFile, assignment_id
from .utils import int2ts, ts2int


async def create_tables_submissions(conn: asyncpg.Connection) -> None:
    """Создаёт таблицы для базы данных."""
    await conn.execute('''CREATE TABLE IF NOT EXISTS MoodleSubmissions (
        id INTEGER PRIMARY KEY,
        assignment_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        updated INTEGER NOT NULL,
        FOREIGN KEY (user_id) REFERENCES MoodleUsers (id) ON DELETE CASCADE,
        FOREIGN KEY (assignment_id) REFERENCES MoodleAssignments (id) ON DELETE CASCADE
    )''')
    await conn.execute('''CREATE INDEX IF NOT EXISTS MoodleSubmissions_Assignment 
        ON MoodleSubmissions(assignment_id)
    ''')
    await conn.execute('''CREATE INDEX IF NOT EXISTS MoodleSubmissions_Updated ON MoodleSubmissions(updated)''')

    await conn.execute('''CREATE TABLE IF NOT EXISTS MoodleFiles (
        id SERIAL,
        submission_id INTEGER NOT NULL,
        assignment_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        filesize INTEGER NOT NULL,
        mimetype TEXT NOT NULL,
        url TEXT NOT NULL,
        uploaded INTEGER NOT NULL,
        PRIMARY KEY (submission_id, filename),
        FOREIGN KEY (submission_id) REFERENCES MoodleSubmissions (id) ON DELETE CASCADE
    )''')
    await conn.execute('''CREATE INDEX IF NOT EXISTS MoodleFiles_Assignment ON MoodleFiles(assignment_id)''')
    await conn.execute('''CREATE INDEX IF NOT EXISTS MoodleFiles_Uploaded ON MoodleFiles(uploaded)''')


async def store_submissions(conn: asyncpg.Connection,
                            submissions: t.Collection[Submission]) -> None:
    raw_subs = [
        (s.id, s.assignment_id, s.user_id, ts2int(s.updated))
        for s in submissions
    ]
    await conn.executemany('''INSERT INTO MoodleSubmissions
    (id, assignment_id, user_id, updated) VALUES ($1, $2, $3, $4)
    ON CONFLICT (id) DO UPDATE SET
        updated = EXCLUDED.updated
    ''', raw_subs)
    del raw_subs
    raw_files = [
        (f.submission_id, s.assignment_id, s.user_id, f.filename, f.filesize, f.mimetype, f.url, ts2int(f.uploaded))
        for s in submissions for f in s.files
    ]
    await conn.executemany('''INSERT INTO MoodleFiles 
    (submission_id, assignment_id, user_id, filename, filesize, mimetype, url, uploaded) 
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
    ON CONFLICT (submission_id, filename) DO UPDATE SET
        filesize = EXCLUDED.filesize, mimetype = EXCLUDED.mimetype,
        url = EXCLUDED.url, uploaded = EXCLUDED.uploaded
    ''', raw_files)
    del raw_files


async def load_submissions_after(conn: asyncpg.Connection,
                                 assign_id: assignment_id, after: datetime.datetime) -> list[Submission]:
    query = '''SELECT id, assignment_id, user_id, updated FROM MoodleSubmissions
    WHERE (assignment_id = $1) AND (updated > $2)'''

    async with conn.cursor(query, assign_id, ts2int(after)) as cursor:
        raw_subs = {}
        async for sub_id, assign_id, user_id, updated in cursor:
            raw_subs[sub_id] = (assign_id, user_id, updated, [])

    query = '''SELECT submission_id, filename, filesize, mimetype, url, uploaded
    FROM MoodleFiles WHERE assignment_id = $1 AND submission_id = ANY($2::int[])'''
    async with conn.cursor(query, assign_id, list(raw_subs.keys())) as cursor:
        async for (sub_id, filename, filesize, mimetype, url, uploaded) in cursor:
            sf = SubmittedFile(submission_id=sub_id, url=url, uploaded=uploaded,
                               filename=filename, filesize=filesize, mimetype=mimetype)
            raw_subs[sub_id][3].append(sf)
    result = [
        Submission(id=sub_id, assignment_id=assign_id, user_id=user_id, updated=updated, files=tuple(files))
        for sub_id, (assign_id, user_id, updated, files) in raw_subs.items()
    ]
    return result


async def get_last_submission_times(conn: asyncpg.Connection,
                                    assignment_ids: t.Collection[assignment_id]
                                    ) -> dict[assignment_id, t.Optional[datetime.datetime]]:
    result = {aid: None for aid in assignment_ids}
    query = '''SELECT assignment_id, MAX(updated) FROM MoodleSubmissions
    WHERE assignment_id = ANY($1::int[]) GROUP BY assignment_id'''
    async with conn.cursor(query, list(assignment_ids)) as cursor:
        async for aid, upd in cursor:
            result[aid] = int2ts(upd)
    return result
