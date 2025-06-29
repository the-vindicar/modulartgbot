"""Поддерживает список пользователей системы, а также механизм одноразовых кодов."""
import logging

from sqlalchemy.ext.asyncio import AsyncEngine
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommandScopeAllPrivateChats

from api import CoreAPI, PostInit
from .models import UserBase, SiteUser, UserRepository, UserRoles, NameStyle
from .tg import context, router, is_registered, is_site_admin, prepare_command_list


__all__ = ['SiteUser', 'UserRepository', 'UserRoles', 'NameStyle', 'is_registered', 'is_site_admin']
requires = [AsyncEngine, Bot, Dispatcher]
provides = [UserRepository]


async def lifetime(api: CoreAPI):
    """Тело модуля."""
    log = logging.getLogger('modules.users')
    engine = await api(AsyncEngine)
    context.log = log
    context.bot = await api(Bot)
    context.dispatcher = await api(Dispatcher)
    context.repository = UserRepository(engine)
    await context.repository.create_tables()
    api.register_api_provider(context.repository, UserRepository)
    context.dispatcher.include_router(router)
    yield PostInit

    context.commands = prepare_command_list(context.dispatcher)
    if not await context.bot.set_my_commands(context.commands[UserRoles.VERIFIED], BotCommandScopeAllPrivateChats()):
        log.warning('Call to bot.set_my_commands() failed!')
    yield
