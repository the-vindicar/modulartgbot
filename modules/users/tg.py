"""Реализует простую регистрацию через Telegram с подтверждением учётки админом."""
import typing as t
from collections import defaultdict
import dataclasses
import logging
import re

from aiogram import Router, Dispatcher, Bot
from aiogram.dispatcher.event.handler import HandlerObject, FilterObject
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import StorageKey
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from aiogram.filters import Command, CommandStart, or_f, logic

from .models import SiteUser, UserRoles, UserRepository, NameStyle


__all__ = [
    'context', 'router',
    'is_registered', 'is_site_admin',
    'prepare_command_list'
]
CommandsInfo: t.TypeAlias = dict[UserRoles, list[BotCommand]]


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


class UserRegistrationStates(StatesGroup):
    """Состояния при регистрации пользователя."""
    awaiting_name = State()
    awaiting_confirmation = State()
    blocked = State()


async def is_registered(src: Message | CallbackQuery) -> bool:
    """Проверяет, что пользователь с этим TGID зарегистрирован и не заблокирован."""
    role = await context.repository.get_role_by_tg_id(src.from_user.id)
    return role not in (UserRoles.UNVERIFIED, UserRoles.BLOCKED)


async def is_site_admin(src: Message | CallbackQuery) -> bool:
    """Проверяет, что пользователь с этим TGID является администратором сайта."""
    role = await context.repository.get_role_by_tg_id(src.from_user.id)
    return role == UserRoles.SITE_ADMIN


@router.message(UserRegistrationStates.blocked)
async def blocked_message(msg: Message):
    """Перехватывает сообщения от заблокированных пользователей."""
    context.log.debug('Message from blocked user %d ignored.', msg.from_user.id)


@router.callback_query(UserRegistrationStates.blocked)
async def blocked_query(query: CallbackQuery):
    """Перехватывает нажатия кнопок от заблокированных пользователей."""
    context.log.debug('Callback query from blocked user %d ignored.', query.from_user.id)
    await query.answer()


@router.message(CommandStart())
async def on_start_command(msg: Message, state: FSMContext):
    """При вводе /start проверяет, зарегистирован ли пользователь. Если нет, начинает процесс регистрации."""
    user_id = msg.from_user.id
    user = await context.repository.get_by_tgid(user_id)
    if user is not None:
        text = f'''Доброе время суток, {user.get_name(NameStyle.FirstPatronym)}.'''
        if user.role == UserRoles.UNVERIFIED:
            text += '\r\nВаша учётная запись ещё не подтверждена.'
        await msg.answer(text, parse_mode='markdown')
    else:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='Отмена', callback_data=f'register.cancel.{msg.from_user.id}')]
        ])
        text = (f'Вы ещё не зарегистрированы. Пожалуйста, введите своё ФИО, '
                f'разделённое пробелами или переносами строк (например, Иванов Иван Иванович или Петров Пётр).')
        await msg.answer(text, parse_mode='markdown', reply_markup=markup)
        await state.set_state(UserRegistrationStates.awaiting_name)
        context.log.debug('User %d attempting registration.', msg.from_user.id)


# region Регистрация и подтверждение пользователя
@router.callback_query(
    or_f(UserRegistrationStates.awaiting_confirmation, UserRegistrationStates.awaiting_name),
    lambda cb: cb.data.startswith('register.cancel.'))
async def user_cancel_button_handler(query: CallbackQuery, state: FSMContext):
    """Пользователь может отменить регистрацию до получения ответа от админа."""
    await state.set_state(None)
    await query.answer(text='Регистрация отменена.', show_alert=True)
    context.log.debug('User %d cancelled registration.', query.from_user.id)


@router.message(UserRegistrationStates.awaiting_name)
async def on_name_entered(msg: Message, state: FSMContext):
    """Обрабатывает ввод имени после регистрации."""
    text = msg.text.strip()
    url = msg.from_user.url
    parts = [word.strip() for word in text.split('\n')] if '\n' in text else text.split()
    if len(parts) == 1:
        user = dict(firstname=parts[0], patronym='', lastname='')
    elif len(parts) == 2:
        user = dict(firstname=parts[1], patronym='', lastname=parts[0])
    else:
        user = dict(firstname=parts[1], patronym=' '.join(parts[2:]), lastname=parts[0])
    await state.set_state(UserRegistrationStates.awaiting_confirmation)
    u = SiteUser(tgid=msg.from_user.id, role=UserRoles.UNVERIFIED,
                 lastname=user['lastname'], firstname=user['firstname'], patronym=user['patronym'])
    admin = await context.repository.get_admin()
    if admin is None:
        context.log.warning('No site admin found! Automatically accepting new user %s ( %s ) as site admin.',
                            u.get_name(NameStyle.LastFirstPatronym), url)
        u.role = UserRoles.SITE_ADMIN
        await context.repository.store(u)
        await state.set_state(None)
        await msg.answer('Ого! Похоже, вы теперь админ...')
        return
    context.log.debug('Awaiting approval for user %s ( %s ) by the site admin.',
                      u.get_name(NameStyle.LastFirstPatronym), url)
    await context.repository.store(u)
    text = f'Пользователь ожидает подтверждения: {u.get_name(NameStyle.LastFirstPatronym)} ( {user["url"]} )'
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='\u2795 Подтвердить', callback_data=f'register.confirm:{u.tgid}'),
            InlineKeyboardButton(text='\u21a9 Сбросить', callback_data=f'register.reset:{u.tgid}'),
            InlineKeyboardButton(text='\u274c Заблокировать', callback_data=f'register.block:{u.tgid}'),
        ]
    ])
    await context.bot.send_message(admin.tgid, text, reply_markup=keyboard)
    await msg.answer('Спасибо за регистрацию. Подождите подтверждения вашей записи администратором.')


@router.callback_query(is_site_admin, lambda cb: cb.data.startswith('register.confirm:'))
async def admin_confirm_button_handler(query: CallbackQuery):
    """Администратор подтвердил регистрацию пользователя."""
    user_id = int(query.data[len('register.confirm:'):])
    user = await context.repository.get_by_tgid(user_id)
    if user is None or user.role != UserRoles.UNVERIFIED:
        await query.answer('Этот пользователь не ожидает регистрации!', show_alert=False)
    else:
        user.role = UserRoles.VERIFIED
        await context.repository.store(user)
        await context.set_state_for_user(user_id, None)
        await query.answer('Пользователь подтверждён.', show_alert=True)
        await context.bot.send_message(user_id, 'Ваша учётная запись подтверждена администратором.')


@router.callback_query(is_site_admin, lambda cb: cb.data.startswith('register.reset:'))
async def admin_reset_button_handler(query: CallbackQuery):
    """Администратор сбросил регистрацию пользователя."""
    user_id = int(query.data[len('register.reset:'):])
    user = await context.repository.get_by_tgid(user_id)
    if user is None or user.role != UserRoles.UNVERIFIED:
        await query.answer('Этот пользователь не ожидает регистрации!', show_alert=False)
    else:
        await context.repository.delete_by_tgid(user_id)
        await context.set_state_for_user(user_id, None)
        await query.answer('Регистрация пользователя отменена.', show_alert=True)
        await context.bot.send_message(user_id, 'Ваша регистрация отменена администратором.')


@router.callback_query(is_site_admin, lambda cb: cb.data.startswith('register.block:'))
async def admin_block_button_handler(query: CallbackQuery):
    """Администратор отменил регистрацию пользователя и заблокировал его."""
    user_id = int(query.data[len('register.block:'):])
    user = await context.repository.get_by_tgid(user_id)
    if user is None or user.role != UserRoles.UNVERIFIED:
        await query.answer('Этот пользователь не ожидает регистрации!', show_alert=False)
    else:
        user.role = UserRoles.BLOCKED
        await context.repository.store(user)
        await context.set_state_for_user(user_id, UserRegistrationStates.blocked)
        await query.answer('Пользователь заблокирован.', show_alert=True)
        await context.bot.send_message(user_id, 'Простите, но ваша учётная запись заблокирована администратором.')


@router.message(is_site_admin, Command('unverified'))
async def admin_list_unverified(msg: Message):
    """Выводит список неподтверждённых пользователей."""
    total = 0
    lines = []
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    async for user in await context.repository.get_all_with_role(UserRoles.UNVERIFIED):
        total += 1
        lines.append(f'[#{user.id}] {user.get_name(NameStyle.LastFirstPatronym)}: '
                     f'{user.registered:%Y-%m-%d %H:%M}; tg://user?id={user.tgid}')
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=f'\u2795 Подтвердить {user.get_name(NameStyle.LastFP)}',
                                 callback_data=f'register.confirm:{user.tgid}'),
            InlineKeyboardButton(text=f'\u21a9 Сбросить {user.get_name(NameStyle.LastFP)}',
                                 callback_data=f'register.reset:{user.tgid}'),
            InlineKeyboardButton(text=f'\u274c Заблокировать {user.get_name(NameStyle.LastFP)}',
                                 callback_data=f'register.block:{user.tgid}'),
        ])
    if total == 0:
        await context.bot.send_message(
            msg.from_user.id,
            'Сейчас нет ни одного пользователя, ожидающего подтверждения.'
        )
    else:
        await context.bot.send_message(msg.from_user.id, '\r\n'.join(lines), reply_markup=keyboard)
# endregion


# region Справка о командах

def all_message_handlers(dispatcher: Dispatcher) -> t.Iterable[HandlerObject]:
    """Перечисляет все обработчики сообщений, прямо или опосредованно зарегистрированные в диспетчере бота."""
    for r in dispatcher.chain_tail:
        yield from r.message.handlers


def all_filters(filters: t.Iterable[FilterObject]) -> t.Iterable[FilterObject]:
    """Распаковывает логические конструкции из фильтров, получая цепочку базовых фильтров."""
    for f in filters:
        if isinstance(f, (logic._OrFilter, logic._AndFilter)):  # noqa
            yield from all_filters(f.targets)
        elif isinstance(f, logic._InvertFilter):  # noqa
            pass  # yield from all_filters((f.target,))
        else:
            yield f


def prepare_command_list(dispatcher: Dispatcher) -> CommandsInfo:
    """Составляем список команд в диспетчере, получаем их описания из docstring, и раскидываем их по ролям."""
    commands: CommandsInfo = defaultdict(list)
    log = logging.getLogger('modules.users')
    log.debug('Making a list of all available commands...')
    log.debug('Dispatcher has %d subrouters.', len(dispatcher.sub_routers))
    for h in all_message_handlers(dispatcher):  # команды - это всегда сообщения
        log.debug('Processing %s()', h.callback.__qualname__)
        filters = list(all_filters(h.filters))
        if any(isinstance(f, State) for f in filters):
            log.debug('    %s() has a State filter, ignoring it', h.callback.__qualname__)
            continue  # игнорируем команды, требующие определённого состояния FSM
        command_filters: list[FilterObject] = [f for f in filters if isinstance(f.callback, Command)]
        if command_filters:
            if any(f.callback is is_site_admin for f in filters):
                roles = UserRoles.SITE_ADMIN,
            elif any(f.callback is is_registered for f in filters):
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
                        log.debug('    BotCommand "%s" defined for roles %r', info.command, roles)
                    elif isinstance(cmd_pattern, re.Pattern):
                        info = BotCommand(command=f'{cmd_pattern.pattern}', description=docstring)
                        log.debug('    Regexp command "%s" defined for roles %r', info.command, roles)
                    else:
                        info = BotCommand(command=f'{cmd_pattern}', description=docstring)
                        log.debug('    String command "%s" defined for roles %r', info.command, roles)
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
    role = await context.repository.get_role_by_tg_id(msg.from_user.id)
    text = [
        'Доступные вам команды:'
    ]
    for cmd, cmdhelp in context.commands[role]:
        text.append(f'/{cmd} - {cmdhelp}')
    await msg.reply('\r\n'.join(text))
# endregion
