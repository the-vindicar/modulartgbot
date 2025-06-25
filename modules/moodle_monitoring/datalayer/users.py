"""Описывает модели пользователя и роли для кэша сущностей Moodle."""
from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column

from .base import MoodleBase


__all__ = ['MoodleUser', 'MoodleRole']


class MoodleUser(MoodleBase):
    """Пользователь на сервере Moodle. Они определяются в пределах сервера в целом."""
    __tablename__ = 'MoodleUsers'
    id: Mapped[int] = mapped_column(primary_key=True, comment='ID пользователя')
    fullname: Mapped[str] = mapped_column(nullable=False, comment='Имя пользователя')
    email: Mapped[str | None] = mapped_column(nullable=True, comment='E-mail пользователя')
    last_seen: Mapped[datetime] = mapped_column(nullable=False, server_default='NOW()',
                                                comment='Когда пользователь упоминался последний раз')


class MoodleRole(MoodleBase):
    """Роли пользователей на сервере Moodle. Они определяются в пределах сервера в целом."""
    __tablename__ = 'MoodleRoles'
    id: Mapped[int] = mapped_column(primary_key=True, comment='ID роли')
    name: Mapped[str] = mapped_column(nullable=False, comment='Название роли')
