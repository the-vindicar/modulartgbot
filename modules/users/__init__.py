"""Поддерживает список пользователей системы, а также механизм одноразовых кодов."""
import logging
import os

from sqlalchemy.ext.asyncio import AsyncEngine
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommandScopeAllPrivateChats
import quart
import quart_auth

from api import CoreAPI, PostInit
from .models import UserBase, SiteUser, UserRepository, UserRoles, NameStyle
from .common import tg_is_registered, tg_is_site_admin, SiteAuthUser, context, router, blueprint
from .registration import *
from .login import *
from .profile import *
from .help import prepare_command_list


__all__ = ['SiteAuthUser', 'SiteUser', 'UserRepository', 'UserRoles', 'NameStyle', 'tg_is_registered',
           'tg_is_site_admin']
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
    app = await api(quart.Quart)
    app.secret_key = os.environ['QUART_AUTH_SECRET']
    quart_auth.QuartAuth(app, user_class=SiteAuthUser, mode='cookie')
    api.register_web_router(blueprint)

    async def load_user_before_request():
        """Загружает сведения о текущем пользователе."""
        if isinstance(quart_auth.current_user, SiteAuthUser):
            await quart_auth.current_user.resolve_user()

    app.before_websocket(load_user_before_request)
    app.before_request(load_user_before_request)

    yield PostInit

    context.commands = prepare_command_list(context.dispatcher)
    if not await context.bot.set_my_commands(context.commands[UserRoles.VERIFIED], BotCommandScopeAllPrivateChats()):
        log.warning('Call to bot.set_my_commands() failed!')
    yield
