"""Реализует справку о доступных командах."""
import typing as t
from collections import defaultdict
import logging
import re

from aiogram import Dispatcher
from aiogram.dispatcher.event.handler import HandlerObject, FilterObject
from aiogram.fsm.state import State
from aiogram.types import Message, BotCommand
from aiogram.filters import Command, logic

from .models import UserRoles
from .common import router, context, CommandsInfo, tg_is_site_admin, tg_is_registered


__all__ = [
    'prepare_command_list'
]


def all_message_handlers(dispatcher: Dispatcher) -> t.Iterable[HandlerObject]:
    """Перечисляет все обработчики сообщений, прямо или опосредованно зарегистрированные в диспетчере бота."""
    for r in dispatcher.chain_tail:
        yield from r.message.handlers


def all_filters(filters: t.Iterable[FilterObject]) -> t.Iterable[FilterObject]:
    """Распаковывает логические конструкции из фильтров, получая цепочку базовых фильтров."""
    for f in filters:
        if isinstance(f.callback, (logic._OrFilter, logic._AndFilter)):  # noqa
            yield from all_filters(f.callback.targets)
        else:
            yield f


def prepare_command_list(dispatcher: Dispatcher) -> CommandsInfo:
    """Составляем список команд в диспетчере, получаем их описания из docstring, и раскидываем их по ролям."""
    commands: CommandsInfo = defaultdict(list)
    log = logging.getLogger('modules.users')
    log.debug('Making a list of all available commands...')
    log.debug('Dispatcher has %d subrouters: %s',
              len(dispatcher.sub_routers), ', '.join([r.name for r in dispatcher.sub_routers]))
    for h in all_message_handlers(dispatcher):  # команды - это всегда сообщения
        log.debug('Processing %s()', h.callback.__qualname__)
        filters = list(all_filters(h.filters))
        if any(isinstance(f.callback, State) for f in filters):
            log.debug('    %s() has a State filter, ignoring it', h.callback.__qualname__)
            continue  # игнорируем команды, требующие определённого состояния FSM
        command_filters: list[FilterObject] = [f for f in filters if isinstance(f.callback, Command)]
        if command_filters:
            if any(f.callback is tg_is_site_admin for f in filters):
                roles = UserRoles.SITE_ADMIN,
            elif any(f.callback is tg_is_registered for f in filters):
                roles = UserRoles.SITE_ADMIN, UserRoles.VERIFIED
            else:
                roles = UserRoles.SITE_ADMIN, UserRoles.VERIFIED, UserRoles.UNVERIFIED
            docstring = getattr(h.callback, '__doc__', 'Нет информации.')
            for fltr in command_filters:
                cmd: Command = fltr.callback  # type: ignore
                for cmd_pattern in cmd.commands:
                    if isinstance(cmd_pattern, BotCommand):
                        info = BotCommand(command=f'{cmd_pattern.command}',
                                          description=cmd_pattern.description or docstring)
                        log.debug('    BotCommand "%s" defined for roles %s', info.command,
                                  ', '.join([r.name for r in roles]))
                    elif isinstance(cmd_pattern, re.Pattern):
                        info = BotCommand(command=f'{cmd_pattern.pattern}', description=docstring)
                        log.debug('    Regexp command "%s" defined for roles %s', info.command,
                                  ', '.join([r.name for r in roles]))
                    else:
                        info = BotCommand(command=f'{cmd_pattern}', description=docstring)
                        log.debug('    String command "%s" defined for roles %s', info.command,
                                  ', '.join([r.name for r in roles]))
                    for role in roles:
                        commands[role].append(info)
        else:
            log.debug('    %s() does not have a Command filter, ignoring it.', h.callback.__qualname__)
    for role, cmds in commands.items():
        log.debug('For role %s there are %d available commands.', role, len(cmds))
        startcmd, helpcmd = None, None
        for i in range(len(cmds)-1, -1, -1):
            if cmds[i].command == 'start':
                startcmd = cmds.pop(i)
            elif cmds[i].command == 'help':
                helpcmd = cmds.pop(i)
        cmds.sort(key=lambda item: item.command)
        if startcmd:
            cmds.insert(0, startcmd)
        if helpcmd:
            cmds.insert(0, helpcmd)
    return commands


@router.message(Command('help'))
async def on_help_command(msg: Message):
    """Показывает справку по доступным командам."""
    try:
        role = await context.repository.get_role_by_tg_id(msg.from_user.id)
    except Exception as err:
        context.log.warning('Failed to get user role for %s', msg.from_user.url, exc_info=err)
        role = UserRoles.UNVERIFIED
    text = [
        'Доступные вам команды:'
    ]
    for cmd in context.commands[role]:
        text.append(f'/{cmd.command} - {cmd.description}')
    helptext = '\r\n'.join(text)
    await msg.answer(helptext, parse_mode='HTML')
