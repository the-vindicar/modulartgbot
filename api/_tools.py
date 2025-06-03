import asyncio
import contextlib
import typing as t


__all__ = ['background_task']


@contextlib.asynccontextmanager
async def background_task(coro: t.Coroutine):
    """Гарантирует фоновый запуск указанной корутины при входе в асинхронный контекст (async with),
    и её завершение (отмену) при выходе из этого контекста."""
    task = asyncio.create_task(coro)
    try:
        yield task
    finally:
        try:
            task.cancel()
            await task
        except asyncio.CancelledError:
            pass
