"""Общие утилиты для работы с пользователями."""
import typing as t
import dataclasses
import functools
import logging

from aiogram import Router, Dispatcher, Bot
from aiogram.fsm.state import State
from aiogram.fsm.storage.memory import StorageKey
from aiogram.types import Message, CallbackQuery, BotCommand
from quart import Blueprint, current_app
import quart_auth

from .models import UserRoles, UserRepository, SiteUser


__all__ = [
    'CommandsInfo', 'blueprint', 'context', 'router',
    'tg_is_registered', 'tg_is_site_admin',
    'SiteAuthUser', 'web_is_registered', 'web_is_site_admin']
CommandsInfo: t.TypeAlias = dict[UserRoles, list[BotCommand]]
T = t.TypeVar("T")
P = t.ParamSpec("P")


class SiteAuthUser(quart_auth.AuthUser):
    def __init__(self, user_id: t.Optional[str], action: quart_auth.Action = quart_auth.Action.PASS):
        super().__init__(user_id, action)
        self._resolved = False
        self._user: t.Optional[SiteUser] = None

    @property
    def user(self) -> t.Optional[SiteUser]:
        """Текущий пользователь."""
        return self._user

    @property
    def is_admin(self) -> bool:
        """Является ли текущий пользователь админом."""
        return self._user.role == UserRoles.SITE_ADMIN if self._user else False

    async def resolve_user(self) -> None:
        """Загружает пользователя из БД."""
        if not self._resolved:
            if self.auth_id is None:
                self._user = None
            else:
                self._user = await context.repository.get_by_id(int(self.auth_id))
            self._resolved = True


@dataclasses.dataclass
class RegistrationContext:
    """Зависимости, требуемые для реализации команд бота."""
    repository: UserRepository = None
    bot: Bot = None
    dispatcher: Dispatcher = None
    log: logging.Logger = None
    commands: CommandsInfo = dataclasses.field(default_factory=dict)

    async def get_state_for_user(self, user_id: int) -> t.Optional[str]:
        """Принудительно читает состояние пользователя. Может быть использовано вне контекста обработки сообщения."""
        key = StorageKey(bot_id=self.bot.id, chat_id=user_id, user_id=user_id,
                         thread_id=None, business_connection_id=None)
        return await self.dispatcher.storage.get_state(key)

    async def set_state_for_user(self, user_id: int, state: str | State | None, **data_updates) -> None:
        """Принудительно задаёт состояние пользователю. Может быть использовано вне контекста обработки сообщения."""
        key = StorageKey(bot_id=self.bot.id, chat_id=user_id, user_id=user_id,
                         thread_id=None, business_connection_id=None)
        await self.dispatcher.storage.set_state(key, state)
        if data_updates:
            await self.dispatcher.storage.update_data(key, **data_updates)


context: RegistrationContext = RegistrationContext()
router: Router = Router(name='users')
blueprint: Blueprint = Blueprint(
    name='users', import_name='modules.users',
    url_prefix='/user', template_folder='templates',
    static_folder='static', static_url_path='static')


async def tg_is_registered(src: Message | CallbackQuery) -> bool:
    """Проверяет, что пользователь с этим TGID зарегистрирован и не заблокирован."""
    role = await context.repository.get_role_by_tg_id(src.from_user.id)
    return role not in (UserRoles.UNVERIFIED, UserRoles.BLOCKED)


async def tg_is_site_admin(src: Message | CallbackQuery) -> bool:
    """Проверяет, что пользователь с этим TGID является администратором сайта."""
    role = await context.repository.get_role_by_tg_id(src.from_user.id)
    return role == UserRoles.SITE_ADMIN


web_is_registered = quart_auth.login_required


def web_is_site_admin(f: t.Callable[P, t.Awaitable[T]]) -> t.Callable[P, t.Awaitable[T]]:
    """Проверяет, что пользователь залогинен на сайте как админ."""
    @functools.wraps(f)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        """Обёртка для проверки логина."""
        cuser = t.cast(SiteAuthUser, quart_auth.current_user)
        await cuser.resolve_user()
        if not cuser.is_admin:
            raise quart_auth.Unauthorized()
        return await current_app.ensure_async(f)(*args, **kwargs)

    return wrapper
