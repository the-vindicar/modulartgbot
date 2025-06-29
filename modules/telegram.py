"""
Запускает Телеграм-бота с указанным токеном. Предоставляет доступ к боту другим модулям.
"""
import dataclasses
import logging
import json
from typing import cast, Optional, Dict, Any

from sqlalchemy import MetaData, Table, Column, Text, TableClause, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncConnection

import aiogram
from aiogram.fsm.storage.base import BaseStorage, StorageKey, StateType, KeyBuilder, DefaultKeyBuilder
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation

from api import CoreAPI, background_task


requires = [AsyncEngine]
provides = [aiogram.Dispatcher, aiogram.Bot]


@dataclasses.dataclass
class TGBotConfig:
    """Настройки телеграм-бота"""
    bot_token: str
    temp_storage: bool = False


class PostgreStorage(BaseStorage):
    """Stores aiogram FSM states for users in a PostgreSQL database, using SQLAlchemy engine."""
    def __init__(self, conn: AsyncConnection, table: str = 'AiogramFSMStorage', builder: KeyBuilder = None):
        self.__conn = conn
        metadata = MetaData()
        self.__table = Table(
            table,
            metadata,
            Column('key', Text, primary_key=True),
            Column('state', Text, nullable=True),
            Column('data', Text, nullable=True),
        )
        self.__table.create(bind=self.__conn.sync_connection, checkfirst=True)
        self.__builder = builder or DefaultKeyBuilder()

    @property
    def table(self) -> Table:
        """Returns SQLAlchemy table information."""
        return self.__table

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        statekey = self.__builder.build(key)
        statename = state if isinstance(state, str) or state is None else state.state
        stmt = insert(cast(TableClause, self.__table)).values(key=statekey, state=statename)
        stmt = stmt.on_conflict_do_update(index_elements=['key'], set_=dict(state=stmt.excluded.state))
        async with self.__conn.begin():
            await self.__conn.execute(stmt)

    async def get_state(self, key: StorageKey) -> Optional[str]:
        statekey = self.__builder.build(key)
        stmt = select('state').select_from(self.__table).where(self.__table.c.key == statekey)
        async with self.__conn.begin():
            state = await self.__conn.scalar(stmt)  # noqa
        return state

    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        statekey = self.__builder.build(key)
        statedata = json.dumps(data, ensure_ascii=True, indent=None, separators=(',', ':'))
        stmt = insert(cast(TableClause, self.__table)).values(key=statekey, data=statedata)
        stmt = stmt.on_conflict_do_update(index_elements=['key'], set_=dict(data=stmt.excluded.data))
        async with self.__conn.begin():
            await self.__conn.execute(stmt)

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        statekey = self.__builder.build(key)
        stmt = select('data').select_from(self.__table).where(self.__table.c.key == statekey)
        async with self.__conn.begin():
            data = await self.__conn.scalar(stmt)  # noqa
        return json.loads(data) if data else {}

    async def close(self) -> None:
        await self.__conn.close()


async def lifetime(api: CoreAPI):
    """Тело модуля."""
    log = logging.getLogger('modules.telegram')
    log.info('Preparing telegram bot...')
    bot_cfg = await api.config.load('telegram', TGBotConfig)
    if bot_cfg.temp_storage:
        log.warning('Using in-memory storage - user states will be lost on restart.')
        storage = MemoryStorage()
        pool_ctx = None
    else:
        log.debug('Database storage selected - trying to set it up.')
        engine = await api(AsyncEngine)
        pool_ctx = engine.connect()
        conn = await pool_ctx.__aenter__()
        storage = PostgreStorage(conn)
        log.debug('Database storage ready.')
    tgdispatcher = aiogram.Dispatcher(storage=storage, events_isolation=SimpleEventIsolation())
    bot = aiogram.Bot(token=bot_cfg.bot_token)
    api.register_api_provider(bot, aiogram.Bot)
    api.register_api_provider(tgdispatcher, aiogram.Dispatcher)
    log.info('Starting telegram bot...')
    try:
        # ДА ЯПОНСКИЙ ГОРОДОВОЙ! aiogram пожирает сигналы, не позволяя другим частям программы среагировать на них,
        # если не указать handle_signals=False
        async with background_task(tgdispatcher.start_polling(bot, handle_signals=False)):
            yield
    finally:
        if pool_ctx:
            await pool_ctx.__aexit__(None, None, None)
            log.debug('Database storage released.')
        log.info('Telegram bot stopped.')
