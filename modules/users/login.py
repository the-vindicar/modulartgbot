"""Реализует форму входа на сайт, а также отправку кода для входа на сайт."""
from datetime import timedelta
from urllib.parse import urlparse

from aiogram.types import Message
from aiogram.filters import Command
import quart
import quart_auth

from .models import NameStyle
from .common import tg_is_registered, context, router, blueprint


__all__ = []
WEB_LOGIN_INTENT = 'web_login'


@router.message(tg_is_registered, Command('login'))
async def on_login_command(msg: Message):
    """Предоставляет одноразовый код для входа на сайт."""
    user = await context.repository.get_by_tgid(msg.from_user.id)
    if not user:
        context.log.warning('Somehow, user %s passed is_registered() test despite not being in the database!',
                            msg.from_user.url)
        return
    context.log.debug('User %s ( %s ) requested a login code.',
                      user.get_name(NameStyle.LastFP), msg.from_user.url)
    code, _expires = await context.repository.create_onetime_code(WEB_LOGIN_INTENT, user, timedelta(minutes=10))
    await msg.answer(f'Ваш код входа на сайт (истекает через 10 минут): {code}')


@blueprint.route('/login', methods=['GET', 'POST'])
async def login():
    """Показывает и обслуживает форму логина."""
    if quart.request.method == 'POST':  # метод POST - обрабатываем форму входа
        form = await quart.request.form
        return_url = form.get('return_url', '')
        try:
            code = str(form['code'])
            _intent, user = await context.repository.try_consume_onetime_code(code, intent=WEB_LOGIN_INTENT)
        except Exception as err:
            context.log.warning('Failed to check login code!', exc_info=err)
            user = None
        if user is None:  # такого кода нет, или он не для логина на сайт
            return await quart.render_template(
                'users/login.html',
                return_url=return_url,
                messages=['Введённый код неверен или устарел.'],
                login_form_target=quart.url_for('.login')
            )
        # код корректен
        user_id = str(user.id)
        quart_auth.login_user(quart_auth.AuthUser(user_id), remember=True)
        context.log.debug('User %s has logged in.', user.get_name(NameStyle.LastFP))
        # пробуем отредиректить пользователя на желаемый url
        parts = urlparse(return_url) if return_url else None
        if parts is not None and not parts.scheme and not parts.netloc:
            return quart.redirect(return_url)
        else:  # отсутствующий или подозрительный редирект... отредиректим на профиль
            return quart.redirect(quart.url_for('.user_profile'))
    else:  # метод GET - показываем форму входа
        return_url = quart.request.args.get('return_url', '')
        return await quart.render_template(
            'users/login.html',
            return_url=return_url,
            messages=[],
            login_form_target=quart.url_for('.login')
        )


@blueprint.route('/logout', methods=['GET', 'POST'])
def logout():
    """Реализует выход из учётной записи."""
    quart_auth.logout_user()
    referer = quart.request.headers.get('Referer', '')
    if referer:
        return quart.redirect(referer)
    else:
        return quart.redirect('/')
