"""Класс-репозиторий, занимающийся доступом к таблицам данных, и вспомогательные датаклассы."""
import typing as t
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
import logging

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.dialects.postgresql import insert as upsert, aggregate_order_by
from sqlalchemy.orm import aliased

from .files import *
from modules.moodle_monitoring.models import MoodleSubmittedFile, MoodleUser


__all__ = [
    'FileToCompute', 'DigestPair',
    'FileDetails', 'FileSimilarityDetails', 'FileWarningDetails',
    'FileDataRepository'
]


@dataclass
class FileToCompute:
    """Файл, подлежащий обработке."""
    file_id: int
    digest_type: str
    user_id: int
    user_name: str
    assignment_id: int
    submission_id: int
    file_name: str
    file_url: str
    file_uploaded: datetime
    mimetype: str
    file_size: int
    digest_types: frozenset[str]


@dataclass
class DigestPair:
    """Пара файлов для сравнения."""
    older_id: int
    older_content: bytes
    newer_id: int
    newer_content: bytes
    digest_type: str


@dataclass
class FileSimilarityDetails:
    """Описывает файл, схожий с указанным."""
    submission_id: int
    user_id: int
    user_name: str
    file_name: str
    file_url: str
    similarity_score: float


@dataclass
class FileWarningDetails:
    """Описывает особое замечание о файле."""
    type: str
    message: str


@dataclass
class FileDetails:
    """Сведения об указанном файле."""
    name: str
    is_known: bool
    earlier_files: list[FileSimilarityDetails] = field(default_factory=list)
    later_files: list[FileSimilarityDetails] = field(default_factory=list)
    warnings: list[FileWarningDetails] = field(default_factory=list)


class FileDataRepository:
    """Предоставляет услуги по чтению и записи сведений о содержимом файлов."""
    TZ = timezone.utc

    def __init__(self, engine: AsyncEngine, log: logging.Logger):
        self.__sessionmaker = async_sessionmaker(bind=engine, class_=AsyncSession,
                                                 autoflush=True, expire_on_commit=False)
        self.__log = log

    async def create_tables(self) -> None:
        """Создаёт таблицы, необходимые для работы репозитория."""
        engine: AsyncEngine = self.__sessionmaker.kw['bind']
        async with engine.connect() as conn:
            await conn.run_sync(FileInfoBase.metadata.create_all)
            await conn.commit()

    async def stream_files_with_missing_digests(self,
                                                available_digest_types: t.Collection[str],
                                                max_age: t.Optional[timedelta] = None,
                                                max_size: t.Optional[int] = None
                                                ) -> t.AsyncIterable[FileToCompute]:
        """Определяет, у каких хранимых файлов нет данных по заданном дайджесту.

        :param available_digest_types: Имена доступных типов дайджестов.
        :param max_age: Максимальный возраст файла, или None для обработки всех файлов.
        :param max_size: Максимальный размер файла в байтах, или None для любого размера.
        :returns: Последовательность описаний файлов. Записи для одного и того же файла идут подряд.
        """
        available_set = frozenset(available_digest_types)
        if not available_set:
            self.__log.warning('Requested missing digests with NO digest types specified.')
            return
        async with self.__sessionmaker() as session:
            # загружаем сведения о дайджестах указанных файлов
            # столбец-агрегат возвращает массив типов дайджестов, которые рассчитаны для этого файла
            existing_digests_column = func.array_agg(aggregate_order_by(
                FileDigest.digest_type, FileDigest.digest_type.asc()
            )).label('existing_digests')
            subquery = (
                select(
                    MoodleSubmittedFile.id,
                    existing_digests_column,
                )
                .select_from(MoodleSubmittedFile)
                .join(FileDigest, onclause=and_(
                    FileDigest.file_id == MoodleSubmittedFile.id,
                    FileDigest.digest_type.in_(available_digest_types)
                ))
                .group_by(MoodleSubmittedFile.id)
            )
            if max_age is not None:
                oldest = datetime.now(self.TZ) - max_age
                subquery = subquery.where(MoodleSubmittedFile.uploaded >= oldest)
            if max_size is not None:
                subquery = subquery.where(MoodleSubmittedFile.filesize <= max_size)
            subquery = subquery.subquery('digests_for_files')
            stmt = (
                select(
                    MoodleSubmittedFile,
                    MoodleUser.fullname,
                    subquery.c.existing_digests
                )
                .select_from(MoodleSubmittedFile)
                .join(MoodleUser, onclause=(MoodleUser.id == MoodleSubmittedFile.user_id))
                .outerjoin(subquery, onclause=(subquery.c.id == MoodleSubmittedFile.id))
            )
            async for f, username, has_digests in await session.stream(stmt):
                f: MoodleSubmittedFile
                username: str
                has_digests: list[str]
                missing_set = available_set.difference(has_digests) if has_digests else available_set
                if missing_set:
                    self.__log.debug('    File %s is missing: %s', f.filename, ', '.join(missing_set))
                    target = FileToCompute(
                        file_id=f.id,
                        digest_type='',
                        user_id=f.user_id,
                        user_name=username,
                        assignment_id=f.assignment_id,
                        submission_id=f.submission_id,
                        file_name=f.filename,
                        file_url=f.url,
                        file_size=f.filesize,
                        file_uploaded=f.uploaded,
                        mimetype=f.mimetype,
                        digest_types=missing_set
                    )
                    yield target

    async def store_digests(self, digests: t.Collection[FileDigest]) -> None:
        """Сохраняет дайджесты файлов для последующего использования."""
        data = [
            dict(file_id=d.file_id, assignment_id=d.assignment_id, submission_id=d.submission_id,
                 user_id=d.user_id, user_name=d.user_name,
                 file_name=d.file_name, file_url=d.file_url, file_uploaded=d.file_uploaded,
                 digest_type=d.digest_type, created=d.created.astimezone(self.TZ), content=d.content)
            for d in digests
        ]
        if not data:
            return
        async with self.__sessionmaker() as session:
            stmt = upsert(FileDigest)
            stmt = stmt.on_conflict_do_update(
                index_elements=[FileDigest.file_id, FileDigest.digest_type],
                set_={
                    FileDigest.created: stmt.excluded.created,
                    FileDigest.content: stmt.excluded.content,
                }
            )
            await session.execute(stmt, data)
            await session.commit()

    async def stream_missing_comparisons(self) -> t.AsyncIterable[DigestPair]:
        """
        Определяет пары дайджестов, которые нужно сравнить между собой, но для которых ещё нет данных о сравнении.
        Пары дайджестов гарантированно имеют один и тот же тип, относятся к одному и тому же заданию (assignment),
        получены от разных пользователей, и новый файл в паре новее старого.
        Последовательность будет отсортирована так, чтобы все сравнения для одного и того же файла шли подряд

        :returns: Последовательность пар дайджестов.
        """
        async with self.__sessionmaker() as session:
            OldDigest = t.cast(t.Type[FileDigest], aliased(FileDigest, name='OldDigest'))
            stmt = (
                select(FileDigest, OldDigest)
                .select_from(FileDigest)
                .join(OldDigest, onclause=and_(  # ищем пары потенциально сравниваемых дайджестов:
                    (FileDigest.assignment_id == OldDigest.assignment_id),  # из одного и того же задания
                    (FileDigest.digest_type == OldDigest.digest_type),  # дайджесты одного типа
                    (FileDigest.submission_id != OldDigest.submission_id),  # от разных пользователей
                    (FileDigest.file_uploaded > OldDigest.file_uploaded),  # новый файл в паре позднее старого
                ))
                .outerjoin(FileComparison, onclause=and_(  # подсоединяем таблицу сравнений
                    # запись должна соединять два указанных файла
                    (FileDigest.file_id == FileComparison.newer_file_id),
                    (OldDigest.file_id == FileComparison.older_file_id),
                    # по указанному типу дайджеста
                    (FileDigest.digest_type == FileComparison.newer_digest_type),
                    (OldDigest.digest_type == FileComparison.older_digest_type),
                ))
                # ищем пары дайджестов, у которых нет записи о сравнении
                .where(FileComparison.similarity_score.is_(None))
                .order_by(FileDigest.file_id)
            )
            async for new_digest, old_digest in await session.stream(stmt):
                new_digest: FileDigest
                old_digest: FileDigest
                yield DigestPair(
                    older_id=old_digest.file_id, newer_id=new_digest.file_id, digest_type=old_digest.digest_type,
                    older_content=old_digest.content, newer_content=new_digest.content
                )

    async def store_comparisons(self, comparisons: t.Collection[FileComparison]) -> None:
        """Сохраняет результат сравнения файлов для последующего использования."""
        data = [
            dict(older_file_id=c.older_file_id, older_digest_type=c.older_digest_type,
                 newer_file_id=c.newer_file_id, newer_digest_type=c.newer_digest_type,
                 similarity_score=c.similarity_score)
            for c in comparisons
        ]
        if not data:
            return
        async with self.__sessionmaker() as session:
            stmt = upsert(FileComparison)
            stmt = stmt.on_conflict_do_update(
                index_elements=[FileComparison.older_file_id, FileComparison.older_digest_type,
                                FileComparison.newer_file_id, FileComparison.newer_digest_type],
                set_={
                    FileComparison.similarity_score: stmt.excluded.similarity_score,
                }
            )
            await session.execute(stmt, data)
            await session.commit()

    async def store_warnings(self, warnings: t.Collection[FileWarning]) -> None:
        """Сохраняет примечания/преджупреждения к файлам для последующего использования."""
        data = [
            dict(file_id=w.file_id, warning_type=w.warning_type, warning_info=w.warning_info)
            for w in warnings
        ]
        if not data:
            return
        async with self.__sessionmaker() as session:
            stmt = upsert(FileWarning)
            stmt = stmt.on_conflict_do_update(
                index_elements=[FileWarning.file_id, FileWarning.warning_type],
                set_={
                    FileWarning.warning_info: stmt.excluded.warning_info,
                }
            )
            await session.execute(stmt, data)
            await session.commit()

    async def get_files_by_submission(self, submission_id: int, filenames: t.Collection[str],
                                      min_score: float, max_similar: int,
                                      also_get_later_files: bool) -> list[FileDetails]:
        """
        Получает сведения о файлах с указанными именами, входящих в указанный ответ.

        :param submission_id: ID ответа на вопрос, в котором находятся искомые файлы.
        :param filenames: Имена искомых файлов (чувствительно к регистру!)
        :param min_score: Выбирать файлы со степенью сходства не менее указанной.
        :param max_similar: Возвращать не более указанного числа файлов с наибольшим сходством.
        :param also_get_later_files: Если истина, в ответ будут также добавлены сведения о более поздних файлах.
        """
        if not filenames:
            return []
        results: list[FileDetails] = []
        async with self.__sessionmaker() as session:
            stmt = (
                select(MoodleSubmittedFile.id, MoodleSubmittedFile.filename)
                .where(
                    (MoodleSubmittedFile.submission_id == submission_id),
                    (MoodleSubmittedFile.filename.in_(filenames)),
                )
            )
            found = []
            by_id: dict[int, FileDetails] = {}
            for fid, fname in (await session.execute(stmt)).scalars():
                details = FileDetails(name=fname, is_known=True)
                results.append(details)
                found.append(fname)
                by_id[fid] = details
            stmt = (
                select(FileWarning)
                .where(FileWarning.file_id.in_(list(by_id.keys())))
            )
            for warn in (await session.execute(stmt)).scalars():
                by_id[warn.file_id].warnings.append(
                    FileWarningDetails(type=warn.warning_type, message=warn.warning_info)
                )
            row_number_column = func.row_number().over(
                partition_by=FileComparison.newer_file_id,
                order_by=FileComparison.similarity_score.desc()
            ).label('row_number')

            stmt = (
                select(
                    FileComparison.similarity_score,
                    FileDigest.digest_type,
                    FileDigest.file_id,
                    FileDigest.file_name,
                    FileDigest.file_url,
                    FileDigest.user_id,
                    FileDigest.user_name,
                    FileDigest.submission_id,
                    row_number_column
                )
                .select_from(FileDigest)
                .join(FileComparison, onclause=and_(
                    (FileComparison.similarity_score >= min_score),
                    (FileComparison.newer_file_id.in_(list(by_id.keys()))),
                    (FileComparison.older_file_id == FileDigest.file_id),
                    (FileComparison.older_digest_type == FileDigest.digest_type),
                ))
                .where(row_number_column <= max_similar)
                .order_by(FileComparison.similarity_score.desc())
            )
            for score, dtype, fid, fname, furl, uid, uname, subid in await session.execute(stmt):
                details = by_id[fid]
                if len(details.earlier_files) < max_similar:
                    simdetails = FileSimilarityDetails(
                        submission_id=subid,
                        file_name=fname,
                        file_url=furl,
                        user_id=uid,
                        user_name=uname,
                        similarity_score=score
                    )
                    details.earlier_files.append(simdetails)
            if also_get_later_files:
                stmt = (
                    select(
                        FileComparison.similarity_score,
                        FileDigest.digest_type,
                        FileDigest.file_id,
                        FileDigest.file_name,
                        FileDigest.file_url,
                        FileDigest.user_id,
                        FileDigest.user_name,
                        FileDigest.submission_id,
                        row_number_column
                    )
                    .select_from(FileDigest)
                    .join(FileComparison, onclause=and_(
                        (FileComparison.similarity_score >= min_score),
                        (FileComparison.older_file_id.in_(list(by_id.keys()))),
                        (FileComparison.newer_file_id == FileDigest.file_id),
                        (FileComparison.newer_digest_type == FileDigest.digest_type),
                    ))
                    .where(row_number_column <= max_similar)
                    .order_by(FileComparison.similarity_score.desc())
                )
                for score, dtype, fid, fname, furl, uid, uname, subid in await session.execute(stmt):
                    details = by_id[fid]
                    if len(details.later_files) < max_similar:
                        simdetails = FileSimilarityDetails(
                            submission_id=subid,
                            file_name=fname,
                            file_url=furl,
                            user_id=uid,
                            user_name=uname,
                            similarity_score=score
                        )
                        details.later_files.append(simdetails)
        for fname in filenames:
            if fname not in found:
                results.append(FileDetails(name=fname, is_known=False))
        return results
