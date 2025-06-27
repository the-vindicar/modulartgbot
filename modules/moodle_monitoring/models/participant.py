"""Описывает модели участника курса, ролей участника и групп участника для кэша сущностей Moodle."""
from sqlalchemy import ForeignKey, ForeignKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import MoodleBase
from .users import MoodleUser, MoodleRole
from .course import MoodleCourse, MoodleGroup


__all__ = ['MoodleParticipant', 'MoodleParticipantGroups', 'MoodleParticipantRoles']


class MoodleParticipant(MoodleBase):
    __tablename__ = 'MoodleParticipants'
    course_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleCourse.id, ondelete='cascade'),
        primary_key=True, comment='ID курса')
    user_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleUser.id, ondelete='cascade'),
        primary_key=True, comment='ID пользователя-участника')


class MoodleParticipantRoles(MoodleBase):
    __tablename__ = 'MoodleParticipantRoles'
    course_id: Mapped[int] = mapped_column(primary_key=True, comment='ID курса')
    user_id: Mapped[int] = mapped_column(primary_key=True, comment='ID пользователя-участника')
    role_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleRole.id, ondelete='cascade'),
        primary_key=True, comment='ID роли')
    __table_args__ = (
        ForeignKeyConstraint(
            columns=['course_id', 'user_id'],
            refcolumns=[MoodleParticipant.course_id, MoodleParticipant.user_id],
            ondelete='cascade'
        ),
    )


class MoodleParticipantGroups(MoodleBase):
    __tablename__ = 'MoodleParticipantGroups'
    course_id: Mapped[int] = mapped_column(primary_key=True, comment='ID курса')
    user_id: Mapped[int] = mapped_column(primary_key=True, comment='ID пользователя-участника')
    group_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleGroup.id, ondelete="cascade"),
        primary_key=True, comment='ID группы')
    __table_args__ = (
        ForeignKeyConstraint(
            columns=['course_id', 'user_id'],
            refcolumns=[MoodleParticipant.course_id, MoodleParticipant.user_id],
            ondelete='cascade'
        ),
    )
