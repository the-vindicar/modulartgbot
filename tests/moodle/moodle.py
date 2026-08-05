import asyncio
from collections import defaultdict
import datetime
import logging
from pprint import pprint
from modules.moodle import *


async def main():
    logging.basicConfig(stream=None)
    m = MoodleAdapter('https://sdo.kosgos.ru', input('Username: '), input('Password: '))
    async with m:
        await m.login()
        # await test_site_info(m)
        await test_events(m)


async def test_events(m: MoodleAdapter):
    events = await m.function.core_calendar.get_calendar_events()
    for e in events.events:
        print(e)


async def test_site_info(m: MoodleAdapter):
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
