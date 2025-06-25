"""Реализует репозиторий для работы с локальным кэшем сущностей Moodle."""
import typing as t
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import logging

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, AsyncSession
from sqlalchemy import select, delete, or_, and_, tuple_, func

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
        roles = set(MoodleRole(id=r.id, name=r.name) for c in courses for p in c.participants for r in p.roles)
        session.add_all(roles)
        await session.flush()

    async def _store_groups_for(self, session: AsyncSession, courses: t.Collection[Course]) -> None:
        """Сохраняет группы, встреченные в указанных курсах.
        Если группа, связанная с курсом, есть в БД, но не упоминается в курсе, она будет удалена из БД."""
        cids = set(c.id for c in courses)
        groups = set(MoodleGroup(course_id=c.id, id=g.id, name=g.name)
                     for c in courses for p in c.participants for g in p.groups)
        session.add_all(groups)
        await session.flush()
        course_groups = set((mg.course_id, mg.id) for mg in groups)
        if course_groups:
            stmt = delete(MoodleGroup).where(
                MoodleGroup.course_id.in_(cids),
                tuple_(MoodleGroup.course_id, MoodleGroup.id).notin_(course_groups))
            await session.execute(stmt)

    async def _store_participants_for(self, session: AsyncSession, courses: t.Collection[Course]) -> None:
        """Сохраняет участников указанных курсов, их роли и группы."""
        cids = set(c.id for c in courses)
        participation = set(MoodleParticipant(course_id=c.id, user_id=p.user.id)
                            for c in courses for p in c.participants)
        session.add_all(participation)
        await session.flush()
        course_participants = set((mp.course_id, mp.user_id) for mp in participation)
        if course_participants:
            stmt = delete(MoodleParticipant).where(
                MoodleParticipant.course_id.in_(cids),
                tuple_(MoodleParticipant.course_id, MoodleParticipant.user_id).notin_(course_participants))
            await session.execute(stmt)

        participant_roles = set(MoodleParticipantRoles(course_id=c.id, user_id=p.user.id, role_id=r.id)
                                for c in courses for p in c.participants for r in p.roles)
        session.add_all(participant_roles)
        await session.flush()
        participating_roles = set((c.id, p.user.id, r.id) for c in courses for p in c.participants for r in p.roles)
        if participating_roles:
            stmt = delete(MoodleParticipantRoles).where(
                MoodleParticipantRoles.course_id.in_(cids),
                tuple_(
                    MoodleParticipantRoles.course_id,
                    MoodleParticipantRoles.user_id,
                    MoodleParticipantRoles.role_id
                ).notin_(participating_roles))
            await session.execute(stmt)

        participant_groups = set(MoodleParticipantGroups(course_id=c.id, user_id=p.user.id, group_id=g.id)
                                 for c in courses for p in c.participants for g in p.groups)
        session.add_all(participant_groups)
        await session.flush()
        participating_groups = set((c.id, p.user.id, g.id) for c in courses for p in c.participants for g in p.groups)
        if participating_groups:
            stmt = delete(MoodleParticipantGroups).where(
                MoodleParticipantGroups.course_id.in_(cids),
                tuple_(
                    MoodleParticipantGroups.course_id,
                    MoodleParticipantGroups.user_id,
                    MoodleParticipantGroups.group_id
                ).notin_(participating_groups))
            await session.execute(stmt)

    async def store_courses(self, courses: t.Collection[Course], now: datetime = None) -> None:
        """Сохраняет записи о курсах в БД.
        :param courses: Коллекция курсов для сохранения.
        :param now: Время для пометки сохраняемых курсов (когда их в последний раз "видели").
        Если None, используется текущее время."""
        if not courses:
            return
        now = now.astimezone(self.TZ) if now is not None else datetime.now(self.TZ)
        async with self.__sessionmaker() as session:
            session.add_all(
                MoodleCourse(id=c.id, shortname=c.shortname, fullname=c.fullname,
                             starts=c.starts.astimezone(self.TZ) if c.starts else None,
                             ends=c.ends.astimezone(self.TZ) if c.ends else None,
                             last_seen=now)
                for c in courses
            )
            await session.flush()
            users = set(MoodleUser(id=p.user.id, fullname=p.user.name, email=p.user.email, last_seen=now)
                        for c in courses for p in c.participants)
            session.add_all(users)
            await session.flush()
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
        if not assigns:
            return
        async with self.__sessionmaker() as session:
            session.add_all(
                MoodleAssignment(id=a.id, course_id=a.course_id, name=a.name,
                                 opening=a.opening.astimezone(self.TZ) if a.opening else None,
                                 closing=a.closing.astimezone(self.TZ) if a.closing else None,
                                 cutoff=a.cutoff.astimezone(self.TZ) if a.cutoff else None)
                for a in assigns
            )
            await session.flush()
            await session.commit()

    async def drop_assignments_except_for(self, content: dict[course_id, t.Collection[assignment_id]]) -> None:
        """Удаляет из базы все задания для указанных курсов, за исключением перечисленных.
        Курсы, чьи ID отсутствуют среди ключей content, не будут затронуты.
        :param content: Набор пар "ID курса - список ID заданий", которые следует оставить."""
        affected_cids = list(content.keys())
        correct_pairs = [(cid, aid) for cid, aids in content.items() for aid in aids]
        if not correct_pairs:
            return
        async with self.__sessionmaker() as session:
            stmt = delete(MoodleAssignment).where(
                MoodleAssignment.course_id.in_(affected_cids),
                tuple_(MoodleAssignment.course_id, MoodleAssignment.id).notin_(correct_pairs)
            )
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
            stmt = (select(MoodleAssignment.id).where(
                # задание уже открыто
                or_(MoodleAssignment.opening.is_(None), MoodleAssignment.opening <= now),
                or_(  # хотя бы один из сроков должен попадать в интервал
                    # срок сдачи находится в интервале
                    and_(MoodleAssignment.closing.isnot(None), start <= MoodleAssignment.closing <= end),
                    # дата закрытия находится в интервале
                    and_(MoodleAssignment.cutoff.isnot(None), start <= MoodleAssignment.cutoff <= end),
                ),
            ))
            result = await session.scalars(stmt)
            return [assignment_id(aid) for aid in result.all()]

    async def get_active_assignment_ids_not_ending_soon(self, now: datetime, *,
                                                        before: timedelta, after: timedelta
                                                        ) -> list[assignment_id]:
        """Загружает список ID заданий, которые уже открыты, но НЕ завершаются (срок сдачи или закрытие)
        в указанный интервал времени. Задания, для которых не указано время закрытия, всегда попадут в этот список.
        :param now: Текущий момент времени (внутри интервала).
        :param before: Отступ от начала интервала до текущего момента.
        :param after: Отступ от текущего момента до конца интервала.
        :returns: Список ID заданий, удовлетворяющих условиям."""
        now = now.astimezone(self.TZ)
        start = now - before
        end = now + after
        async with self.__sessionmaker() as session:
            stmt = (select(MoodleAssignment.id).where(
                # задание уже открыто
                or_(MoodleAssignment.opening.is_(None), MoodleAssignment.opening <= now),
                and_(  # ни один из сроков не должен попадать в интервал
                    # срок сдачи неизвестен или не находится в интервале
                    or_(MoodleAssignment.closing.is_(None), ~(start <= MoodleAssignment.closing <= end)),
                    # дата закрытия неизвестна или не находится в интервале
                    or_(MoodleAssignment.cutoff.is_(None), ~(start <= MoodleAssignment.cutoff <= end)),
                ),
            ))
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
        if not submissions:
            return
        async with self.__sessionmaker() as session:
            session.add_all(
                MoodleSubmission(id=s.id, assignment_id=s.assignment_id, user_id=s.user_id,
                                 status=s.status, updated=s.updated)
                for s in submissions
            )
            await session.flush()
            session.add_all(
                MoodleSubmittedFile(submission_id=s.id, assignment_id=s.assignment_id, user_id=s.user_id,
                                    filename=f.filename, filesize=f.filesize, mimetype=f.mimetype,
                                    url=f.url, uploaded=f.uploaded.astimezone(self.TZ))
                for s in submissions for f in s.files
            )
            await session.flush()
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
                                        ) -> dict[assignment_id, datetime | None]:
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
