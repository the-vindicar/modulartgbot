import asyncio
from modules.moodle.moodle import *


async def main():
    m = Moodle('https://sdo.kosgos.ru', input('Username: '), input('Password: '))
    async with m:
        await m.login()

        cs = await m.function.core_course_get_enrolled_courses_by_timeline_classification(
            classification=CourseTimelineClassification.ALL,
            offset=0, limit=50
        )
        for c in cs.courses:
            print(f'[{c.id}] {c.fullname}')


if __name__ == '__main__':
    asyncio.run(main())
