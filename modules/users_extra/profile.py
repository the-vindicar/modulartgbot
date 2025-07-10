"""Реализует профиль пользователя."""
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
import quart
import quart_auth

from .common import context, blueprint
from modules.users import SiteUser, UserRoles, web_is_registered, web_is_site_admin, SiteAuthUser


__all__ = []


class UserProfileForm(BaseModel):
    firstname: str = Field(
        min_length=1,
        pattern=r'^\S+$',
        json_schema_extra={
            'error_messages': {
                'min_length': 'Имя должно содержать хотя бы один символ.',
                'pattern': 'Имя не должно содержать пробелов.'
            }
        })
    patronym: str = Field(min_length=0)
    lastname: str = Field(
        min_length=0,
        pattern=r'^\S+$',
        json_schema_extra={
            'error_messages': {
                'pattern': 'Фамилия не должна содержать пробелов.'
            }
        })
    tgid: str = Field(
        default='',
        pattern=r'^\d*$',
        json_schema_extra={
            'error_messages': {
                'pattern': 'Telegram ID должен быть либо пустой строкой, либо записью tg id (123456789).'
            }
        })
    moodleid: str = Field(
        default='',
        pattern=r'^\d*$',
        json_schema_extra={
            'error_messages': {
                'pattern': 'Moodle ID должен быть либо пустой строкой, либо записью moodle user id (1234).'
            }
        })


@blueprint.route('/', methods=['GET', 'POST'])
@web_is_registered
async def user_profile():
    """Показывает профиль текущего пользователя и позволяет редактировать его."""
    current_user: SiteAuthUser = quart_auth.current_user  # type: ignore
    return await edit_user_profile(current_user.user, is_admin=current_user.is_admin)


@blueprint.get('/all')
@web_is_site_admin
async def full_user_list():
    """Показывает полный список пользователей."""
    users = await context.repository.get_all_by_roles(
        UserRoles.UNVERIFIED, inverted=True, order_by=(SiteUser.role.desc(), SiteUser.id.asc()))
    return await quart.render_template(
        'users_extra/userlist.html',
        users=users
    )


@blueprint.route('/<int:user_id>', methods=['GET', 'POST'])
@web_is_site_admin
async def other_user_profile(user_id: int):
    """Показывает профиль текущего пользователя и позволяет редактировать его."""
    user = await context.repository.get_by_id(user_id)
    return await edit_user_profile(user, is_admin=True)


async def edit_user_profile(user: SiteUser, is_admin: bool):
    """Показывает профиль пользователя и позволяет редактировать его."""
    if quart.request.method == 'POST':  # метод POST - обновляем профиль текущего пользователя
        adapter = TypeAdapter(UserProfileForm)
        raw_form = (await quart.request.form).to_dict()
        try:
            form: UserProfileForm = adapter.validate_python(raw_form)  # type: ignore
        except ValidationError as err:
            err: ValidationError
            for ed in err.errors():
                await quart.helpers.flash(ed['msg'])
            raw_form.setdefault('tgid', str(user.tgid) if user.tgid else '')
            raw_form.setdefault('moodleid', str(user.moodleid) if user.moodleid else '')
            return await quart.render_template(
                'users_extra/profile.html',
                admin_edit=is_admin,
                firstname=raw_form.get('firstname', ''),
                patronym=raw_form.get('patronym', ''),
                lastname=raw_form.get('lastname', ''),
                tgid=raw_form['tgid'],
                moodleid=raw_form['moodleid'],
                moodle_user_link='',
                user_profile_target=quart.url_for('.user_profile')
            )
        else:
            user.lastname = form.lastname
            user.firstname = form.firstname
            user.patronym = form.patronym
            if is_admin:
                user.tgid = int(form.tgid) if form.tgid else None
                user.moodleid = int(form.moodleid) if form.moodleid else None
            await context.repository.store(user)
            await quart.helpers.flash('Изменения сохранены.')

    return await quart.render_template(
        'users_extra/profile.html',
        admin_edit=is_admin,
        firstname=user.firstname,
        patronym=user.patronym,
        lastname=user.lastname,
        tgid=str(user.tgid) if user.tgid else '',
        moodleid=str(user.moodleid) if user.moodleid else '',
        moodle_user_link='',
        user_profile_target=quart.url_for('.user_profile')
    )
