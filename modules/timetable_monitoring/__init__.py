"""
Реализует отслеживание обновления расписания на сайте КГУ, оповещение об изменениях в расписании,
а также вывод последнего известного расписания в виде веб-страниц.
"""
import asyncio
import datetime
import logging

import asyncpg
import aiogram

from api import CoreAPI, background_task
from modules.wellknown import WellKnownUsers, WellKnownUserInfo
from ._classes import *
from ._data_layer import *
from ._adapter import *
from ._web import *


__all__ = []
requires = [aiogram.Bot, asyncpg.Pool, WellKnownUsers]
provides = []
log = logging.getLogger('modules.timetablemon')


async def tracker_task(api: CoreAPI, db: asyncpg.Connection, users: WellKnownUsers, bot: aiogram.Bot):
    """Фоновая задача, ежесуточно скачивающая расписание с сайта университета и рассылающая уведомления."""
    web_context.config = await api.config.load('timetable_monitoring', TimetableMonitorConfig)
    while True:
        await wait_till_next_update(web_context.config)
        # перезагружаем конфигурацию - в ней могли быть обновления
        web_context.config = await api.config.load('timetable_monitoring', TimetableMonitorConfig)
        # грузим обновленное расписание с сайта
        notifications = await perform_update(api, db, web_context.config, users)
        if notifications:  # были обновления?
            await notify_teachers(bot, notifications)  # да, оповещаем


async def perform_update(
        api: CoreAPI, db: asyncpg.Connection, cfg: TimetableMonitorConfig, users: WellKnownUsers
        ) -> list[tuple[WellKnownUserInfo, list[TimetableSlotChange]]]:
    """Загружает обновлённое расписание с сайта университета, сохраняет его и вычисляет изменения"""
    adapter = KSUTimetableAdapter()
    notifications: list[tuple[WellKnownUserInfo, list[TimetableSlotChange]]] = []
    courses: set[str] = set()
    async with adapter:  # устанавливаем соединение с сайтом
        # выясняем, какие ID у преподавателей в нашем списке
        teacher_ids = await adapter.download_teacher_ids(list(cfg.teachers.keys()))
        for teacher in cfg.teachers:
            if teacher not in teacher_ids:
                log.warning('Unknown teacher "%s" - no teacher id!', teacher)
                continue
            try:
                log.debug('Querying new timetable for %s', teacher)
                timetable = await adapter.download_teacher_timetable(teacher_ids[teacher])
                # обновляем полный список курсов
                courses.update(timetable.get_all_courses())
                async with db.transaction():  # все изменения в БД выполняются в транзакции
                    log.debug('Reading old timetable for teacher %s', teacher)
                    old_timetable = await load_teacher_timetable(db, teacher)
                    log.debug('Storing timetable for %s', teacher)
                    await store_teacher_timetable(db, teacher, timetable)
                    if old_timetable is not None:
                        changes = timetable.changes_from(old_timetable)
                        log.debug('%d changes for %s', len(changes), teacher)
                        if changes:
                            await bump_update_timestamp(db, teacher, datetime.datetime.now(datetime.timezone.utc))
                            key = cfg.teachers.get(teacher, None) or teacher
                            user = users.get(key, None)
                            if user:
                                notifications.append((user, changes))
            except Exception as err:
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
                async with db.transaction():  # все изменения выполняем в рамках транзакции
                    # так как нет нужды вычислять изменения для аудитории, мы просто заменяем её расписание на новое
                    log.debug('Storing timetable for %s', room)
                    await store_room_timetable(db, room, timetable)
            except Exception as err:
                log.error('Failed to update the timetable for %s', room, exc_info=err)
            else:
                log.debug('Updated timetable for %s', room)

    courses.difference_update(cfg.course_shortnames.keys())
    cfg.course_shortnames.update({c: None for c in courses})
    await api.config.save('timetable_monitoring', cfg)
    return notifications


async def notify_teachers(bot: aiogram.Bot,
                          notifications: list[tuple[WellKnownUserInfo, list[TimetableSlotChange]]]) -> None:
    """Выполняет рассылку уведомлений тем преподавателям, для которых мы знаем telegram ID."""
    log.info('Sending notifications...')
    for user, changes in notifications:
        if not user.tgid:
            log.debug('Skipping notifying %s (unknown tgid)', user.name)
            continue
        try:
            log.debug('Notifying %s (tgid:%s)', user.name, user.tgid)
            # формируем текст уведомления
            lines = [f'Изменения в расписании для *{user.name}*:']
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
            await bot.send_message(user.tgid, text, parse_mode='markdown')
            await asyncio.sleep(web_context.config.telegram_delay)
        except Exception as err:
            log.warning('Failed to notify %s!', user.name, exc_info=err)
    log.info('Notifications sent.')


async def wait_till_next_update(cfg) -> None:
    """Ожидает наступления следующего момента обновления расписания, с учётом возможности досрочного обновления."""
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
    log.info('Starting timetable monitoring.')
    pool = await api(asyncpg.Pool)
    bot = await api(aiogram.Bot)
    users = await api(WellKnownUsers)
    # у нас два отдельных соединения - одно для фоновой задачи, одно для веб-обработчиков
    async with pool.acquire() as tracker_connection, pool.acquire() as web_connection:
        async with tracker_connection.transaction():  # создаём таблицы в рамках транзакции
            await create_tables(tracker_connection, log)
        async with background_task(tracker_task(api, tracker_connection, users, bot)):
            # если все нужные ресурсы доступны, и фоновая задача запущена, регистрируем веб-обработчики
            web_context.connection = web_connection
            api.register_web_router(blueprint)
            yield
    log.info('Terminating timetable monitoring.')
