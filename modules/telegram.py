"""
Запускает Телеграм-бота с указанным токеном. Предоставляет доступ к боту другим модулям.
"""
import dataclasses
import logging

import aiogram

from api import CoreAPI, background_task


requires = []
provides = [aiogram.Dispatcher, aiogram.Bot]


@dataclasses.dataclass
class TGBotConfig:
    bot_token: str


async def lifetime(api: CoreAPI):
    log = logging.getLogger('modules.telegram')
    log.info('Preparing telegram bot...')
    bot_cfg = await api.config.load('telegram', TGBotConfig)
    tgdispatcher = aiogram.Dispatcher()
    bot = aiogram.Bot(token=bot_cfg.bot_token)

    async def bot_provider():
        return bot

    async def dispatcher_provider():
        return tgdispatcher

    api.register_api_provider(bot_provider, aiogram.Bot)
    api.register_api_provider(dispatcher_provider, aiogram.Dispatcher)
    log.info('Starting telegram bot...')
    try:
        # ДА ЯПОНСКИЙ ГОРОДОВОЙ! aiogram пожирает сигналы, не позволяя другим частям программы среагировать на них,
        # если не указать handle_signals=False
        async with background_task(tgdispatcher.start_polling(bot, handle_signals=False)):
            yield
    finally:
        log.info('Telegram bot stopped.')
