"""Описывает модели участника курса, ролей участника и групп участника для кэша сущностей Moodle."""
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import MoodleBase
from .users import MoodleUser, MoodleRole
from .course import MoodleCourse, MoodleGroup


__all__ = ['MoodleParticipant', 'MoodleParticipantGroups', 'MoodleParticipantRoles']


class MoodleParticipant(MoodleBase):
    __tablename__ = 'MoodleParticipants'
    course_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleCourse.__tablename__+".id", cascade="all, delete-orphan"),
        primary_key=True, comment='ID курса')
    user_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleUser.__tablename__ + ".id", cascade="all, delete-orphan"),
        primary_key=True, comment='ID пользователя-участника')
    course: Mapped[MoodleCourse] = relationship(back_populates='participants')
    user: Mapped[MoodleUser] = relationship()
    roles: Mapped[list[MoodleRole]] = relationship()
    groups: Mapped[list[MoodleGroup]] = relationship()


class MoodleParticipantRoles(MoodleBase):
    __tablename__ = 'MoodleParticipantRoles'
    course_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleParticipant.__tablename__+".course_id", cascade="all, delete-orphan"),
        primary_key=True, comment='ID курса')
    user_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleParticipant.__tablename__ + ".user_id", cascade="all, delete-orphan"),
        primary_key=True, comment='ID пользователя-участника')
    role_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleRole.__tablename__ + ".id", cascade="all, delete-orphan"),
        primary_key=True, comment='ID роли')
    participant: Mapped[MoodleParticipant] = relationship(back_populates='roles')
    role: Mapped[MoodleRole] = relationship()


class MoodleParticipantGroups(MoodleBase):
    __tablename__ = 'MoodleParticipantGroups'
    course_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleParticipant.__tablename__+".course_id", cascade="all, delete-orphan"),
        primary_key=True, comment='ID курса')
    user_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleParticipant.__tablename__ + ".user_id", cascade="all, delete-orphan"),
        primary_key=True, comment='ID пользователя-участника')
    group_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleGroup.__tablename__ + ".id", cascade="all, delete-orphan"),
        primary_key=True, comment='ID группы')
    participant: Mapped[MoodleParticipant] = relationship(back_populates='groups')
    group: Mapped[MoodleGroup] = relationship()
