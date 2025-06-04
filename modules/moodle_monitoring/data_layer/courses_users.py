import typing as t
import datetime

import asyncpg

from .moodle_classes import Course, User, Participant, Group, ts2int, int2ts


async def create_tables_courses_users(conn: asyncpg.Connection) -> None:
    """Создаёт таблицы, связанные с курсами, пользователями, их участием. группами и ролями."""
    # создаём таблицу пользователей
    await conn.execute('''CREATE TABLE IF NOT EXISTS MoodleUsers (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT NULL,
        last_seen INTEGER NOT NULL
    )''')
    # таблица курсов и связанные индексы
    await conn.execute('''CREATE TABLE IF NOT EXISTS MoodleCourses (
        id INTEGER PRIMARY KEY,
        shortname TEXT NOT NULL,
        fullname TEXT NOT NULL,
        starts INTEGER NULL,
        ends INTEGER NULL,
        last_seen INTEGER NOT NULL
    )''')
    await conn.execute('''CREATE INDEX IF NOT EXISTS MoodleCourses_Dates ON MoodleCourses(starts, ends)''')
    # участие пользователей в курсах
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
    # группы в курсах и участие пользователей в группах
    await conn.execute('''CREATE TABLE IF NOT EXISTS MoodleGroups (
        course_id INTEGER NOT NULL,
        id INTEGER NOT NULL,
        name TEXT NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY (course_id) REFERENCES MoodleCourses (id) ON DELETE CASCADE
    )''')
    await conn.execute('''CREATE TABLE IF NOT EXISTS MoodleParticipantGroups (
        user_id INTEGER NOT NULL,
        course_id INTEGER NOT NULL,
        group_id INTEGER NOT NULL,
        PRIMARY KEY (user_id, course_id, group_id),
        FOREIGN KEY (user_id, course_id) REFERENCES MoodleParticipants (user_id, course_id) ON DELETE CASCADE,
        FOREIGN KEY (group_id) REFERENCES MoodleGroups (id) ON DELETE CASCADE
    )''')
    await conn.execute('''CREATE INDEX IF NOT EXISTS MoodleParticipantGroups_Courses 
        ON MoodleParticipantGroups(course_id)
    ''')


async def store_courses(conn: asyncpg.Connection, courses: t.Collection[Course]) -> None:
    """Сохраняет указанный набор курсов в базу данных."""
    # текущая метка, чтобы помечать некоторые корневые сущности как "последний раз виденные"
    now = ts2int(datetime.datetime.now(datetime.timezone.utc))
    # заносим в базу данных новые курсы и обновляем существующие
    coursedata = [
        (c.id, c.shortname, c.fullname,
         int(c.starts.timestamp()) if c.starts else None,
         int(c.ends.timestamp()) if c.ends else None,
         now)
        for c in courses
    ]
    await conn.executemany('''INSERT INTO MoodleCourses 
    (id, shortname, fullname, starts, ends, last_seen) VALUES ($1, $2, $3, $4, $5, $6) 
    ON CONFLICT (id) DO UPDATE SET 
        shortname = EXCLUDED.shortname, fullname = EXCLUDED.fullname,
        starts = EXCLUDED.starts, ends = EXCLUDED.ends,
        last_seen = EXCLUDED.last_seen
    ''', coursedata)
    del coursedata
    # заносим в базу данные новых пользователей или обновляем существующих
    userdata = list(set([
        (p.user.id, p.user.name, p.user.email, now)
        for c in courses for p in (c.students + c.teachers)
    ]))
    await conn.executemany('''INSERT INTO MoodleUsers 
    (id, name, email, last_seen) VALUES ($1, $2, $3, $4) 
    ON CONFLICT (id) DO UPDATE SET 
        name = EXCLUDED.name, email = EXCLUDED.email,
        last_seen = EXCLUDED.last_seen
    ''', userdata)
    del userdata
    # находим в обрабатываемых курсах группы, которые были удалены, и удаляем их из базы
    composed_groups = [
        (c.id, list(set(g.id for u in (c.students + c.teachers) for g in u.groups)))
        for c in courses
    ]
    await conn.executemany(
        '''DELETE FROM MoodleGroups WHERE course_id = $1 AND NOT (id = ANY($2::int[]))''',
        composed_groups)
    del composed_groups
    # добавляем/обновляем остальные группы
    groups = list(set([
        (c.id, g.id, g.name)
        for c in courses for u in (c.students + c.teachers) for g in u.groups
    ]))
    await conn.executemany('''INSERT INTO MoodleGroups
    (course_id, id, name) VALUES ($1, $2, $3)
    ON CONFLICT (id) DO UPDATE SET
        name = EXCLUDED.name
    ''', groups)
    del groups
    # удаляем из курсов тех участников, которые более не присутствуют в списке
    composed_users = [
        (c.id, [u.user.id for u in (c.students+c.teachers)])
        for c in courses
    ]
    await conn.executemany(
        '''DELETE FROM MoodleParticipants WHERE course_id = $1 AND NOT (user_id = ANY($2::int[]))''',
        composed_users
    )
    del composed_users
    # добавляем/обновляем существующих участников курсов
    participation_data = [(u.user.id, c.id, 0) for c in courses for u in c.students]
    participation_data.extend((u.user.id, c.id, 1) for c in courses for u in c.teachers)
    await conn.executemany('''INSERT INTO MoodleParticipants
    (user_id, course_id, is_teacher) VALUES ($1, $2, $3)
    ON CONFLICT (user_id, course_id) DO UPDATE SET
        is_teacher = EXCLUDED.is_teacher
    ''', participation_data)
    del participation_data
    # добавляем/обновляем группы, которые упоминаются в курсах
    # Не упомянутые группы уже были удалены выше, что спровоцировало каскадное удаление
    part_groups_data = [(c.id, u.user.id, g.id) for c in courses for u in (c.students + c.teachers) for g in u.groups]
    await conn.executemany('''INSERT INTO MoodleParticipantGroups
    (user_id, course_id, group_id) VALUES ($1, $2, $3)
    ON CONFLICT (user_id, course_id, group_id) DO NOTHING
    ''', part_groups_data)
    del part_groups_data


async def get_open_course_ids(conn: asyncpg.Connection, with_dates_only: bool = False) -> list[int]:
    now = ts2int(datetime.datetime.now(datetime.timezone.utc))
    query = 'SELECT (id) FROM MoodleCourses '
    if with_dates_only:
        query += 'WHERE ((starts IS NOT NULL) AND (starts >= $1::int)) AND ((ends IS NOT NULL) AND (ends <= $1::int))'
    else:
        query += 'WHERE ((starts IS NULL) OR (starts >= $1::int)) AND ((ends IS NULL) OR (ends <= $1::int))'
    async with conn.cursor(query, now) as cursor:
        rows = [cid async for (cid,) in cursor]
    return rows


async def load_courses(conn: asyncpg.Connection, ids: t.Iterable[int]) -> list[Course]:
    """Загружает из базы данных указанный набор курсов."""
    now = ts2int(datetime.datetime.now(datetime.timezone.utc))
    args = [now]
    query = 'SELECT (id, shortname, fullname, starts, ends) FROM MoodleCourses'
    query += ' AND (id = ANY($2::int[]))'
    args.append(list(ids))
    course_cursor = conn.cursor(query, *args)
    async with course_cursor:
        course_rows: list[tuple[int, str, str, int | None, int | None]] = [row async for row in course_cursor]
    course_ids = [row[0] for row in course_rows]
    participant_cursor = conn.cursor('''SELECT (
        MoodleParticipants.user_id, MoodleParticipants.course_id, MoodleParticipants.is_teacher,
        MoodleUsers.name, MoodleUsers.email
        ) FROM MoodleParticipants
    INNER JOIN MoodleUsers ON (MoodleUsers.id = MoodleParticipants.user_id)
    WHERE course_id = ANY($1::int[])''', course_ids)
    raw_courses: t.MutableMapping[int, dict] = {cid: {} for cid in course_ids}
    async with participant_cursor:
        async for uid, cid, is_teacher, name, email in participant_cursor:
            raw_courses[cid][uid] = (name, email, is_teacher, [])

    group_cursor = conn.cursor('''SELECT (
        MoodleParticipants.user_id, MoodleParticipants.course_id,
        MoodleGroups.id, MoodleGroups.name
        ) FROM MoodleParticipants
    INNER JOIN MoodleParticipantGroups ON (
        (MoodleParticipantGroups.course_id = MoodleParticipants.course_id) AND
        (MoodleParticipantGroups.user_id = MoodleParticipants.user_id)
        )
    INNER JOIN MoodleGroups ON (MoodleGroups.id = MoodleParticipantGroups.group_id)
    WHERE course_id = ANY($1::int[])''', course_ids)
    async with group_cursor:
        async for uid, cid, gid, gname in group_cursor:
            raw_courses[cid][uid][3].append((gid, gname))

    courses = []
    for cid, shortname, fullname, starts, ends in course_rows:
        raw_users = raw_courses.get(cid, {})
        students, teachers = [], []
        for uid, (name, email, is_teacher, raw_groups) in raw_users.items():
            u = User(id=uid, name=name, email=email)
            groups = [Group(gid, name) for gid, name in raw_groups]
            p = Participant(user=u, groups=tuple(groups))
            if is_teacher:
                teachers.append(p)
            else:
                students.append(p)
        c = Course(
            id=cid,
            shortname=shortname, fullname=fullname,
            starts=int2ts(starts),
            ends=int2ts(ends),
            teachers=tuple(teachers),
            students=tuple(students)
        )
        courses.append(c)
    return courses
