"""Описывает модель задания (assignment) и ответа (submission) для кэша сущностей Moodle."""
from datetime import datetime

from sqlalchemy import ForeignKey, Sequence, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from .base import MoodleBase
from .course import MoodleCourse
from .users import MoodleUser

__all__ = ['MoodleAssignment', 'MoodleSubmission', 'MoodleSubmittedFile']


class MoodleAssignment(MoodleBase):
    __tablename__ = 'MoodleAssignments'
    id: Mapped[int] = mapped_column(primary_key=True, comment='ID задания')
    course_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleCourse.id, ondelete="cascade"),
        comment='ID курса, которому принадлежит задание')
    name: Mapped[str] = mapped_column(nullable=False, comment='Название задания')
    opening: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True, index=True,
                                              comment='Когда задание открывается')
    closing: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True, index=True,
                                              comment='Срок сдачи ответов на задание')
    cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True, index=True,
                                             comment='Когда задание закрывается')


class MoodleSubmission(MoodleBase):
    __tablename__ = 'MoodleSubmissions'
    id: Mapped[int] = mapped_column(primary_key=True, comment='ID ответа на задание')
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleAssignment.id, ondelete='cascade'),
        comment='ID задания на которое дан ответ',
        index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleUser.id, ondelete='cascade'),
        comment='ID пользователя, давшего ответ')
    updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True,
                                              comment='Момент последнего изменения')
    status: Mapped[str] = mapped_column(nullable=False, comment='Статус ответа')


class MoodleSubmittedFile(MoodleBase):
    __tablename__ = 'MoodleSubmittedFiles'
    id: Mapped[int] = mapped_column(Sequence('MoodleSubmittedFiles_id'), nullable=False,
                                    comment='Уникальный номер файла (не ID в Moodle)')
    submission_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleSubmission.id, ondelete='cascade'),
        primary_key=True,
        comment='ID ответа, к которому прикреплён этот файл')
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleAssignment.id, ondelete='cascade'),
        index=True,
        comment='ID задания, к ответу на которое прикреплён этот файл')
    user_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleUser.id, ondelete='cascade'),
        comment='ID пользователя, загрузившего этот файл')
    filename: Mapped[str] = mapped_column(primary_key=True, comment='Имя файла (возможно, с каталогом)')
    filesize: Mapped[int] = mapped_column(nullable=False, comment='Размер файла в байтах')
    mimetype: Mapped[str] = mapped_column(nullable=False, comment='MIME-тип файла')
    url: Mapped[str] = mapped_column(nullable=False, comment='URL для скачивания файла (потребуется токен)')
    uploaded: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True,
                                               comment='Когда файл был загружен')
