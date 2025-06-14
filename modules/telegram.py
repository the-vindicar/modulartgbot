"""
Запускает Телеграм-бота с указанным токеном. Предоставляет доступ к боту другим модулям.
"""
import dataclasses
import logging
import json
from typing import Dict, Any, Optional

import asyncpg
import aiogram
from aiogram.fsm.storage.base import BaseStorage, StorageKey, StateType, DefaultKeyBuilder
from aiogram.fsm.storage.memory import MemoryStorage

from api import CoreAPI, background_task


requires = [asyncpg.Pool]
provides = [aiogram.Dispatcher, aiogram.Bot, BaseStorage]


@dataclasses.dataclass
class TGBotConfig:
    bot_token: str
    temp_storage: bool = False


class PostgreStorage(BaseStorage):
    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn
        self.builder = DefaultKeyBuilder()

    async def create_tables(self) -> None:
        async with self.conn.transaction():
            await self.conn.execute('''CREATE TABLE IF NOT EXISTS AiogramStateStorage (
                key TEXT PRIMARY KEY,
                state TEXT NULL,
                data TEXT NULL
            )''')

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        statekey = self.builder.build(key)
        if isinstance(state, str) or state is None:
            statevalue = state
        else:
            statevalue = state.state
        async with self.conn.transaction():
            await self.conn.execute(
                '''INSERT INTO AiogramStateStorage 
                (key, state) VALUES ($1, $2)
                ON CONFLICT (key) DO UPDATE SET state = EXCLUDED.state''',
                statekey, statevalue
            )

    async def get_state(self, key: StorageKey) -> Optional[str]:
        statekey = self.builder.build(key)
        async with self.conn.transaction(readonly=True):
            res = await self.conn.cursor(
                '''SELECT (SELECT state FROM AiogramStateStorage WHERE key = $1) as state''',
                statekey)
            (state,) = await res.fetchrow()
            return state

    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        statekey = self.builder.build(key)
        statedata = json.dumps(data)
        async with self.conn.transaction():
            await self.conn.execute(
                '''INSERT INTO AiogramStateStorage 
                (key, data) VALUES ($1, $3)
                ON CONFLICT (key) DO UPDATE SET data = EXCLUDED.data''',
                statekey, statedata
            )

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        statekey = self.builder.build(key)
        async with self.conn.transaction(readonly=True):
            res = await self.conn.cursor(
                '''SELECT (SELECT state FROM AiogramStateStorage WHERE key = $1) as state''',
                statekey)
            (data,) = await res.fetchrow()
        return json.loads(data) if data is not None else {}

    async def close(self) -> None:
        self.conn = None


async def lifetime(api: CoreAPI):
    log = logging.getLogger('modules.telegram')
    log.info('Preparing telegram bot...')
    bot_cfg = await api.config.load('telegram', TGBotConfig)
    pool = await api(asyncpg.Pool)
    if bot_cfg.temp_storage:
        storage = MemoryStorage()
        pool_ctx = None
    else:
        log.debug('Database storage selected - trying to set it up.')
        pool_ctx = pool.acquire()
        conn = await pool_ctx.__aenter__()
        storage = PostgreStorage(conn)
        await storage.create_tables()
        log.debug('Database storage ready.')
    tgdispatcher = aiogram.Dispatcher(storage=storage)
    bot = aiogram.Bot(token=bot_cfg.bot_token)

    async def bot_provider():
        return bot

    async def dispatcher_provider():
        return tgdispatcher

    async def storage_provider():
        return storage

    api.register_api_provider(bot_provider, aiogram.Bot)
    api.register_api_provider(dispatcher_provider, aiogram.Dispatcher)
    api.register_api_provider(storage_provider, BaseStorage)
    log.info('Starting telegram bot...')
    try:
        # ДА ЯПОНСКИЙ ГОРОДОВОЙ! aiogram пожирает сигналы, не позволяя другим частям программы среагировать на них,
        # если не указать handle_signals=False
        async with background_task(tgdispatcher.start_polling(bot, handle_signals=False)):
            yield
    finally:
        if pool_ctx:
            await pool_ctx.__aexit__()
            log.debug('Database storage released.')
        log.info('Telegram bot stopped.')
