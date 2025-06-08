import asyncio
import contextlib
import logging
import typing as t


__all__ = ['background_task']


def done_callback(task: asyncio.Task):
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        pass
    else:
        if exc is None or isinstance(exc, asyncio.CancelledError):
            return
        exc_info = (type(exc), exc, exc.__traceback__)
        task_name = task.get_name()
        coro_name = task.get_coro().__qualname__
        logging.root.critical('Uncaught exception in task %s running %s():',
                              task_name, coro_name, exc_info=exc_info)


@contextlib.asynccontextmanager
async def background_task(coro: t.Coroutine):
    """Гарантирует фоновый запуск указанной корутины при входе в асинхронный контекст (async with),
    и её завершение (отмену) при выходе из этого контекста."""
    task = asyncio.create_task(coro, name=f'{coro.__qualname__}()@{coro.cr_code.co_filename}')
    task.add_done_callback(done_callback)
    try:
        yield task
    finally:
        try:
            task.cancel()
            await task
        except asyncio.CancelledError:
            pass
