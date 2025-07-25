"""Модели для хранения настроек."""
from typing import Any, TypeVar, Type, Optional

import pydantic
from sqlalchemy import JSON, select, delete, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, AsyncSession
from sqlalchemy.dialects.postgresql import insert as upsert

from api import DBModel


__all__ = ['SettingsRepository']
TModel = TypeVar('TModel')


class Settings(DBModel):
    """Набор настроек, привязанных к сущности.

    - ``namespace``: Пространство имён (имя модуля). Позволяет разным модулям хранить настройки для одной сущности.
    - ``entity_type``: Тип сущности, к которой прикреплены настройки.
    - ``entity_id``: Идентификатор сущности, к которой прикреплены настройки.
    - ``data``: Настройки в формате JSON.
    """
    __tablename__ = 'Settings'
    namespace: Mapped[str] = mapped_column(String(32), primary_key=True,
                                           comment='Пространство имён')
    entity_type: Mapped[str] = mapped_column(String(32), primary_key=True,
                                             comment='Наименование типа сущности')
    entity_id: Mapped[str] = mapped_column(String(64), primary_key=True,
                                           comment='ID сущности')
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, server_default='{}',
                                                 comment='Настройки в JSON')


class SettingsRepository:
    """Предоставляет доступ к хранилищу настроек."""
    def __init__(self, engine: AsyncEngine):
        self.__known_models: dict[Type[TModel], tuple[str, str]] = {}
        self.__sessionmaker = async_sessionmaker(bind=engine, class_=AsyncSession,
                                                 autoflush=True, expire_on_commit=False)

    def register_model(self, namespace: str, entity_type: str, modeltype: Type[TModel]) -> None:
        """Регистрирует модель настроек для указанной пары "пространство имён - тип сущности".

        :param namespace: Простраство имён (например, имя модуля). Нечувствительно к регистру.
        :param entity_type: Обозначение типа сущности, для которого мы регистрируем настройки.
        Нечувствительно к регистру.
        :param modeltype: Модель настроек на базе :class:`pydantic.BaseModel`."""
        namespace = namespace.lower()
        entity_type = entity_type.lower()
        for m, (ns, etype) in self.__known_models.items():
            if namespace == ns and etype == entity_type:
                raise TypeError(f'There is already a model registered for {ns}/{etype}: {m!r}')
            if m is modeltype:
                raise TypeError(f'Model {modeltype!r} is already registered for {ns}/{etype}')
        self.__known_models[modeltype] = (namespace, entity_type)

    def get_models(self, entity_type: str) -> dict[str, Type[TModel]]:
        """Возвращает словарь моделей настроек, привязанных к указанному типу сущностей.

        :param entity_type: Обозначение типа сущности. Нечувствительно к регистру.
        :returns: Словарь пар "пространство имён - класс модели"."""
        entity_type = entity_type.lower()
        return {namespace: model
                for model, (namespace, etype) in self.__known_models.items()
                if etype == entity_type}

    def get_model_usage(self, modeltype: Type[TModel]) -> tuple[str, str]:
        """Возвращает пару "пространство имён - тип сущности" для указанного класса модели."""
        usage = self.__known_models.get(modeltype, None)
        if usage is None:
            raise TypeError(f'Model {modeltype!r} is not registered')
        else:
            return usage

    async def create_tables(self) -> None:
        """Создаёт таблицу для хранения настроек."""
        engine: AsyncEngine = self.__sessionmaker.kw['bind']
        async with engine.connect() as conn:
            await conn.run_sync(Settings.metadata.create_all)
            await conn.commit()

    async def get(self, entity_id: str, modeltype: Type[TModel]) -> TModel:
        """Загружает настройки для указанной сущности и формирует из них модель.

        :param entity_id: ID сущности, для которой загружаются настройки.
        :param modeltype: Зарегистрированная модель настроек на базе :class:`pydantic.BaseModel`.
        :returns: Экземпляр модели настроек, зарегистрированной для этой сущности.
        """
        namespace, entity_type = self.get_model_usage(modeltype)
        stmt = select(Settings.data).select_from(Settings).where(
            Settings.namespace == namespace,
            Settings.entity_type == entity_type,
            Settings.entity_id == entity_id
        )
        async with self.__sessionmaker() as session:
            data = await session.scalar(stmt)
        if data is None:
            return modeltype()
        else:
            ta = pydantic.TypeAdapter(modeltype)
            return ta.validate_python(data)

    async def set(self, entity_id: str, data: TModel) -> None:
        """Сохраняет настройки для указанной сущности.

        Нечувствительно к регистру.
        :param entity_id: ID сущности, для которой сохраняются настройки.
        :param data: Экземпляр модели, содержащий сохраняемые настройки.
        """
        modeltype = type(data)
        namespace, entity_type = self.get_model_usage(modeltype)
        adapter = pydantic.TypeAdapter(modeltype)
        stmt = upsert(Settings).values({
            Settings.namespace: namespace,
            Settings.entity_type: entity_type,
            Settings.entity_id: entity_id,
            Settings.data: adapter.dump_python(data)
        })
        stmt = stmt.on_conflict_do_update(
            index_elements=[Settings.namespace, Settings.entity_type, Settings.entity_id],
            set_={Settings.data: stmt.excluded.data}
        )
        async with self.__sessionmaker() as session:
            await session.execute(stmt)

    async def delete_for(self, namespace: str, entity_type: Optional[str], entity_id: Optional[str]) -> None:
        """Удаляет настройки для указанной сущности, типа сущностей или все настройки из заданного пространства имён.

        :param namespace: Простраство имён (например, имя модуля). Нечувствительно к регистру.
        :param entity_type: Обозначение типа сущности, для которого мы регистрируем настройки.
        Нечувствительно к регистру. Если None, будут удалены все настройки из пространства имён.
        :param entity_id: ID сущности, для которой удаляются настройки. Если None, будут удалены настройки
        для всех экземпляров указанного типа сущностей.
        """
        stmt = delete(Settings).where(Settings.namespace == namespace.lower())
        if entity_type is not None:
            stmt = stmt.where(Settings.entity_type == entity_type.lower())
            if entity_id is not None:
                stmt = stmt.where(Settings.entity_id == entity_id)
        async with self.__sessionmaker() as session:
            await session.execute(stmt)

    async def delete(self, modeltype: Type[TModel], entity_id: Optional[str]) -> None:
        """Удаляет настройки для указанной сущности или типа сущностей.

        :param modeltype: Зарегистрированная модель настроек на базе :class:`pydantic.BaseModel`.
        :param entity_id: ID сущности, для которой удаляются настройки. Если None, будут удалены настройки
        для всех экземпляров указанного типа сущностей."""
        namespace, entity_type = self.get_model_usage(modeltype)
        return await self.delete_for(namespace, entity_type, entity_id)
