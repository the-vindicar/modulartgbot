import dataclasses
import typing as t

import asyncpg


@dataclasses.dataclass(frozen=True)
class User:
    lastname: str
    firstname: str
    patronym: str
    fields: t.Mapping[str, str]
    id: int | None = None


async def create_tables(conn: asyncpg.Connection) -> None:
    await conn.execute('''CREATE TABLE IF NOT EXISTS Users (
        id SERIAL PRIMARY KEY,
        lastname TEXT NOT NULL,
        firstname TEXT NOT NULL,
        patronym TEXT NOT NULL
    )''')
    await conn.execute('''CREATE TABLE IF NOT EXISTS UserFieldTypes (
        type TEXT PRIMARY KEY,
        description TEXT NOT NULL
    )''')
    await conn.execute('''CREATE TABLE IF NOT EXISTS UserFields (
        user_id INT, 
        field_type TEXT,
        value TEXT,
        PRIMARY KEY (user_id, field_type),
        FOREIGN KEY (user_id) REFERENCES Users(id) ON DELETE CASCADE,
        FOREIGN KEY (field_type) REFERENCES UserFieldTypes(type) ON DELETE CASCADE
    )''')


async def register_user_field_type(conn: asyncpg.Connection, typename: str, description: str) -> None:
    await conn.execute('''INSERT INTO UserFieldTypes (type, description) VALUES ($1, $2)
    ON CONFLICT (type) DO UPDATE SET description = EXCLUDED.descrtiption''', typename, description)


async def unregister_user_field_type(conn: asyncpg.Connection, typename: str) -> None:
    await conn.execute('''DELETE FROM UserFieldTypes WHERE type = $1''', typename)


async def store_user(conn: asyncpg.Connection, user: User) -> User:
    if user.id is None:
        userid = await conn.fetchval('''INSERT INTO Users 
            (lastname, firstname, patronym) VALUES ($1, $2, $3) 
            RETURNING id''', user.lastname, user.firstname, user.patronym)
    else:
        userid = user.id
        await conn.execute('''UPDATE Users SET
                lastname = $2, firstname = $3, patronym = $4
                WHERE id = $1
            ''', user.id, user.lastname, user.firstname, user.patronym)
    if user.fields:
        await conn.executemany('''INSERT INTO UserFields
            (user_id, field_type, value) VALUES ($1, $2, $3)
            ON CONFLICT (user_id, field_type) DO UPDATE SET value = EXCLUDED.value
            ''', [(userid, ftype, fvalue) for ftype, fvalue in user.fields.items()])
    return dataclasses.replace(user, id=userid) if user.id is None else user


async def load_user(conn: asyncpg.Connection, userid: int) -> User | None:
    userrow = await conn.fetchrow('''SELECT lastname, firstname, patronym FROM Users WHERE id = $1''', userid)
    if userrow is None:
        return None
    lastname, firstname, patronym = userrow
    cursor = conn.cursor('''SELECT field_type, value FROM UserFields WHERE id = $1''', userid)
    data = {ftype: fvalue async for ftype, fvalue in cursor}
    return User(id=userid, lastname=lastname, firstname=firstname, patronym=patronym, fields=data)
