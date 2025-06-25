"""Описывает модель задания (assignment) и ответа (submission) для кэша сущностей Moodle."""
from datetime import datetime

from sqlalchemy import ForeignKey, Sequence
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import MoodleBase
from .course import MoodleCourse
from .users import MoodleUser

__all__ = ['MoodleAssignment', 'MoodleSubmission', 'MoodleSubmittedFile']


class MoodleAssignment(MoodleBase):
    __tablename__ = 'MoodleAssignments'
    id: Mapped[int] = mapped_column(primary_key=True, comment='ID задания')
    course_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleCourse.__tablename__+".id", cascade="all, delete-orphan"),
        comment='ID курса, которому принадлежит задание')
    course: Mapped[MoodleCourse] = relationship()
    name: Mapped[str] = mapped_column(nullable=False, comment='Название задания')
    opening: Mapped[datetime] = mapped_column(nullable=True, comment='Когда задание открывается', index=True)
    closing: Mapped[datetime] = mapped_column(nullable=True, comment='Срок сдачи ответов на задание', index=True)
    cutoff: Mapped[datetime] = mapped_column(nullable=True, comment='Когда задание закрывается', index=True)


class MoodleSubmission(MoodleBase):
    __tablename__ = 'MoodleSubmissions'
    id: Mapped[int] = mapped_column(primary_key=True, comment='ID ответа на задание')
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleAssignment.__tablename__+".id", cascade="all, delete-orphan"),
        comment='ID задания на которое дан ответ',
        index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleUser.__tablename__ + ".id", cascade="all, delete-orphan"),
        comment='ID пользователя, давшего ответ')
    updated: Mapped[datetime] = mapped_column(nullable=False, comment='Момент последнего изменения', index=True)
    status: Mapped[str] = mapped_column(nullable=False, comment='Статус ответа')
    files: Mapped[list['MoodleSubmittedFile']] = relationship()


class MoodleSubmittedFile(MoodleBase):
    __tablename__ = 'MoodleSubmittedFiles'
    id: Mapped[int] = mapped_column(Sequence('MoodleSubmittedFiles_id'), nullable=False,
                                    comment='Уникальный номер файла (не ID в Moodle)')
    submission_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleSubmission.__tablename__+".id", cascade="all, delete-orphan"),
        primary_key=True,
        comment='ID ответа, к которому прикреплён этот файл')
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleAssignment.__tablename__+".id", cascade="all, delete-orphan"),
        comment='ID задания, к ответу на которое прикреплён этот файл',
        index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey(MoodleUser.__tablename__+".id", cascade="all, delete-orphan"),
        comment='ID пользователя, загрузившего этот файл')
    filename: Mapped[str] = mapped_column(primary_key=True, comment='Имя файла (возможно, с каталогом)')
    filesize: Mapped[int] = mapped_column(nullable=False, comment='Размер файла в байтах')
    mimetype: Mapped[str] = mapped_column(nullable=False, comment='MIME-тип файла')
    url: Mapped[str] = mapped_column(nullable=False, comment='URL для скачивания файла (потребуется токен)')
    uploaded: Mapped[datetime] = mapped_column(nullable=False, index=True, comment='Когда файл был загружен')
    submission: Mapped[MoodleSubmission] = relationship(back_populates='files')