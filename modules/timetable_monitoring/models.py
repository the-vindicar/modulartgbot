"""Обеспечивает доступ к кэшу расписаний, скачанных с сайта."""
import typing as t
from datetime import datetime, timezone

from sqlalchemy import DateTime, select, delete
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.dialects.postgresql import insert as upsert

from api import DBModel
from ._classes import Timetable, Lesson


class TimetableBase(DBModel):
    __abstract__ = True


class TimetableCache(TimetableBase):
    __tablename__ = 'timetable_cache'
    week: Mapped[int] = mapped_column(primary_key=True, comment='Неделя (1 - нечётная, 2 - чётная, 0 - обе)')
    day: Mapped[int] = mapped_column(primary_key=True, comment='День (1-6)')
    period: Mapped[int] = mapped_column(primary_key=True, comment='Пара (1-8)')
    teacher: Mapped[str] = mapped_column(primary_key=True, index=True, comment='Фамилия И.О. преподавателя')
    room: Mapped[str] = mapped_column(nullable=False, index=True, comment='Аудитория')
    course: Mapped[str] = mapped_column(nullable=False, comment='Дисциплина')
    course_type: Mapped[str] = mapped_column(nullable=False, comment='Тип занятия')
    groups: Mapped[str] = mapped_column(nullable=False, comment='Перечисление групп')


class TeacherUpdate(TimetableBase):
    __tablename__ = 'teacher_updates'
    teacher: Mapped[str] = mapped_column(primary_key=True, comment='Фамилия И.О. преподавателя')
    updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                              comment='Когда расписание изменилось последний раз')


class TimetableRepository:
    """Обеспечивает доступ к кэшу расписаний, скачанных с сайта."""
    def __init__(self, engine: AsyncEngine):
        self.__sessionmaker = async_sessionmaker(bind=engine, class_=AsyncSession)

    async def create_tables(self) -> None:
        """Создаёт таблицы, относящиеся к кэшу расписания."""
        engine: AsyncEngine = self.__sessionmaker.kw['bind']
        async with engine.connect() as conn:
            await conn.run_sync(TimetableBase.metadata.create_all)
            await conn.commit()

    async def store_teacher_timetable(self, teacher: str, timetable: Timetable) -> None:
        """Заменяет расписание для указанного преподавателя, удаляя старое.
        :param teacher: Фамилия И.О. преподавателя.
        :param timetable: Содержимое расписания."""
        async with self.__sessionmaker() as session:
            await session.execute(delete(TimetableCache).where(TimetableCache.teacher == teacher))
            data = [
                dict(week=week, day=day, period=period, teacher=teacher,
                     room=lesson.room, course=lesson.course, course_type=lesson.type, groups=lesson.groups)
                for day, period, week, lesson in timetable.iterate()
            ]
            if data:
                stmt = upsert(TimetableCache)
                stmt = stmt.on_conflict_do_update(
                    index_elements=[TimetableCache.week, TimetableCache.day, TimetableCache.period,
                                    TimetableCache.teacher],
                    set_={
                        TimetableCache.room: stmt.excluded.room,
                        TimetableCache.course: stmt.excluded.course,
                        TimetableCache.course_type: stmt.excluded.course_type,
                        TimetableCache.groups: stmt.excluded.groups
                    }
                )
                await session.execute(stmt, data)
            await session.commit()

    async def store_room_timetable(self, room: str, timetable: Timetable) -> None:
        """Заменяет расписание для указанной аудитории, удаляя старое.
        :param room: Номер аудитории.
        :param timetable: Содержимое расписания."""
        async with self.__sessionmaker() as session:
            await session.execute(delete(TimetableCache).where(TimetableCache.room == room))
            data = [
                dict(week=week, day=day, period=period, room=room,
                     teacher=lesson.teacher, course=lesson.course, course_type=lesson.type, groups=lesson.groups)
                for day, period, week, lesson in timetable.iterate()
            ]
            if data:
                stmt = upsert(TimetableCache)
                stmt = stmt.on_conflict_do_update(
                    index_elements=[TimetableCache.week, TimetableCache.day, TimetableCache.period,
                                    TimetableCache.teacher],
                    set_={
                        TimetableCache.room: stmt.excluded.room,
                        TimetableCache.course: stmt.excluded.course,
                        TimetableCache.course_type: stmt.excluded.course_type,
                        TimetableCache.groups: stmt.excluded.groups
                    }
                )
                await session.execute(stmt, data)
            await session.commit()

    async def load_teacher_timetable(self, teacher: str) -> Timetable:
        """Загружает из кэша расписание указанного преподавателя.
        :param teacher: Фамилия И.О. преподавателя.
        :returns: Содержимое расписания. Если для преподавателя нет записей, вернёт пустое расписание."""
        timetable = Timetable()
        async with self.__sessionmaker() as session:
            stmt = select(
                TimetableCache.week, TimetableCache.day, TimetableCache.period,
                TimetableCache.teacher, TimetableCache.room, TimetableCache.groups,
                TimetableCache.course_type, TimetableCache.course
            ).select_from(TimetableCache).where(TimetableCache.teacher == teacher)
            result = await session.execute(stmt)
            for week, day, period, teacher, room, groups, ctype, course in result.all():
                slot = timetable.slots[day][period]
                lesson = Lesson(room=room, teacher=teacher, course=course, type=ctype, groups=groups)
                if week == 1:
                    slot.above = lesson
                elif week == 2:
                    slot.below = lesson
                else:
                    slot.both = lesson
        return timetable

    async def load_teachers_timetables(self, teachers: t.Collection[str]) -> dict[str, Timetable]:
        """Загружает из кэша расписание указанных преподавателей.
        :param teachers: Фамилия И.О. для каждого интересующего преподавателя.
        :returns: Набор расписаний. Если для преподавателя нет записей, вернёт пустое расписание."""
        timetables = {teacher: Timetable() for teacher in teachers}
        async with self.__sessionmaker() as session:
            stmt = select(
                TimetableCache.week, TimetableCache.day, TimetableCache.period,
                TimetableCache.teacher, TimetableCache.room, TimetableCache.groups,
                TimetableCache.course_type, TimetableCache.course
            ).select_from(TimetableCache).where(TimetableCache.teacher.in_(teachers))
            result = await session.execute(stmt)
            for week, day, period, teacher, room, groups, ctype, course in result.all():
                timetable = timetables.get(teacher, None)
                if timetable is None:
                    continue
                slot = timetable.slots[day][period]
                lesson = Lesson(room=room, teacher=teacher, course=course, type=ctype, groups=groups)
                if week == 1:
                    slot.above = lesson
                elif week == 2:
                    slot.below = lesson
                else:
                    slot.both = lesson
        return timetables

    async def load_room_timetable(self, room: str) -> Timetable:
        """Загружает из кэша расписание указанной аудитории.
        :param room: Номер аудитории.
        :returns: Содержимое расписания. Если для аудитории нет записей, вернёт пустое расписание."""
        timetable = Timetable()
        async with self.__sessionmaker() as session:
            stmt = select(
                TimetableCache.week, TimetableCache.day, TimetableCache.period,
                TimetableCache.teacher, TimetableCache.room, TimetableCache.groups,
                TimetableCache.course_type, TimetableCache.course
            ).select_from(TimetableCache).where(TimetableCache.room == room)
            result = await session.execute(stmt)
            for week, day, period, teacher, room, groups, ctype, course in result:
                slot = timetable.slots[day][period]
                lesson = Lesson(room=room, teacher=teacher, course=course, type=ctype, groups=groups)
                if week == 1:
                    slot.above = lesson
                elif week == 2:
                    slot.below = lesson
                else:
                    slot.both = lesson
        return timetable

    async def load_rooms_timetables(self, rooms: t.Collection[str]) -> dict[str, Timetable]:
        """Загружает из кэша расписания указанных аудиторий.
        :param rooms: Номера аудиторий.
        :returns: Набор пар "аудитория - расписание". Если для аудитории нет записей, вернёт пустое расписание."""
        timetables = {room: Timetable() for room in rooms}
        async with self.__sessionmaker() as session:
            stmt = select(
                TimetableCache.week, TimetableCache.day, TimetableCache.period,
                TimetableCache.teacher, TimetableCache.room, TimetableCache.groups,
                TimetableCache.course_type, TimetableCache.course
            ).select_from(TimetableCache).where(TimetableCache.room.in_(rooms))
            result = await session.execute(stmt)
            for week, day, period, teacher, room, groups, ctype, course in result:
                timetable = timetables.get(room, None)
                if timetable is None:
                    continue
                slot = timetable.slots[day][period]
                lesson = Lesson(room=room, teacher=teacher, course=course, type=ctype, groups=groups)
                if week == 1:
                    slot.above = lesson
                elif week == 2:
                    slot.below = lesson
                else:
                    slot.both = lesson
        return timetables

    async def load_update_timestamps(self) -> dict[str, datetime]:
        """Загружает даты последнего обновления расписания для преподавателей.
        :returns: Пары "Фамилия И.О. преподавателя - время обновления"."""
        async with self.__sessionmaker() as session:
            stmt = select(TeacherUpdate.teacher, TeacherUpdate.updated).select_from(TeacherUpdate)
            result = await session.execute(stmt)
            return {teacher: timestamp for teacher, timestamp in result}

    async def bump_update_timestamp(self, teacher: str) -> None:
        """Обновляет дату обновления расписания указанного преподавателя на текущий момент.
        :param teacher: Фамилия И.О. преподавателя, для которого нужно обновить дату."""
        now = datetime.now(timezone.utc)
        async with self.__sessionmaker() as session:
            stmt = upsert(TeacherUpdate)
            stmt = stmt.on_conflict_do_update(
                index_elements=[TeacherUpdate.teacher],
                set_={TeacherUpdate.updated: stmt.excluded.updated}
            )
            await session.execute(stmt, dict(teacher=teacher, updated=now))
            await session.commit()
