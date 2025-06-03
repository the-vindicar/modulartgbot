import asyncio
import dataclasses

import asyncpg
import quart

from ._classes import *
from ._data_layer import *


@dataclasses.dataclass(slots=True)
class Context:
    """Глобальные переменные для взаимодействия между фоновой задачей и веб-обработчиками."""
    config: TimetableMonitorConfig = dataclasses.field(default_factory=TimetableMonitorConfig)
    connection: asyncpg.Connection = None
    force_update: asyncio.Event = asyncio.Event()  # при установке принудительно запускает обновление расписания


web_context = Context()
blueprint = quart.Blueprint(
    name='timetable', import_name='modules.timetable_monitoring',
    url_prefix='/timetable', template_folder='templates',
    static_folder='static', static_url_path='static')
__all__ = ['blueprint', 'web_context']


@blueprint.get('/')
async def handle_root():
    return quart.redirect(quart.url_for('.handle_teachers'))


@blueprint.get('/teachers')
async def handle_teachers():
    teachers = list(web_context.config.teachers.keys())
    timetables: dict[str, Timetable] = {}
    async with web_context.connection.transaction(isolation='read_committed', readonly=True):
        for t in teachers:
            timetables[t] = await load_teacher_timetable(web_context.connection, t)
        updates = await load_update_timestamps(web_context.connection)
    update_times = [
        (name,
         f'Обновлено {updates[name]:%d %B %Y}' if name in updates else None)
        for name in teachers
    ]
    days = []
    for iday, day in enumerate(Timetable.DAYS):
        periods = []
        for iperiod, period in enumerate(Timetable.PERIODS):
            items = []
            for t in teachers:
                slot = timetables[t].slots[iday][iperiod]
                items.append(slot.replace_course_names(web_context.config.course_shortnames))
            periods.append((iperiod, period, items))
        days.append((iday, day, periods))

    return await quart.render_template(
        'timetable/teachers.html',
        headers=update_times,
        days=days,
        len=len,
        rooms_url=quart.url_for('.handle_rooms')
    )


@blueprint.get('/rooms')
async def handle_rooms():
    rooms = list(web_context.config.rooms)
    timetables: dict[str, Timetable] = {}
    async with web_context.connection.transaction(isolation='read_committed', readonly=True):
        for r in rooms:
            timetables[r] = await load_room_timetable(web_context.connection, r)
    days = []
    for iday, day in enumerate(Timetable.DAYS):
        periods = []
        for iperiod, period in enumerate(Timetable.PERIODS):
            items = []
            for r in rooms:
                slot = timetables[r].slots[iday][iperiod]
                items.append(slot.replace_course_names(web_context.config.course_shortnames))
            periods.append((iperiod, period, items))
        days.append((iday, day, periods))

    return await quart.render_template(
        'timetable/rooms.html',
        headers=rooms,
        days=days,
        len=len,
        teachers_url=quart.url_for('.handle_teachers')
    )
