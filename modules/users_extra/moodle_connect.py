"""Реализует привязку учётной записи в Moodle."""
from datetime import timedelta

from aiogram.types import Message, CopyTextButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from .common import context, tgrouter
from modules.users import tg_is_registered, SiteUser
from modules.moodle import RMessage

__all__ = [
    'MOODLE_ATTACH_INTENT', 'handle_moodle_intent_code'
]


MOODLE_ATTACH_INTENT = 'user_moodle_attach'


@tgrouter.message(Command('moodle'), tg_is_registered)
async def handle_moodle_attach(msg: Message):
    """Позволяет привязать к вашей учётной записи учётную запись Moodle, или узнать привязанную."""
    user = await context.repository.get_by_tgid(msg.from_user.id)
    botusername = context.moodle.me.fullname
    botuserlink = f'{context.moodle.base_url}message/index.php?id={context.moodle.me.id}'
    if user.moodleid is not None:
        userlink = f'{context.moodle.base_url}user/profile.php?id={user.moodleid}'
        await msg.answer(f'К вашей учётной записи уже привязана учётная запись Moodle.\r\n'
                         f'{userlink}\r\n'
                         f'Используйте команду /moodle_detach чтобы отвязать её.')
    else:
        code, _expires = await context.repository.create_onetime_code(MOODLE_ATTACH_INTENT, user, timedelta(minutes=10))
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='Копировать код', copy_text=CopyTextButton(text=code))]
        ])
        await msg.answer(f'Чтобы привязать учётную запись Moodle, в течение 10 минут отправьте код `{code}` '
                         f'в личные сообщения пользователю {botusername} ( {botuserlink} ).',
                         parse_mode='markdown', reply_markup=markup)


@tgrouter.message(Command('moodle_detach'), tg_is_registered)
async def handle_moodle_detach(msg: Message):
    """Позволяет отвязать от вашей учётной записи учётную запись Moodle."""
    user = await context.repository.get_by_tgid(msg.from_user.id)
    if user.moodleid is not None:
        userlink = f'{context.moodle.base_url}user/profile.php?id={user.moodleid}'
        user.moodleid = None
        await context.repository.store(user)
        await msg.answer(f'Учётная запись {userlink} отвязана от вашей.')
    else:
        await msg.answer('К вашей учётной записи не привязана ни одна учётная запись Moodle.')


async def handle_moodle_intent_code(_intent: str, user: SiteUser, msg: RMessage) -> None:
    """Реагирует на отправленный в личку Moodle одноразовый код с нужным intent."""
    userlink = f'{context.moodle.base_url}user/profile.php?id={msg.useridfrom}'
    user.moodleid = msg.useridfrom
    await context.repository.store(user)
    await context.bot.send_message(
        user.tgid,
        text=f'Учётная запись "{msg.userfromfullname}" ( {userlink} ) успешно привязана к вашей.')
