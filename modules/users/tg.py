"""Реализует простую регистрацию через Telegram с подтверждением учётки админом."""
import dataclasses
import logging

from aiogram import Router, Dispatcher, Bot
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import StorageKey
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command, CommandStart, or_f

from .models import SiteUser, UserRoles, UserRepository


__all__ = [
    'context', 'router',
    'is_registered', 'is_site_admin'
]


@dataclasses.dataclass
class RegistrationContext:
    repository: UserRepository = None
    bot: Bot = None
    dispatcher: Dispatcher = None
    log: logging.Logger = None

    async def set_state_for_user(self, user_id: int, state: str | State | None, **data_updates) -> None:
        key = StorageKey(bot_id=self.bot.id, chat_id=user_id, user_id=user_id,
                         thread_id=None, business_connection_id=None)
        await self.dispatcher.storage.set_state(key, state)
        if data_updates:
            await self.dispatcher.storage.update_data(key, **data_updates)


context: RegistrationContext = RegistrationContext()
router: Router = Router(name='users')


class UserRegistrationStates(StatesGroup):
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
        text = f'''Доброе время суток, {user.partname}.'''
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
        context.log.warning('No site admin found! Automatically accepting new user %s (%s) as site admin.',
                            u.fullname_last, url)
        u.role = UserRoles.SITE_ADMIN
        await context.repository.store(u)
        await state.set_state(None)
        await msg.answer('Ого! Похоже, вы теперь админ...')
        return
    context.log.debug('Awaiting approval for user %s ( %s ) by the site admin.',
                      u.fullname_last, url)
    await context.repository.store(u)
    text = f'Пользователь ожидает подтверждения: {u.fullname_last} ( {user["url"]} )'
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
async def admin_confirm_button_handler(query: CallbackQuery):
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
    async for user in context.repository.get_all_with_role(UserRoles.UNVERIFIED):
        total += 1
        lines.append(f'[#{user.id}] {user.fullname_first}: {user.registered:%Y-%m-%d %H:%M}; tg://user?id={user.tgid}')
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=f'\u2795 Подтвердить {user.shortname_first}',
                                 callback_data=f'register.confirm:{user.tgid}'),
            InlineKeyboardButton(text=f'\u21a9 Сбросить {user.shortname_first}',
                                 callback_data=f'register.reset:{user.tgid}'),
            InlineKeyboardButton(text=f'\u274c Заблокировать {user.shortname_first}',
                                 callback_data=f'register.block:{user.tgid}'),
        ])
    if total == 0:
        await context.bot.send_message(
            msg.from_user.id,
            'Сейчас нет ни одного пользователя, ожидающего подтверждения.'
        )
    else:
        await context.bot.send_message(msg.from_user.id, '\r\n'.join(lines), reply_markup=keyboard)
