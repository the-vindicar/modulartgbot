import asyncio
from modules.moodle import *


async def main():
    m = MoodleAdapter('https://sdo.kosgos.ru', input('Username: '), input('Password: '))
    async with m:
        await m.login()
        sinfo = await m.function.core_webservice_get_site_info()
        print(f'[{sinfo.userid}] {sinfo.username}: {sinfo.fullname}')
        print('-'*15, 'Доступные функции', '-'*15)
        sinfo.functions.sort(key=lambda fn: fn.name)
        for fn in sinfo.functions:
            print(f'    {fn.name}')
        print('-' * 15, 'Дополнительные возможности', '-' * 15)
        for fea in sinfo.advancedfeatures:
            print(f'    {fea.name}: {fea.value}')


if __name__ == '__main__':
    asyncio.run(main())
