"""Общие утилиты для работы с пользователями."""
import dataclasses
import logging

from aiogram import Router, Dispatcher, Bot
from quart import Blueprint

from modules.users import UserRepository
from modules.moodle import MoodleAdapter, MoodleMessageBot


@dataclasses.dataclass
class RegistrationContext:
    """Зависимости, требуемые для реализации команд бота."""
    repository: UserRepository = None
    bot: Bot = None
    dispatcher: Dispatcher = None
    log: logging.Logger = None
    moodle: MoodleAdapter = None
    moodlebot: MoodleMessageBot = None


context: RegistrationContext = RegistrationContext()
tgrouter = Router(name='users_extra')
blueprint: Blueprint = Blueprint(
    name='users_extra', import_name='modules.users_extra',
    url_prefix='/user', template_folder='templates',
    static_folder='static', static_url_path='static')
__all__ = ['context', 'tgrouter', 'blueprint']
