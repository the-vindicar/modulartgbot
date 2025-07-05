"""Общие утилиты для работы с пользователями."""
import dataclasses
import logging

from aiogram import Router, Dispatcher, Bot

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
__all__ = ['context', 'tgrouter']