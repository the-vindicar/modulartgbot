"""Реализует репозиторий для работы с локальным кэшем сущностей Moodle."""
import typing as t
from datetime import datetime, timezone
from collections import defaultdict
import logging

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, AsyncSession
from sqlalchemy import select, delete, or_, and_, tuple_

from modules.moodle import Course, Participant, User, Role, Group, user_id, course_id
from .base import MoodleBase
from .course import *
from .users import *
from .participant import *


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

    async def load_courses(self, course_ids: t.Collection[course_id]) -> list[Course]:
        """Загружает список курсов с указанными id.
        :param course_ids: Коллекция идентификаторов курсов.
        :returns: Список объектов Course."""
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

    async def drop_courses(self, course_ids: t.Collection[int]) -> None:
        """Удаляет из базы записи о курсах с указанными id.
        :param course_ids: Коллекция идентификаторов удаляемых курсов."""
        async with self.__sessionmaker() as session:
            stmt = delete(MoodleCourse).where(MoodleCourse.id.in_(course_ids))
            await session.execute(stmt)
