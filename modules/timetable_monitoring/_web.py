"""Реализует web-часть монитора расписаний."""
from typing import Literal
import asyncio
import dataclasses
import datetime

import quart

from ._classes import *
from .models import TimetableRepository


@dataclasses.dataclass(slots=True)
class Context:
    """Глобальные переменные для взаимодействия между фоновой задачей и веб-обработчиками."""
    config: TimetableMonitorConfig = dataclasses.field(default_factory=TimetableMonitorConfig)
    ttrepo: TimetableRepository = None
    force_update: asyncio.Event = asyncio.Event()  # при установке принудительно запускает обновление расписания


@dataclasses.dataclass(slots=True)
class RoomDescription:
    """Описание аудитории для передачи в шаблон"""
    name: str
    type: str
    equip: dict[str, ...]


web_context = Context()
blueprint = quart.Blueprint(
    name='timetable', import_name='modules.timetable_monitoring',
    url_prefix='/timetable', template_folder='templates',
    static_folder='static', static_url_path='static')
__all__ = ['blueprint', 'web_context']


def get_current_week() -> Literal['above', 'below']:
    """Определяет текущую неделю: над чертой или под чертой"""
    now = datetime.datetime.now()
    # начало текущего учебного года
    start = datetime.datetime(now.year if now.month >= 9 else now.year-1, 9, 1)
    # понедельник первой учебной недели
    start = start + datetime.timedelta(days=(7 if start.weekday() >= 5 else 0) - start.weekday())
    # номер учебной недели (с нуля)
    week = (now - start).days // 7
    return 'above' if week % 2 == 0 else 'below'


@blueprint.get('/')
async def handle_root():
    """Корень раздела расписаний."""
    return quart.redirect(quart.url_for('.handle_teachers'))


@blueprint.get('/teachers')
async def handle_teachers():
    """Таблица расписаний преподавателей."""
    teachers = [name.partition('@')[0] for name in web_context.config.teachers.keys()]
    timetables: dict[str, Timetable] = await web_context.ttrepo.load_teachers_timetables(teachers)
    updates = await web_context.ttrepo.load_update_timestamps()
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
                items.append((t, slot.replace_course_names(web_context.config.course_shortnames)))
            periods.append((iperiod, period, items))
        days.append((iday, day, periods))

    return await quart.render_template(
        'timetable/teachers.html',
        headers=update_times,
        days=days,
        week=get_current_week(),
        len=len,
        rooms_url=quart.url_for('.handle_rooms')
    )


@blueprint.get('/rooms')
async def handle_rooms():
    """Таблица расписаний аудиторий."""
    room_names = list(web_context.config.rooms.keys())
    timetables: dict[str, Timetable] = await web_context.ttrepo.load_rooms_timetables(room_names)
    days = []
    for iday, day in enumerate(Timetable.DAYS):
        periods = []
        for iperiod, period in enumerate(Timetable.PERIODS):
            items = []
            for r in room_names:
                slot = timetables[r].slots[iday][iperiod]
                items.append((r, slot.replace_course_names(web_context.config.course_shortnames)))
            periods.append((iperiod, period, items))
        days.append((iday, day, periods))
    headers = [
        RoomDescription(name, info.get('type', '').lower(), {k: v for k, v in info.items() if k != 'type'})
        for name, info in web_context.config.rooms.items()
    ]
    return await quart.render_template(
        'timetable/rooms.html',
        headers=headers,
        days=days,
        week=get_current_week(),
        len=len,
        teachers_url=quart.url_for('.handle_teachers')
    )
