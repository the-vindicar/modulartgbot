"""Реализует процесс регистрации пользователя."""
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command, CommandStart, or_f

from .models import SiteUser, UserRoles, NameStyle
from .common import context, router, tg_is_site_admin


__all__ = []


class UserRegistrationStates(StatesGroup):
    """Состояния при регистрации пользователя."""
    awaiting_name = State()
    awaiting_confirmation = State()
    blocked = State()


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
    """Позволяет зарегистрироваться."""
    user_id = msg.from_user.id
    user = await context.repository.get_by_tgid(user_id)
    if user is not None:
        text = f'''Доброе время суток, {user.get_name(NameStyle.FirstPatronym)}.'''
        if user.role == UserRoles.UNVERIFIED:
            text += '\r\nВаша учётная запись ещё не подтверждена.'
        await msg.answer(text)
    else:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='Отмена', callback_data=f'register.cancel.{msg.from_user.id}')]
        ])
        text = (f'Вы ещё не зарегистрированы. Пожалуйста, введите своё ФИО, '
                f'разделённое пробелами или переносами строк (например, Иванов Иван Иванович или Петров Пётр).')
        await msg.answer(text, reply_markup=markup)
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


@router.callback_query(tg_is_site_admin, lambda cb: cb.data.startswith('register.confirm:'))
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


@router.callback_query(tg_is_site_admin, lambda cb: cb.data.startswith('register.reset:'))
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


@router.callback_query(tg_is_site_admin, lambda cb: cb.data.startswith('register.block:'))
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


@router.message(tg_is_site_admin, Command('unverified'))
async def admin_list_unverified(msg: Message):
    """Выводит список неподтверждённых пользователей."""
    total = 0
    lines = []
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for user in await context.repository.get_all_by_roles(UserRoles.UNVERIFIED,
                                                          order_by=(SiteUser.registered.desc(),)):
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
