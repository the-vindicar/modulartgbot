"""Дополнительные возможности для пользователей системы, такие как страница профиля или привязка Moodle."""
import logging

from sqlalchemy.ext.asyncio import AsyncEngine
from aiogram import Bot, Dispatcher

from api import CoreAPI
from .common import context
from modules.users import UserRepository
from modules.moodle import MoodleAdapter, MoodleMessageBot

from .common import tgrouter
from .code_handler import MoodleCodeHandler
from .moodle_connect import MOODLE_ATTACH_INTENT, handle_moodle_intent_code


__all__ = ['MoodleCodeHandler']
requires = [AsyncEngine, Bot, Dispatcher, UserRepository, MoodleAdapter, MoodleMessageBot]
provides = [MoodleCodeHandler]


async def lifetime(api: CoreAPI):
    """Тело модуля."""
    log = logging.getLogger('modules.users')
    engine = await api(AsyncEngine)
    context.log = log
    context.bot = await api(Bot)
    context.dispatcher = await api(Dispatcher)
    context.repository = UserRepository(engine)
    context.moodle = await api(MoodleAdapter)
    context.moodlebot = await api(MoodleMessageBot)

    context.dispatcher.include_router(tgrouter)
    codehandler = MoodleCodeHandler()
    api.register_api_provider(codehandler, MoodleCodeHandler)
    codehandler.register(MOODLE_ATTACH_INTENT, handle_moodle_intent_code)
    codehandler.register_self(context.moodlebot)
    yield
