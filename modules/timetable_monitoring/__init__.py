"""
Реализует отслеживание обновления расписания на сайте КГУ, оповещение об изменениях в расписании,
а также вывод последнего известного расписания в виде веб-страниц.
"""
import typing as t
import asyncio
import datetime
import logging

import aiohttp
import aiogram
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncEngine

from api import CoreAPI, background_task
from modules.users import UserRepository, NameStyle, SiteUser, tg_is_site_admin
from ._classes import *
from .models import TimetableRepository
from ._adapter import *
from ._web import web_context, blueprint


__all__ = []
requires = [aiogram.Bot, aiogram.Dispatcher, AsyncEngine, UserRepository]
provides = []
log = logging.getLogger('modules.timetablemon')
tgrouter = aiogram.Router(name='timetable')


@tgrouter.message(tg_is_site_admin, Command('timetable_scan_now'))
async def force_timetable_scan(msg: aiogram.types.Message):
    """Принудительно запускает сканирование официального расписания занятий. Также разошлёт оповещения об изменениях."""
    web_context.force_update.set()
    log.info('User %s ( %s ) forced a scan.', msg.from_user.full_name, msg.from_user.id)
    await msg.answer('Обновление расписания запущено.')


class TimetableTracker:
    """Реализует мониторинг расписания и его кэширование в БД."""
    def __init__(self, ttrepo: TimetableRepository, userrepo: UserRepository, api: CoreAPI, bot: aiogram.Bot):
        self.ttrepo = ttrepo
        self.userrepo = userrepo
        self.api = api
        self.bot = bot

    async def tracker_task(self) -> None:
        """Фоновая задача, ежесуточно скачивающая расписание с сайта университета и рассылающая уведомления."""
        web_context.config = await self.api.config.load('timetable_monitoring', TimetableMonitorConfig)
        while True:
            await self.wait_till_next_update(web_context.config)
            # перезагружаем конфигурацию - в ней могли быть обновления
            web_context.config = await self.api.config.load('timetable_monitoring', TimetableMonitorConfig)
            # грузим обновленное расписание с сайта
            try:
                notifications = await self.perform_update(web_context.config)
                if notifications:  # были обновления?
                    await self.notify_teachers(notifications)  # да, оповещаем
            except Exception as err:
                log.critical('Unexpected error:', exc_info=err)

    async def perform_update(self, cfg: TimetableMonitorConfig) -> list[tuple[SiteUser, list[TimetableSlotChange]]]:
        """Загружает обновлённое расписание с сайта университета, сохраняет его и вычисляет изменения.
        :param cfg: Текущая конфигурация сервиса.
        :returns: Набор пар "Telegram ID - список изменений"."""
        notifications: list[tuple[SiteUser, list[TimetableSlotChange]]] = []
        courses: set[str] = set()
        mindelay = datetime.timedelta(seconds=cfg.website_delay)
        async with KSUTimetableAdapter(request_interval=mindelay) as adapter:  # устанавливаем соединение с сайтом
            # выясняем, какие ID у преподавателей в нашем списке
            all_names = list(cfg.teachers.keys())
            names_with_ids = [n for n in all_names if '@' in n]
            names_without_ids = [n for n in all_names if '@' not in n]
            teacher_ids = await adapter.download_teacher_ids(names_without_ids)
            for n in names_without_ids:
                if n not in teacher_ids:
                    log.warning('Unknown teacher "%r" - no teacher id!', n)
            for n in names_with_ids:
                name, _, tid = n.partition('@')
                teacher_ids[name] = int(tid)
            for teacher, teacher_id in teacher_ids.items():
                try:
                    log.debug('Querying new timetable for %s', teacher)
                    timetable = await adapter.download_teacher_timetable(teacher_id)
                    # обновляем полный список курсов
                    courses.update(timetable.get_all_courses())
                    log.debug('Reading old timetable for teacher %s', teacher)
                    old_timetable = await self.ttrepo.load_teacher_timetable(teacher)
                    log.debug('Storing timetable for %s', teacher)
                    await self.ttrepo.store_teacher_timetable(teacher, timetable)
                    if old_timetable is not None:
                        changes = timetable.changes_from(old_timetable)
                        log.debug('%d changes for %s', len(changes), teacher)
                        if changes:
                            await self.ttrepo.bump_update_timestamp(teacher)
                            userlist = await self.userrepo.get_by_name(teacher, NameStyle.LastFP)
                            if len(userlist) == 1:
                                notifications.append((userlist[0], changes))
                except Exception as err:
                    if isinstance(err, aiohttp.ClientResponseError):
                        log.error('Failed to update the timetable for %s.\n[%d] Headers: %s',
                                  teacher, err.status, repr(err.headers), exc_info=err)
                    else:
                        log.error('Failed to update the timetable for %s', teacher, exc_info=err)
                else:
                    log.debug('Updated timetable for %s', teacher)
            # выясняем ID аудиторий
            room_ids = await adapter.download_room_ids()
            for room in cfg.rooms:
                room_id = room_ids.get(room, None)
                if room_id is None:
                    log.warning('Unknown room "%s" - no room id!', room)
                    continue
                try:
                    log.debug('Querying new timetable for room %s', room)
                    timetable = await adapter.download_room_timetable(room_id)
                    courses.update(timetable.get_all_courses())
                    # так как нет нужды вычислять изменения для аудитории, мы просто заменяем её расписание на новое
                    log.debug('Storing timetable for %s', room)
                    await self.ttrepo.store_room_timetable(room, timetable)
                except Exception as err:
                    if isinstance(err, aiohttp.ClientResponseError):
                        log.error('Failed to update the timetable for %s.\n[%d] Headers: %s',
                                  room, err.status, repr(err.headers), exc_info=err)
                    else:
                        log.error('Failed to update the timetable for %s', room, exc_info=err)
                else:
                    log.debug('Updated timetable for %s', room)

        courses.difference_update(cfg.course_shortnames.keys())
        cfg.course_shortnames.update({c: None for c in courses})
        await self.api.config.save('timetable_monitoring', cfg)
        return notifications

    async def notify_teachers(self, notifications: list[tuple[SiteUser, list[TimetableSlotChange]]]) -> None:
        """Выполняет рассылку уведомлений тем преподавателям, для которых мы знаем telegram ID.
        :param notifications: Список пар "пользователь - список уведомлений"."""
        log.info('Sending notifications...')
        for user, changes in notifications:
            username = user.get_name(NameStyle.LastFP)
            usertgid = t.cast(int, user.tgid)
            if not user.tgid:
                log.debug('Skipping notifying %s (unknown tgid)', username)
                continue
            try:
                log.debug('Notifying %s (tgid:%s)', username, usertgid)
                # формируем текст уведомления
                lines = [f'Изменения в расписании для *{username}*:']
                for diff in changes:
                    lines.append(f'{diff.day} ({diff.week}) {diff.period + 1}я пара:')
                    if diff.old and diff.new:
                        lines.append(f'  Было: ({diff.old.type}) {diff.old.course} '
                                     f'у {diff.old.groups} в {diff.old.room}')
                        lines.append(f'  Стало: ({diff.new.type}) {diff.new.course} '
                                     f'у {diff.new.groups} в {diff.new.room}')
                    elif diff.old:
                        lines.append(f'  Пропало: ({diff.old.type}) {diff.old.course} '
                                     f'у {diff.old.groups} в {diff.old.room}')
                    elif diff.new:
                        lines.append(f'  Появилось: ({diff.new.type}) {diff.new.course} '
                                     f'у {diff.new.groups} в {diff.new.room}')
                text = '\n'.join(lines)
                # отправляем сообщение, затем ждём, чтобы не превышать лимиты по частоте отправки
                await self.bot.send_message(usertgid, text, parse_mode='markdown')
                await asyncio.sleep(web_context.config.telegram_delay)
            except Exception as err:
                log.warning('Failed to notify %s!', username, exc_info=err)
        log.info('Notifications sent.')

    @staticmethod
    async def wait_till_next_update(cfg: TimetableMonitorConfig) -> None:
        """Ожидает наступления следующего момента обновления расписания, с учётом возможности досрочного обновления.
        :param cfg: Текущая конфигурация."""
        update_time = datetime.datetime.strptime(
            cfg.update_time_utc, '%H:%M:%S'
        ).replace(tzinfo=datetime.timezone.utc)
        now = datetime.datetime.now(datetime.timezone.utc)
        next_update = now.replace(hour=update_time.hour, minute=update_time.minute, second=update_time.second)
        if next_update < now:
            next_update += datetime.timedelta(days=1)
        log.info('Next timetable update at %s. Waiting...', next_update)
        delay = (next_update - now).total_seconds()
        # сбрасываем флаг принудительного обновления прямо перед ожиданием
        # это гарантирует, что повторное выставление этого флага в ходе обновления не приведёт к ещё одному обновлению
        web_context.force_update.clear()
        try:  # ждём или истечения интервала времени, или сигнала о принудительном обновлении
            await asyncio.wait_for(web_context.force_update.wait(), delay)
        except asyncio.TimeoutError:
            pass


async def lifetime(api: CoreAPI):
    """Тело модуля."""
    log.info('Starting timetable monitoring.')
    engine = await api(AsyncEngine)
    bot = await api(aiogram.Bot)
    tgdispatcher = await api(aiogram.Dispatcher)
    users = await api(UserRepository)
    ttrepo = TimetableRepository(engine)
    tracker = TimetableTracker(ttrepo, users, api, bot)
    async with background_task(tracker.tracker_task()):
        # если все нужные ресурсы доступны, и фоновая задача запущена, регистрируем веб-обработчики
        web_context.ttrepo = ttrepo
        api.register_web_router(blueprint)
        tgdispatcher.include_router(tgrouter)
        yield
    log.info('Terminating timetable monitoring.')
