import asyncio
import logging
from pprint import pprint
from modules.moodle import *


async def main():
    logging.basicConfig(stream=None)
    m = MoodleAdapter('https://sdo.kosgos.ru', input('Username: '), input('Password: '))
    async with m:
        await m.login()
        # await test_site_info(m)
        # await test_grades(m)
        await test_comments(m)


async def test_comments(m: MoodleAdapter):
    asses = await m.function.mod_assign_get_assignments(courseids=[7043])
    for item in asses.courses[0].assignments:
        print(f'[ID={item.id} CMID={item.cmid}] {item.name}')
    # assignid 42400 userid 34295
    res = await m.function.mod_assign_get_submission_status(assignid=42400, userid=34295)
    pprint(res.model_dump())


async def test_grades(m: MoodleAdapter):
    grades = await m.function.gradereport_user_get_grade_items(courseid=7043, userid=34295)
    for grade in grades.usergrades:
        print('-'*5, f'Оценки для [{grade.userid}] {grade.userfullname}', '-'*5)
        grade.gradeitems.sort(key=lambda item: (item.itemtype or '', item.itemmodule or '', item.itemname or ''))
        for item in grade.gradeitems:
            print(f'[{item.itemtype}/{item.itemmodule}] {item.itemname}: {item.graderaw} / {item.grademax}'
                  f'|{item.iteminstance=}; {item.id=}; {item.cmid=}; {item.status=}')


async def test_site_info(m: MoodleAdapter):
    sinfo = await m.function.core_webservice_get_site_info()
    print(f'[{sinfo.userid}] {sinfo.username}: {sinfo.fullname}')
    print('-' * 15, 'Доступные функции', '-' * 15)
    sinfo.functions.sort(key=lambda fn: fn.name)
    for fn in sinfo.functions:
        print(f'    {fn.name}')
    print('-' * 15, 'Дополнительные возможности', '-' * 15)
    for fea in sinfo.advancedfeatures:
        print(f'    {fea.name}: {fea.value}')


if __name__ == '__main__':
    asyncio.run(main())
