"""Описывает модели курса Moodle и групп в курсе для кэша сущностей Moodle."""
from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .base import MoodleBase

__all__ = ['MoodleCourse', 'MoodleGroup']


class MoodleCourse(MoodleBase):
    __tablename__ = 'MoodleCourses'
    id: Mapped[int] = mapped_column(primary_key=True, comment='ID курса')
    shortname: Mapped[str] = mapped_column(nullable=False, comment='Короткое название курса')
    fullname: Mapped[str] = mapped_column(nullable=False, comment='Полное название курса')
    starts: Mapped[datetime] = mapped_column(nullable=True, comment='Когда курс открывается')
    ends: Mapped[datetime] = mapped_column(nullable=True, comment='Когда курс закрывается')
    last_seen: Mapped[datetime] = mapped_column(nullable=False, server_default='NOW()',
                                                comment='Когда курс упоминался последний раз')


class MoodleGroup(MoodleBase):
    __tablename__ = 'MoodleGroups'
    course_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleCourse.__tablename__+".id", ondelete="cascade"),
        primary_key=True, comment='ID курса, в котором описана группа')
    id: Mapped[int] = mapped_column(primary_key=True, comment='ID группы (уникальное в рамках сервера)')
    name: Mapped[str] = mapped_column(nullable=False, comment='Название группы')
