"""Модульная система для сопровождения работы преподавателя кафедры ИСТ (ну т.е. меня).
Если тебе приходится это поддерживать, я тебе сочувствую."""


async def main():
    """Тело программы. Конфигурирует и запускает веб-сервер.
    Все импорты и объявления спрятаны внутрь тела, чтобы облегчить использование multiprocessing и
    других основанных на нём приёмов (вроде concurrent.futures.ProccessPoolExecutor)."""

    import dataclasses
    import os
    import sys
    from pathlib import Path
    import typing as t

    import quart
    from dotenv import load_dotenv

    from api import modules_lifespan, ConfigManagerImpl, setup_logging

    load_dotenv()
    app = quart.Quart(__name__)
    data = Path(os.environ.get('MULTIBOT_DATA', str(Path(sys.argv[0]).parent / 'data')))
    cfg = ConfigManagerImpl(data / 'config')

    @dataclasses.dataclass
    class WebConfig:
        """Конфигурация веб-сервера."""
        host: str = '0.0.0.0'
        port: int = 8080
        ca_certs: t.Optional[str] = None
        certfile: t.Optional[str] = None
        keyfile: t.Optional[str] = None

    @app.while_serving
    async def context():
        """Этот контекст выполняется до yield при запуске сервера, а остальная часть - при остановке сервера."""
        await setup_logging(cfg, app)
        modules_context = modules_lifespan(
            webapp=app,
            cfg=cfg,
            module_whitelist=[
                'db', 'telegram',
                'moodle', 'moodle_monitoring',
                'users', 'users_extra',
                'file_comparison']
        )
        async with modules_context:
            yield

    web_cfg = await cfg.load('web', WebConfig)
    await app.run_task(
        web_cfg.host, web_cfg.port,
        ca_certs=web_cfg.ca_certs, certfile=web_cfg.certfile, keyfile=web_cfg.keyfile,
    )


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
