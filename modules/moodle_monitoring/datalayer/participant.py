"""Описывает модели участника курса, ролей участника и групп участника для кэша сущностей Moodle."""
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .base import MoodleBase
from .users import MoodleUser, MoodleRole
from .course import MoodleCourse, MoodleGroup


__all__ = ['MoodleParticipant', 'MoodleParticipantGroups', 'MoodleParticipantRoles']


class MoodleParticipant(MoodleBase):
    __tablename__ = 'MoodleParticipants'
    course_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleCourse.__tablename__+".id", ondelete="cascade"),
        primary_key=True, comment='ID курса')
    user_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleUser.__tablename__ + ".id", ondelete="cascade"),
        primary_key=True, comment='ID пользователя-участника')


class MoodleParticipantRoles(MoodleBase):
    __tablename__ = 'MoodleParticipantRoles'
    course_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleParticipant.__tablename__+".course_id", ondelete="cascade"),
        primary_key=True, comment='ID курса')
    user_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleParticipant.__tablename__ + ".user_id", ondelete="cascade"),
        primary_key=True, comment='ID пользователя-участника')
    role_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleRole.__tablename__ + ".id", ondelete="cascade"),
        primary_key=True, comment='ID роли')


class MoodleParticipantGroups(MoodleBase):
    __tablename__ = 'MoodleParticipantGroups'
    course_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleParticipant.__tablename__+".course_id", ondelete="cascade"),
        primary_key=True, comment='ID курса')
    user_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleParticipant.__tablename__ + ".user_id", ondelete="cascade"),
        primary_key=True, comment='ID пользователя-участника')
    group_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleGroup.__tablename__ + ".id", ondelete="cascade"),
        primary_key=True, comment='ID группы')
