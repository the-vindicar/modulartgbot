import asyncio
from modules.moodle.moodle import Moodle


async def main():
    m = Moodle('https://sdo.kosgos.ru', input('Username: '), input('Password: '))
    async with m:
        await m.login()


if __name__ == '__main__':
    asyncio.run(main())