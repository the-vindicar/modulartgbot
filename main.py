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
    data = Path(os.environ.get('MULTIBOT_DATA', str(Path(sys.argv[0]).parent / 'data')))
    cfg = ConfigManagerImpl(data / 'config')

    class RootPathMiddleware:
        """Гарантирует, что мы учитываем путь к корню сайта."""
        def __init__(self, app, root_path: str = ""):
            self.app = app
            self.root_path = root_path

        async def __call__(self, scope, receive, send):
            # Если nginx передал SCRIPT_NAME — используем его
            headers = dict((k.decode(), v.decode()) for k, v in scope.get("headers", []))
            script_name = headers.get("script_name") or headers.get("x-script-name")
            if script_name:
                scope["root_path"] = script_name
            elif self.root_path:
                scope["root_path"] = self.root_path

            await self.app(scope, receive, send)

    @dataclasses.dataclass
    class WebConfig:
        """Конфигурация веб-сервера."""
        host: str = '0.0.0.0'
        port: int = 8080
        root: str = ''
        ca_certs: t.Optional[str] = None
        certfile: t.Optional[str] = None
        keyfile: t.Optional[str] = None

    app = quart.Quart(__name__)

    @app.while_serving
    async def context():
        """Этот контекст выполняется до yield при запуске сервера, а остальная часть - при остановке сервера."""
        await setup_logging(cfg, app)
        modules_context = modules_lifespan(
            webapp=app,
            cfg=cfg,
            module_whitelist=[
                'db', 'telegram',
                'users', 'users_extra',
                'moodle', 'moodle_monitoring', 'file_comparison',
                'workload', 'timetable_monitoring'
            ]
        )
        async with modules_context:
            yield

    web_cfg = await cfg.load('web', WebConfig)
    app.config['APPLICATION_ROOT'] = os.environ.get('APPLICATION_ROOT', web_cfg.root)
    app.asgi_app = RootPathMiddleware(app.asgi_app, app.config['APPLICATION_ROOT'])
    await app.run_task(
        web_cfg.host, web_cfg.port,
        ca_certs=web_cfg.ca_certs, certfile=web_cfg.certfile, keyfile=web_cfg.keyfile,
    )


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
