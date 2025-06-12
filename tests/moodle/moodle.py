import asyncio
from modules.moodle import *


async def main():
    m = MoodleAdapter('https://sdo.kosgos.ru', input('Username: '), input('Password: '))
    async with m:
        await m.login()
        async for c in m.stream_enrolled_courses(True, [role_id(3)]):
            print(f'[{c.id}] {c.fullname} ({len(c.teachers)} teachers, {len(c.students)} students)')


if __name__ == '__main__':
    asyncio.run(main())
