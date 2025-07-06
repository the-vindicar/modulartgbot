"""Предоставляет механизмы обработки одноразовых кодов, пришедших в личку Moodle."""
import typing as t
import re

from .common import context
from modules.moodle import MoodleMessageBot, RMessage
from modules.users import SiteUser


CodeHandler = t.Callable[[str, SiteUser, RMessage], t.Awaitable[None]]
__all__ = ['MoodleCodeHandler']


class MoodleCodeHandler:
    """Позволяет регистрировать обработчики одноразовых кодов в личке Moodle."""
    def __init__(self):
        self._handlers: dict[str, CodeHandler] = {}

    async def _handle(self, msg: RMessage) -> None:
        """Обрабатывает сообщения, выглядящие как одноразовый код."""
        match = context.repository.ONE_TIME_CODE_PATTERN.search(msg.fullmessage)
        if not match:
            context.log.warning('For some reason, one-time code message "%s" does not match the pattern "%s"',
                                msg.fullmessage, context.repository.ONE_TIME_CODE_PATTERN.pattern)
            return
        code = match.group(0)
        intent, user = await context.repository.try_consume_onetime_code(code, intent=list(self._handlers.keys()))
        if intent is not None and user is not None:
            context.log.debug('Received a one-time code with intent "%s" from user %s via Moodle PM.',
                              intent, msg.userfromfullname)
            handler = self._handlers.get(intent, None)
            if handler is not None:
                try:
                    await handler(intent, user, msg)
                except Exception as err:
                    context.log.warning('Handler %r for a one-time code with intent "%s" failed!',
                                        handler, intent, exc_info=err)
            else:
                context.log.warning('No handler found for a one-time code with intent "%s".', intent)

    def register_self(self, bot: MoodleMessageBot) -> None:
        """Регистрирует обработчик сообщений, выглядящих как одноразовый код."""
        pattern = re.compile(r'(?:.*?\D+)?' + context.repository.ONE_TIME_CODE_PATTERN.pattern + r'(?:\D+.*?)?')
        bot.register(pattern, self._handle)

    def register(self, intent: str, handler: CodeHandler) -> None:
        """Регистрирует обработчик для одноразовых кодов с указанным intent.

        :param intent: Коды с каким intent должен обслуживать этот обработчик.
        :param handler: Обработчик вида ``(str, SiteUser, RMessage) -> Awaitable[None]``"""
        if intent in self._handlers:
            raise KeyError(f'Code intent {intent!r} is already handled by {self._handlers[intent]!r}!')
        self._handlers[intent] = handler
        context.log.debug('Handler %r handles codes with intent "%s".', handler, intent)
