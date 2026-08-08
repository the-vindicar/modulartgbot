import asyncio
from collections import defaultdict
import datetime
import logging
from pprint import pprint
from modules.moodle.moodle import *


async def main():
    logging.basicConfig(stream=None)
    m = Moodle('https://sdo.kosgos.ru', input('Username: '), input('Password: '))
    async with m:
        await m.login()
        await test_site_info(m)
        # await test_course_contents(m, 683)
        # await test_attendance(m, 683)


async def test_attendance(m: Moodle, courseid: int):
    sections = await m.function.core_course.get_course_contents(courseid, modname='attendance')
    for s in sections:
        if s.modules:
            mod = s.modules[0]
            break
    else:
        raise RuntimeError(f'No attendance module in course {courseid}')
    print(mod)

    sessions = await m.function.mod_attendance.get_sessions(mod.instance)
    for s in sessions:
        print(m.timestamp2datetime(s.sessdate), s.description)


async def test_course_contents(m: Moodle, courseid: int):
    sections = await m.function.core_course.get_course_contents(courseid)
    for s in sections:
        print(f'#{s.section} {s.name}: {s.summary}')
        for mod in s.modules:
            print(f'    {mod.modname} #{mod.id}: {mod.name} ({mod.contextid}, {mod.instance})')
            if mod.availability:
                print(f'        {mod.availability_conditions}')


async def test_site_info(m: Moodle):
    sinfo = await m.function.core_webservice.get_site_info()
    print(f'[{sinfo.userid}] {sinfo.username}: {sinfo.fullname}')
    print('-' * 15, 'Доступные функции', '-' * 15)
    fns = defaultdict(list)
    for fn in sinfo.functions:
        parts = fn.name.split('_')
        block = '_'.join(parts[:2])
        cap = '_'.join(parts[2:])
        fns[block].append(cap)
    for block in sorted(fns.keys()):
        print(f'{block}:', ', '.join(fns[block]))

    print('-' * 15, 'Дополнительные возможности', '-' * 15)
    for fea in sinfo.advancedfeatures:
        print(f'    {fea.name}: {fea.value}')


if __name__ == '__main__':
    asyncio.run(main())
