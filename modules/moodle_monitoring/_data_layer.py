import datetime

import asyncpg
from ._moodle_classes import *


__all__ = [
    'create_tables', 'clear_old_data'
]


async def create_tables(conn: asyncpg.Connection) -> None:
    """Создаёт таблицы для базы данных."""
    await conn.execute('''CREATE TABLE IF NOT EXISTS MoodleUsers (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT NULL,
        last_seen TIMESTAMP NOT NULL
    )''')

    await conn.execute('''CREATE TABLE IF NOT EXISTS MoodleCourses (
        id INTEGER PRIMARY KEY,
        shortname TEXT NOT NULL,
        longname TEXT NOT NULL,
        starts TIMESTAMP NULL,
        ends TIMESTAMP NULL
    )''')
    await conn.execute('''CREATE INDEX IF NOT EXISTS MoodleCourses_Dates ON MoodleCourses(starts, ends)''')

    await conn.execute('''CREATE TABLE IF NOT EXISTS MoodleParticipants (
        user_id INTEGER NOT NULL,
        course_id INTEGER NOT NULL,
        is_teacher INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, course_id),
        FOREIGN KEY (user_id) REFERENCES MoodleUsers (id) ON DELETE CASCADE,
        FOREIGN KEY (course_id) REFERENCES MoodleCourses (id) ON DELETE CASCADE
    )''')
    await conn.execute('''CREATE INDEX IF NOT EXISTS MoodleParticipants_Courses 
        ON MoodleParticipants(course_id)
    ''')

    await conn.execute('''CREATE TABLE IF NOT EXISTS MoodleAssignments (
        id INTEGER PRIMARY KEY,
        course_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        opening TIMESTAMP NULL,
        closing TIMESTAMP NULL,
        cutoff TIMESTAMP NULL,
        FOREIGN KEY (course_id) REFERENCES MoodleCourses (id) ON DELETE CASCADE
    )''')
    await conn.execute('''CREATE INDEX IF NOT EXISTS MoodleAssignments_Closing ON MoodleAssignments(closing)''')
    await conn.execute('''CREATE INDEX IF NOT EXISTS MoodleAssignments_Cutoff ON MoodleAssignments(cutoff)''')

    await conn.execute('''CREATE TABLE IF NOT EXISTS MoodleSubmissions (
        id INTEGER PRIMARY KEY,
        assignment_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        updated TIMESTAMP NOT NULL,
        FOREIGN KEY (user_id) REFERENCES MoodleUsers (id) ON DELETE CASCADE,
        FOREIGN KEY (assignment_id) REFERENCES MoodleAssignments (id) ON DELETE CASCADE
    )''')
    await conn.execute('''CREATE INDEX IF NOT EXISTS MoodleSubmissions_Assignment 
        ON MoodleSubmissions(assignment_id)
    ''')
    await conn.execute('''CREATE INDEX IF NOT EXISTS MoodleSubmissions_Updated ON MoodleSubmissions(updated)''')

    await conn.execute('''CREATE TABLE IF NOT EXISTS MoodleFiles (
        id SERIAL PRIMARY KEY,
        submission_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        filesize INTEGER NOT NULL,
        mimetype TEXT NOT NULL,
        url TEXT NOT NULL,
        updated TIMESTAMP NOT NULL,
        FOREIGN KEY (submission_id) REFERENCES MoodleSubmissions (id) ON DELETE CASCADE
    )''')
    await conn.execute('''CREATE INDEX IF NOT EXISTS MoodleFiles_Submission ON MoodleFiles(submission_id)''')
    await conn.execute('''CREATE INDEX IF NOT EXISTS MoodleFiles_Updated ON MoodleFiles(updated)''')


async def clear_old_data(conn: asyncpg.Connection, cutoff: datetime.datetime) -> None:
    ts = cutoff.timestamp()
    await conn.execute('''DELETE FROM MoodleUsers WHERE last_seen <= $1''', ts)
    await conn.execute('''DELETE FROM MoodleCourses WHERE (ends IS NOT NULL) AND (ends <= $1)''', ts)
