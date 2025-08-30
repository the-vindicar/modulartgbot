"""Реализует репозиторий для работы с локальным кэшем сущностей Moodle."""
import typing as t
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import logging

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, AsyncSession
from sqlalchemy import select, delete, or_, and_, tuple_, func
from sqlalchemy.dialects.postgresql import insert as upsert

from modules.moodle import (Course, Participant, User, Role, Group, Assignment, Submission, SubmittedFile,
                            user_id, course_id, assignment_id)
from .base import MoodleBase
from .course import *
from .users import *
from .participant import *
from .assignment import *


__all__ = ['MoodleRepository']


# noinspection PyMethodMayBeStatic
class MoodleRepository:
    """Предоставляет услуги по чтению и записи локального кэша сущностей Moodle."""
    TZ = timezone.utc

    def __init__(self, engine: AsyncEngine, log: logging.Logger):
        self.__sessionmaker = async_sessionmaker(bind=engine, class_=AsyncSession,
                                                 autoflush=True, expire_on_commit=False)
        self.__log = log

    async def create_tables(self) -> None:
        """Создаёт таблицы, необходимые для работы репозитория."""
        engine: AsyncEngine = self.__sessionmaker.kw['bind']
        async with engine.connect() as conn:
            await conn.run_sync(MoodleBase.metadata.create_all)
            await conn.commit()

    # region Курсы
    async def load_courses(self, course_ids: t.Collection[course_id]) -> list[Course]:
        """Загружает список курсов с указанными id.
        :param course_ids: Коллекция идентификаторов курсов.
        :returns: Список объектов Course."""
        if not course_ids:
            return []
        participants: dict[int, dict[int, tuple[str, str, list[Role], list[Group]]]] = defaultdict(dict)
        async with self.__sessionmaker() as session:
            # загружаем пользователей курсов
            stmt = (
                select(
                    MoodleParticipant.course_id,
                    MoodleUser.id, MoodleUser.fullname, MoodleUser.email
                )
                .select_from(MoodleParticipant)
                .join(MoodleUser, onclause=MoodleUser.id == MoodleParticipant.user_id)
                .where(MoodleParticipant.course_id.in_(course_ids))
            )
            async for cid, uid, uname, uemail in await session.stream(stmt):
                participants[cid][uid] = (uname, uemail, [], [])
            # загружаем роли пользователей
            stmt = (
                select(
                    MoodleParticipantRoles.course_id, MoodleParticipantRoles.user_id,
                    MoodleRole.id, MoodleRole.name
                )
                .select_from(MoodleParticipantRoles)
                .join(MoodleRole, onclause=MoodleParticipantRoles.role_id == MoodleRole.id)
                .where(MoodleParticipantRoles.course_id.in_(course_ids))
            )
            async for cid, uid, rid, rname in await session.stream(stmt):
                p = participants[cid].get(uid, None)
                if p is not None:
                    p[2].append(Role(rid, rname))
            # загружаем группы пользователей
            stmt = (
                select(
                    MoodleParticipantGroups.course_id, MoodleParticipantGroups.user_id,
                    MoodleGroup.id, MoodleGroup.name
                )
                .select_from(MoodleParticipantGroups)
                .join(MoodleGroup, onclause=MoodleParticipantGroups.group_id == MoodleGroup.id)
                .where(MoodleParticipantGroups.course_id.in_(course_ids))
            )
            async for cid, uid, gid, gname in await session.stream(stmt):
                p = participants[cid].get(uid, None)
                if p is not None:
                    p[3].append(Group(rid, rname))
            # загружаем курсы
            stmt = (
                select(MoodleCourse.id, MoodleCourse.fullname, MoodleCourse.shortname,
                       MoodleCourse.starts, MoodleCourse.ends)
                .select_from(MoodleCourse)
                .where(MoodleCourse.id.in_(course_ids))
            )
            courses: list[Course] = []
            async for cid, cfull, cshort, cstart, cend in await session.stream(stmt):
                parts = [
                    Participant(user=User(id=user_id(uid), name=uname, email=uemail),
                                roles=tuple(uroles), groups=tuple(ugroups))
                    for uid, (uname, uemail, uroles, ugroups) in participants[cid].items()
                ]
                course = Course(
                    id=course_id(cid),
                    shortname=cshort,
                    fullname=cfull,
                    participants=tuple(parts),
                    starts=cstart,
                    ends=cend
                )
                courses.append(course)
        return courses

    async def _store_roles_for(self, session: AsyncSession, courses: t.Collection[Course]) -> None:
        """Сохраняет роли, встреченные в указанных курсах."""
        all_roles = set(r for c in courses for p in c.participants for r in p.roles)
        if not all_roles:
            return
        stmt = upsert(MoodleRole)
        stmt = stmt.on_conflict_do_update(index_elements=[MoodleRole.id], set_={
            MoodleRole.name: stmt.excluded.name
        })
        await session.execute(
            stmt,
            [{'id': r.id, 'name': r.name} for r in all_roles]
        )
        await session.commit()

    async def _store_groups_for(self, session: AsyncSession, courses: t.Collection[Course]) -> None:
        """Сохраняет группы, встреченные в указанных курсах.
        Если группа, связанная с курсом, есть в БД, но не упоминается в курсе, она будет удалена из БД."""
        cids = set(c.id for c in courses)
        groups = set((c.id, g) for c in courses for p in c.participants for g in p.groups)
        if not groups:
            return
        stmt = upsert(MoodleGroup)
        stmt = stmt.on_conflict_do_update(index_elements=[MoodleGroup.id], set_={
            MoodleGroup.course_id: stmt.excluded.course_id,
            MoodleGroup.name: stmt.excluded.name
        })
        await session.execute(
            stmt,
            [{'id': g.id, 'name': g.name, 'course_id': cid} for cid, g in groups]
        )
        course_groups = set((cid, g.id) for cid, g in groups)
        stmt = delete(MoodleGroup).where(
            MoodleGroup.course_id.in_(cids),
            tuple_(MoodleGroup.course_id, MoodleGroup.id).notin_(course_groups))
        await session.execute(stmt)
        await session.commit()

    async def _store_participants_for(self, session: AsyncSession, courses: t.Collection[Course]) -> None:
        """Сохраняет участников указанных курсов, их роли и группы."""
        cids = set(c.id for c in courses)
        participation = set((c.id, p.user.id) for c in courses for p in c.participants)
        if participation:
            stmt = upsert(MoodleParticipant)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=[MoodleParticipant.course_id, MoodleParticipant.user_id]
            )
            await session.execute(stmt, [
                {'course_id': cid, 'user_id': uid}
                for cid, uid in participation
            ])
        stmt = delete(MoodleParticipant).where(MoodleParticipant.course_id.in_(cids))
        if participation:
            stmt = stmt.where(tuple_(MoodleParticipant.course_id, MoodleParticipant.user_id).notin_(participation))
        await session.execute(stmt)

        participant_roles = set((c.id, p.user.id, r.id) for c in courses for p in c.participants for r in p.roles)
        if participant_roles:
            stmt = upsert(MoodleParticipantRoles)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=[MoodleParticipantRoles.course_id, MoodleParticipantRoles.user_id,
                                MoodleParticipantRoles.role_id]
            )
            await session.execute(stmt, [
                {'course_id': cid, 'user_id': uid, 'role_id': rid}
                for cid, uid, rid in participant_roles
            ])
        stmt = delete(MoodleParticipantRoles).where(MoodleParticipantRoles.course_id.in_(cids))
        if participant_roles:
            stmt = stmt.where(tuple_(
                MoodleParticipantRoles.course_id,
                MoodleParticipantRoles.user_id,
                MoodleParticipantRoles.role_id
            ).notin_(participant_roles))
        await session.execute(stmt)

        participant_groups = set((c.id, p.user.id, g.id) for c in courses for p in c.participants for g in p.groups)
        if participant_groups:
            stmt = upsert(MoodleParticipantGroups)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=[MoodleParticipantGroups.course_id, MoodleParticipantGroups.user_id,
                                MoodleParticipantGroups.group_id]
            )
            await session.execute(stmt, [
                {'course_id': cid, 'user_id': uid, 'group_id': gid}
                for cid, uid, gid in participant_groups
            ])
        stmt = delete(MoodleParticipantGroups).where(MoodleParticipantGroups.course_id.in_(cids))
        if participant_groups:
            stmt = stmt.where(tuple_(
                MoodleParticipantGroups.course_id,
                MoodleParticipantGroups.user_id,
                MoodleParticipantGroups.group_id
            ).notin_(participant_groups))
        await session.execute(stmt)
        await session.commit()

    async def _store_users(self, session: AsyncSession, courses: t.Collection[Course],
                           now: t.Optional[datetime]) -> None:
        """Сохраняет пользователей, упомянутых на разных курсах."""
        data = set(p for c in courses for p in c.participants)
        if not data:
            return
        stmt = upsert(MoodleUser)
        stmt = stmt.on_conflict_do_update(
            index_elements=[MoodleUser.id],
            set_={
                MoodleUser.fullname: stmt.excluded.fullname,
                MoodleUser.email: stmt.excluded.email,
                MoodleUser.last_seen: stmt.excluded.last_seen
            }
        )
        await session.execute(stmt, [
            dict(id=p.user.id, fullname=p.user.name, email=p.user.email, last_seen=now)
            for p in data
        ])
        await session.commit()

    async def store_courses(self, courses: t.Collection[Course], now: datetime = None) -> None:
        """Сохраняет записи о курсах в БД.
        :param courses: Коллекция курсов для сохранения.
        :param now: Время для пометки сохраняемых курсов (когда их в последний раз "видели").
        Если None, используется текущее время."""
        courses = set(courses)
        if not courses:
            return
        now = now.astimezone(self.TZ) if now is not None else datetime.now(self.TZ)
        async with self.__sessionmaker() as session:
            data = [
                dict(id=c.id, shortname=c.shortname, fullname=c.fullname,
                     starts=c.starts.astimezone(self.TZ) if c.starts else None,
                     ends=c.ends.astimezone(self.TZ) if c.ends else None,
                     last_seen=now)
                for c in courses
            ]
            stmt = upsert(MoodleCourse)
            stmt = stmt.on_conflict_do_update(
                index_elements=[MoodleCourse.id],
                set_={
                    MoodleCourse.shortname: stmt.excluded.shortname,
                    MoodleCourse.fullname: stmt.excluded.fullname,
                    MoodleCourse.starts: stmt.excluded.starts,
                    MoodleCourse.ends: stmt.excluded.ends,
                    MoodleCourse.last_seen: stmt.excluded.last_seen,
                }
            )
            await session.execute(stmt, data)
            await session.commit()

            await self._store_users(session, courses, now)
            await self._store_roles_for(session, courses)
            await self._store_groups_for(session, courses)
            await self._store_participants_for(session, courses)
            await session.commit()

    async def drop_courses(self, course_ids: t.Collection[int]) -> None:
        """Удаляет из базы записи о курсах с указанными id.
        :param course_ids: Коллекция идентификаторов удаляемых курсов."""
        if not course_ids:
            return
        async with self.__sessionmaker() as session:
            stmt = delete(MoodleCourse).where(MoodleCourse.id.in_(course_ids))
            await session.execute(stmt)
            await session.commit()

    async def get_open_course_ids(self, now: datetime, with_dates_only: bool = False) -> list[course_id]:
        """Возвращает идентификаторы курсов, которые открыты в настоящий момент.
        :param now: Что считать настоящим моментом.
        :param with_dates_only: Если истина, то курсы, для которых не указаны даты начала/конца, будут игнорироваться.
        :returns: Список идентификаторов."""
        now = now.astimezone(self.TZ)
        async with self.__sessionmaker() as session:
            stmt = (
                select(MoodleCourse.id)
                .select_from(MoodleCourse)
            )
            if with_dates_only:
                stmt = stmt.where(
                    and_(MoodleCourse.starts.isnot(None), MoodleCourse.starts <= now),
                    and_(MoodleCourse.ends.isnot(None), MoodleCourse.ends >= now),
                )
            else:
                stmt = stmt.where(
                    or_(MoodleCourse.starts.is_(None), MoodleCourse.starts <= now),
                    or_(MoodleCourse.ends.is_(None), MoodleCourse.ends >= now),
                )
            result = await session.execute(stmt)
            return [course_id(cid) for cid in result.scalars().all()]
    # endregion

    # region Задания
    async def load_assignments(self, assign_ids: t.Collection[assignment_id]) -> list[Assignment]:
        """Загружает задания с указанными ID.
        :param assign_ids: Коллекция ID заданий для загрузки.
        :returns: Список заданий (Assignment)."""
        if not assign_ids:
            return []
        async with self.__sessionmaker() as session:
            stmt = select(
                MoodleAssignment.id,
                MoodleAssignment.course_id,
                MoodleAssignment.name,
                MoodleAssignment.opening,
                MoodleAssignment.closing,
                MoodleAssignment.cutoff,
            ).where(MoodleAssignment.id.in_(assign_ids))
            result = await session.stream(stmt)
            results = [
                Assignment(id=aid, course_id=cid, name=aname, opening=aopen, closing=aclose, cutoff=acutoff)
                async for (aid, cid, aname, aopen, aclose, acutoff) in result
            ]
        return results

    async def store_assignments(self, assigns: t.Collection[Assignment]) -> None:
        """Сохраняет задания в базу данных, обновляя уже существующие записи, если надо.
        :param assigns: Коллекция сохраняемых заданий."""
        assigns = set(assigns)
        if not assigns:
            return
        data = [dict(id=a.id, course_id=a.course_id, name=a.name,
                     opening=a.opening.astimezone(self.TZ) if a.opening else None,
                     closing=a.closing.astimezone(self.TZ) if a.closing else None,
                     cutoff=a.cutoff.astimezone(self.TZ) if a.cutoff else None)
                for a in assigns]
        async with self.__sessionmaker() as session:
            stmt = upsert(MoodleAssignment)
            stmt = stmt.on_conflict_do_update(
                index_elements=[MoodleAssignment.id],
                set_={
                    MoodleAssignment.course_id: stmt.excluded.course_id,
                    MoodleAssignment.name: stmt.excluded.name,
                    MoodleAssignment.opening: stmt.excluded.opening,
                    MoodleAssignment.closing: stmt.excluded.closing,
                    MoodleAssignment.cutoff: stmt.excluded.cutoff,
                }
            )
            await session.execute(stmt, data)
            await session.commit()

    async def drop_assignments_except_for(self, content: dict[course_id, t.Collection[assignment_id]]) -> None:
        """Удаляет из базы все задания для указанных курсов, за исключением перечисленных.
        Курсы, чьи ID отсутствуют среди ключей content, не будут затронуты.
        :param content: Набор пар "ID курса - список ID заданий", которые следует оставить."""
        affected_cids = list(content.keys())
        correct_pairs = [(cid, aid) for cid, aids in content.items() for aid in aids]
        async with self.__sessionmaker() as session:
            stmt = delete(MoodleAssignment).where(MoodleAssignment.course_id.in_(affected_cids))
            if correct_pairs:
                stmt = stmt.where(tuple_(MoodleAssignment.course_id, MoodleAssignment.id).notin_(correct_pairs))
            await session.execute(stmt)
            await session.commit()

    async def get_active_assignment_ids_ending_soon(self, now: datetime, *,
                                                    before: timedelta, after: timedelta
                                                    ) -> list[assignment_id]:
        """Загружает список ID заданий, которые завершаются (срок сдачи или закрытие) в указанный интервал времени.
        Задания, для которых не указано время закрытия, никогда не попадут в этот список.
        :param now: Текущий момент времени (внутри интервала).
        :param before: Отступ от начала интервала до текущего момента.
        :param after: Отступ от текущего момента до конца интервала.
        :returns: Список ID заданий, удовлетворяющих условиям."""
        now = now.astimezone(self.TZ)
        start = now - before
        end = now + after
        async with self.__sessionmaker() as session:
            stmt = (
                select(MoodleAssignment.id)
                # выбираем только задания из активных курсов!
                .join(MoodleCourse, onclause=and_(
                    (MoodleAssignment.course_id == MoodleCourse.id),
                    or_(MoodleCourse.starts.is_(None), MoodleCourse.starts <= now),
                    or_(MoodleCourse.ends.is_(None), MoodleCourse.ends >= now),
                ))
                .where(
                    # задание уже открыто
                    or_(MoodleAssignment.opening.is_(None), MoodleAssignment.opening <= now),
                    or_(  # хотя бы один из сроков должен попадать в интервал
                        # срок сдачи находится в интервале
                        and_(MoodleAssignment.closing.isnot(None),
                             start <= MoodleAssignment.closing,
                             MoodleAssignment.closing <= end),
                        # дата закрытия находится в интервале
                        and_(MoodleAssignment.cutoff.isnot(None),
                             start <= MoodleAssignment.cutoff,
                             MoodleAssignment.cutoff <= end),
                    ),
                )
            )
            result = await session.scalars(stmt)
            return [assignment_id(aid) for aid in result.all()]

    async def get_active_assignment_ids_not_ending_soon(self, now: datetime, *,
                                                        before: timedelta, after: timedelta
                                                        ) -> list[assignment_id]:
        """Загружает список ID заданий, которые уже открыты, но НЕ завершаются (срок сдачи или закрытие)
        в указанный интервал времени. Задания, для которых не указано время закрытия, всегда попадут в этот список.
        Если курс ещё не доступен или уже не доступен, его задания игнорируются.
        :param now: Текущий момент времени (внутри интервала).
        :param before: Отступ от начала интервала до текущего момента.
        :param after: Отступ от текущего момента до конца интервала.
        :returns: Список ID заданий, удовлетворяющих условиям."""
        now = now.astimezone(self.TZ)
        start = now - before
        end = now + after
        async with self.__sessionmaker() as session:
            stmt = (
                select(MoodleAssignment.id)
                # выбираем только задания из активных курсов!
                .join(MoodleCourse, onclause=and_(
                    (MoodleAssignment.course_id == MoodleCourse.id),
                    or_(MoodleCourse.starts.is_(None), MoodleCourse.starts <= now),
                    or_(MoodleCourse.ends.is_(None), MoodleCourse.ends >= now),
                ))
                .where(
                    # задание уже открыто
                    or_(MoodleAssignment.opening.is_(None), MoodleAssignment.opening <= now),
                    and_(  # ни один из сроков не должен попадать в интервал
                        # срок сдачи неизвестен или не находится в интервале
                        or_(MoodleAssignment.closing.is_(None),
                            start > MoodleAssignment.closing,
                            MoodleAssignment.closing > end),
                        # дата закрытия неизвестна или не находится в интервале
                        or_(MoodleAssignment.cutoff.is_(None),
                            start > MoodleAssignment.cutoff,
                            MoodleAssignment.cutoff > end),
                    ),
                )
            )
            result = await session.scalars(stmt)
            return [assignment_id(aid) for aid in result.all()]
    # endregion

    # region Ответы на задания
    async def load_submissions(self, assignid: assignment_id, *,
                               before: datetime = None, after: datetime = None) -> list[Submission]:
        """Загружает ответы на указанное задание (assignment), отправленные в указанный интервал времени.
        :param assignid: ID задания, на которое были отправлены ответы.
        :param before: Самый ранний момент времени, в который могли быть отправлены ответы.
        :param after: Самый поздний момент времени, в который могли быть отправлены ответы.
        :returns: Список ответов."""
        async with self.__sessionmaker() as session:
            stmt = (
                select(
                    MoodleSubmission.id, MoodleSubmission.user_id, MoodleSubmission.status, MoodleSubmission.updated
                ).select_from(MoodleSubmission)
                .where(MoodleSubmission.assignment_id == assignid)
            )
            if before:
                stmt = stmt.where(MoodleSubmission.updated <= before.astimezone(self.TZ))
            if after:
                stmt = stmt.where(MoodleSubmission.updated >= after.astimezone(self.TZ))
            result = await session.stream(stmt)
            raw_subs = {
                sid: (uid, status, updated, [])
                async for (sid, uid, status, updated) in result
            }
            if not raw_subs:
                return []
            stmt = (
                select(
                    MoodleSubmittedFile.submission_id, MoodleSubmittedFile.filename, MoodleSubmittedFile.url,
                    MoodleSubmittedFile.filesize, MoodleSubmittedFile.mimetype, MoodleSubmittedFile.uploaded
                ).select_from(MoodleSubmittedFile)
                .where(
                    MoodleSubmittedFile.assignment_id == assignid,
                    MoodleSubmittedFile.submission_id.in_(raw_subs.keys())
                )
            )
            result = await session.stream(stmt)
            async for (sid, fname, furl, fsize, ftype, fupload) in result:
                raw_subs[sid][3].append(SubmittedFile(
                    submission_id=sid,
                    filename=fname,
                    mimetype=ftype,
                    filesize=fsize,
                    url=furl,
                    uploaded=fupload
                ))
        return [
            Submission(
                id=sid,
                user_id=uid,
                assignment_id=assignid,
                status=status,
                updated=updated,
                files=tuple(files)
            )
            for sid, (uid, status, updated, files) in raw_subs.items()
        ]

    async def store_submissions(self, submissions: t.Collection[Submission]) -> None:
        """Сохраняет указанный набор ответов на задание, и сведения о приложенных к ним файлах.
        :param submissions: Ответ на задание, которые следует сохранить."""
        submissions = set(submissions)
        if not submissions:
            return
        async with self.__sessionmaker() as session:
            data = [
                dict(id=s.id, assignment_id=s.assignment_id, user_id=s.user_id,
                     status=s.status, updated=s.updated)
                for s in submissions
            ]
            stmt = upsert(MoodleSubmission)
            stmt = stmt.on_conflict_do_update(
                index_elements=[MoodleSubmission.id],
                set_={
                    MoodleSubmission.status: stmt.excluded.status,
                    MoodleSubmission.updated: stmt.excluded.updated,
                }
            )
            await session.execute(stmt, data)

            data = [
                dict(submission_id=s.id, assignment_id=s.assignment_id, user_id=s.user_id,
                     filename=f.filename, filesize=f.filesize, mimetype=f.mimetype,
                     url=f.url, uploaded=f.uploaded.astimezone(self.TZ))
                for s in submissions for f in s.files
            ]
            if data:
                stmt = upsert(MoodleSubmittedFile)
                stmt = stmt.on_conflict_do_update(
                    index_elements=[MoodleSubmittedFile.submission_id, MoodleSubmittedFile.filename],
                    set_={
                        MoodleSubmittedFile.user_id: stmt.excluded.user_id,
                        MoodleSubmittedFile.filename: stmt.excluded.filename,
                        MoodleSubmittedFile.url: stmt.excluded.url,
                        MoodleSubmittedFile.filesize: stmt.excluded.filesize,
                        MoodleSubmittedFile.mimetype: stmt.excluded.mimetype,
                        MoodleSubmittedFile.uploaded: stmt.excluded.uploaded,
                    }
                )
                await session.execute(stmt, data)
            await session.commit()

    async def drop_submissions(self, assignids: t.Collection[assignment_id], *,
                               before: datetime = None, after: datetime = None) -> None:
        """Удаляет из базы сведения об ответах на указанные задания, попадающих в заданынй временной диапазон.
        :param assignids: Коллекция ID заданий, ответы на которые следует удалить.
        :param before: Удалить задания, отправленные ранее этого момента времени (включительно).
        :param after: Удалить задания, отправленные позднее этого момента времени (включительно).
        """
        if not assignids and not before and not after:
            raise ValueError("You just tried to delete EVERY submission in the database. "
                             "If that's what you really want, use after=datetime.min")
        async with self.__sessionmaker() as session:
            stmt = delete(MoodleSubmission)
            if assignids:
                stmt = stmt.where(MoodleSubmission.assignment_id.in_(assignids))
            if before:
                stmt = stmt.where(MoodleSubmission.updated <= before.astimezone(self.TZ))
            if after:
                stmt = stmt.where(MoodleSubmission.updated >= after.astimezone(self.TZ))
            await session.execute(stmt)
            await session.commit()

    async def get_last_submission_times(self, assignids: t.Collection[assignment_id]
                                        ) -> dict[assignment_id, t.Optional[datetime]]:
        """Возвращает время отправки самого позднего ответа на каждое из указанных заданий.
        Значение None вместо метки времени означает, что ответов на это задание ещё не было.
        :param assignids: ID заданий, для которых следует загрузить ответы.
        :returns: Словарь пар "ID задания - метка времени"."""
        if not assignids:
            return {}
        results = {aid: None for aid in assignids}
        async with self.__sessionmaker() as session:
            stmt = (
                select(MoodleSubmission.assignment_id, func.max(MoodleSubmission.updated))
                .select_from(MoodleSubmission)
                .where(MoodleSubmission.assignment_id.in_(assignids))
                .group_by(MoodleSubmission.assignment_id)
            )
            result = await session.stream(stmt)
            async for aid, ts in result:
                results[aid] = ts
        return results
    # endregion
