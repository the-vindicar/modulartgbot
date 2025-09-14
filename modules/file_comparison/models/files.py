"""Описания моделей данных о файлах, хранимых в БД, и их схожести."""
from datetime import datetime

from sqlalchemy import ForeignKeyConstraint, DateTime, VARCHAR, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column

from api import DBModel
from modules.moodle_monitoring.models import MoodleSubmittedFile


__all__ = ['FileInfoBase', 'FileDigest', 'FileWarning', 'FileComparison', 'DigestNameType', 'WarningNameType']
DigestNameType = VARCHAR(16)
WarningNameType = VARCHAR(64)


class FileInfoBase(DBModel):
    __abstract__ = True


class FileDigest(FileInfoBase):
    __tablename__ = 'file_digests'
    file_id: Mapped[int] = mapped_column(primary_key=True, comment='ID исходного файла')
    digest_type: Mapped[str] = mapped_column(DigestNameType, primary_key=True, comment='Тип дайджеста')
    user_id: Mapped[int] = mapped_column(nullable=False, comment='ID владельца файла')
    user_name: Mapped[str] = mapped_column(nullable=False, comment='Имя владельца файла')
    assignment_id: Mapped[int] = mapped_column(nullable=False, comment='ID задания')
    submission_id: Mapped[int] = mapped_column(nullable=False, comment='ID ответа на задание')
    file_name: Mapped[str] = mapped_column(nullable=False, comment='Имя файла')
    file_url: Mapped[str] = mapped_column(nullable=False, comment='Ссылка на скачивание файла')
    file_uploaded: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                    comment='Время загрузки файла')
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                              comment='Момент создания дайджеста')
    content: Mapped[bytes] = mapped_column(LargeBinary(), nullable=True,
                                           comment='Сжатое gzip содержимое дайджеста, если доступно.')
    __table_args__ = (
        ForeignKeyConstraint(
            columns=['file_id'],
            refcolumns=[MoodleSubmittedFile.id],
            ondelete='cascade'
        ),
    )


class FileWarning(FileInfoBase):
    __tablename__ = 'file_warnings'
    file_id: Mapped[int] = mapped_column(primary_key=True, comment='ID файла')
    warning_type: Mapped[str] = mapped_column(WarningNameType, primary_key=True, comment='Тип предупреждения')
    warning_info: Mapped[str] = mapped_column(nullable=False, comment='Текст предупреждения')
    __table_args__ = (
        ForeignKeyConstraint(
            columns=['file_id'],
            refcolumns=[MoodleSubmittedFile.id],
            ondelete='cascade'
        ),
    )


class FileComparison(FileInfoBase):
    __tablename__ = 'file_comparisons'
    older_file_id: Mapped[int] = mapped_column(primary_key=True, comment='ID оригинального файла')
    older_digest_type: Mapped[str] = mapped_column(DigestNameType, primary_key=True,
                                                   comment='Тип дайджеста оригинального файла')
    newer_file_id: Mapped[int] = mapped_column(primary_key=True, comment='ID сравниваемого файла')
    newer_digest_type: Mapped[str] = mapped_column(DigestNameType, primary_key=True,
                                                   comment='Тип дайджеста сравниваемого файла')
    similarity_score: Mapped[float] = mapped_column(nullable=False, comment='Степень сходства файлов, от 0 до 1')
    __table_args__ = (
        ForeignKeyConstraint(
            columns=['older_file_id', 'older_digest_type'],
            refcolumns=[FileDigest.file_id, FileDigest.digest_type],
            ondelete='cascade'
        ),
        ForeignKeyConstraint(
            columns=['newer_file_id', 'newer_digest_type'],
            refcolumns=[FileDigest.file_id, FileDigest.digest_type],
            ondelete='cascade'
        ),
    )
