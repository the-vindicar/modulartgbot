"""Обеспечивает доступ к кэшу графиков обучения, скачанных с сайта."""
import typing as t
from datetime import datetime

from sqlalchemy import select, delete, VARCHAR
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.dialects.postgresql import insert as upsert, ARRAY

from api import DBModel
from .timeplan_parsing import GroupPlan, TimePlanActivity


__all__ = ['WorkloadBase', 'WorkloadRepository']


class WorkloadBase(DBModel):
    __abstract__ = True


class TimeplanCache(WorkloadBase):
    __tablename__ = 'timeplan_cache'
    groupcode: Mapped[str] = mapped_column(primary_key=True, comment='Код группы')
    year: Mapped[int] = mapped_column(primary_key=True, index=True, comment='Год')
    specialty_code: Mapped[str] = mapped_column(nullable=False, index=True, comment='Код специальности')
    specialty_name: Mapped[str] = mapped_column(nullable=False, index=False, comment='Наименование специальности')
    activities: Mapped[list[str]] = mapped_column(ARRAY(VARCHAR), nullable=False,
                                                  comment='План-график, начиная с 1 сентября')


class WorkloadRepository:
    """Обеспечивает доступ к кэшу сведений о графике обучения."""
    def __init__(self, engine: AsyncEngine):
        self.__sessionmaker = async_sessionmaker(bind=engine, class_=AsyncSession)

    async def create_tables(self) -> None:
        """Создаёт таблицы, относящиеся к кэшу расписания."""
        engine: AsyncEngine = self.__sessionmaker.kw['bind']
        async with engine.connect() as conn:
            await conn.run_sync(WorkloadBase.metadata.create_all)
            await conn.commit()

    async def store_timeplan(self, plan: GroupPlan) -> None:
        """Сохраняет учебный план-график.
        :param plan: План-график. Содержит информацию о группе и годе обучения.
        """
        async with self.__sessionmaker() as session:
            data = [
                dict(groupcode=plan.group_code, year=plan.year,
                     specialty_code=plan.specialty_code,
                     specialty_name=plan.specialty_name,
                     activities=[x.value for x in plan.activity])
            ]
            stmt = upsert(TimeplanCache)
            stmt = stmt.on_conflict_do_update(
                index_elements=[TimeplanCache.groupcode, TimeplanCache.year],
                set_={
                    TimeplanCache.specialty_code: stmt.excluded.specialty_code,
                    TimeplanCache.specialty_name: stmt.excluded.specialty_name,
                    TimeplanCache.activities: stmt.excluded.activities
                }
            )
            await session.execute(stmt, data)
            await session.commit()

    async def load_timeplan(self, group_code: str, year: int) -> t.Optional[GroupPlan]:
        """Загружает из кэша план-график для указанной группы за указанный год.
        :param group_code: Код группы.
        :param year: Год, за который требуется план-график.
        :returns: План-график, если он есть, или None."""
        async with self.__sessionmaker() as session:
            stmt = (
                select(
                    TimeplanCache.groupcode, TimeplanCache.year,
                    TimeplanCache.specialty_code, TimeplanCache.specialty_name,
                    TimeplanCache.activities
                )
                .select_from(TimeplanCache)
                .where(TimeplanCache.groupcode.ilike(group_code), TimeplanCache.year == year)
            )
            result = await session.execute(stmt)
            data = result.first()
            if data is None:
                return None
            gcode, y, scode, sname, act = data
            return GroupPlan(
                specialty_code=scode, specialty_name=sname,
                group_code=gcode, year=y,
                activity=tuple(TimePlanActivity(x) for x in act))

    async def delete_old_workplans(self, before: datetime) -> None:
        """Удаляет старые планы-графики.
        :param before: Точка отсечения. Будут сохранены графики за этот и предыдущий год, но остальные будут удалены.
        """
        async with self.__sessionmaker() as session:
            stmt = delete(TimeplanCache).where(TimeplanCache.year < before.year - 1)
            await session.execute(stmt)
            await session.commit()
