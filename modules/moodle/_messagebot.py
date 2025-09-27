"""Предоставляет примитивный способ реагировать на входящие сообщения от пользователей Moodle."""
import asyncio
import typing as t
import datetime
import logging
import re
from .moodle import Moodle, MessageType, MessageReadStatus, RMessage, MoodleError
from api import ExponentialBackoff


MessageHandler = t.Callable[[RMessage], t.Awaitable[None]]
MessageFilter = t.Callable[[RMessage], t.Awaitable[bool]]
__all__ = ['MoodleMessageBot']


class MoodleMessageBot:
    """Обслуживает входящие сообщения, вызывая обработчики для них."""
    def __init__(self, m: Moodle, log: logging.Logger):
        self._moodle = m
        self._log = log
        self._handlers: list[tuple[t.Union[re.Pattern[str], MessageFilter], MessageHandler]] = []
        self._is_polling = False
        self.default_handler: t.Optional[MessageHandler] = None

    @property
    def is_polling(self) -> bool:
        """Возвращает True, если бот активен."""
        return self._is_polling

    @property
    def moodle(self) -> Moodle:
        """Возвращает ссылку на адаптер Moodle, с которым мы работаем."""
        return self._moodle

    @t.overload
    def register(self, pattern: t.Union[str, re.Pattern[str], MessageFilter], func: MessageHandler) -> MessageHandler:
        """Регистрирует переданную функцию как обработчик сообщений."""

    @t.overload
    def register(self, pattern: t.Union[str, re.Pattern[str], MessageFilter], func: None = None
                 ) -> t.Callable[[MessageHandler], MessageHandler]:
        """Предоставляет декоратор, регистрирующий функцию как обработчик сообщений."""

    def register(self, pattern: t.Union[str, re.Pattern[str], MessageFilter], func: MessageHandler = None):
        """Позволяет зарегистрировать функцию как обработчик сообщений.

        :param pattern: Шаблон, которому должно соответствовать сообщение.
        :param func: Регистрируемый обработчик вида (user_id, str) -> None
        """
        if isinstance(pattern, str):
            pattern = re.compile(pattern)
        if func is None:
            def decorator(f: MessageHandler) -> MessageHandler:
                """Декоратор для регистрации функции."""
                self._handlers.append((pattern, f))
                return f
            return decorator
        self._handlers.append((pattern, func))
        return func

    async def poll_messages(self, interval: datetime.timedelta) -> t.NoReturn:
        """Циклически запрашивает у сервера новые сообщения и обрабатывает их."""
        try:
            self._is_polling = True
            backoff = ExponentialBackoff(base=interval, quotient=2, sleep_on_success='base',
                                         jitter=0.25*interval, cap=datetime.timedelta(hours=1))
            while True:
                unread = await self._moodle.function.core_message.get_unread_conversations_count(self._moodle.me.id)
                if unread > 0:
                    try:
                        messages = await self._moodle.function.core_message.get_messages(
                            useridto=self._moodle.me.id, useridfrom=0, type=MessageType.CONVERSATIONS,
                            read=MessageReadStatus.UNREAD, newestfirst=False, limitnum=10)
                        for msg in messages.messages:
                            for msgfilter, msghandler in self._handlers[::-1]:
                                try:
                                    if isinstance(msgfilter, re.Pattern):
                                        check_passed = msgfilter.match(msg.fullmessage)
                                    else:
                                        check_passed = await msgfilter(msg)
                                except Exception as err:
                                    self._log.warning('Message filter %s failed!\nMessage: %s',
                                                      msgfilter, msg, exc_info=err)
                                    check_passed = False
                                if check_passed:
                                    try:
                                        await msghandler(msg)
                                    except Exception as err:
                                        self._log.warning('Message handler %s failed!\nMessage: %s',
                                                          msghandler, msg, exc_info=err)
                                    break
                            else:
                                defhandler = self.default_handler
                                if defhandler is not None:
                                    try:
                                        await defhandler(msg)
                                    except Exception as err:
                                        self._log.warning('Message handler %s failed!\nMessage: %s',
                                                          defhandler, msg, exc_info=err)
                                else:
                                    self._log.info('No handler found for message from %s (%d): %s',
                                                   msg.userfromfullname, msg.useridfrom, msg.fullmessage)
                            await self._moodle.function.core_message.mark_message_read(msg.id)
                    except MoodleError as err:
                        wait = backoff.after_failure()
                        self._log.error('Moodle server failure! Will sleep for %s and hope it goes away.',
                                        wait, exc_info=err)
                        await asyncio.sleep(wait.total_seconds())
                    else:
                        wait = backoff.after_success()
                        await asyncio.sleep(wait.total_seconds())
        finally:
            self._is_polling = False
