"""Различные мелкие полезные утилиты."""
import asyncio
import contextlib
import datetime
import itertools
import logging
import typing as t


__all__ = ['aiobatch', 'background_task', 'IntervalScheduler']
_T = t.TypeVar('_T')


async def aiobatch(src: t.AsyncIterable[_T], batch_size: int) -> t.AsyncIterable[list[_T]]:
    """Группирует содержимое асинхронного генератора `src` в пакеты по `batch_size` элементов."""
    batch_list = []
    async for item in src:
        batch_list.append(item)
        if len(batch_list) >= batch_size:
            yield batch_list
            batch_list = []
    if batch_list:
        yield batch_list


def done_callback(task: asyncio.Task):
    """Реагирует на завершение фоновой задачи. Если она завершилась из-за исключения, немедленно выводит запись
    об этом исключении в журнал работы."""
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


class IntervalScheduler(t.Generic[_T]):
    """Описывает один цикл опроса, в течении которого происходит опрос всех указанных объектов."""
    def __init__(self,
                 duration: datetime.timedelta,
                 batch_size: int = 1,
                 alignment: float = 1.0):
        """
        :param duration: Длительность одного цикла опроса. Этот цикл делится на интервалы по числу групп.
        :param batch_size: Максимальный размер группы, опрашиваемой за один раз.
        :param alignment: Смещение момента опроса группы внутри интервала.
        0.0 означает, что группа будет опрошена в начале своего интервала, 0.5 - в середине, 1.0 - в конце.
        Если смещение не 1.0, то в конце цикла опроса всех групп будет добавлена ещё одна пустая группа.
        """
        self.duration: datetime.timedelta = duration
        self.batch_size: int = batch_size
        self.alignment = min(1.0, max(0.0, alignment))
        self.events: list[tuple[datetime.datetime, tuple[_T, ...]]] = []

    def is_empty(self) -> bool:
        """Возвращает истину, если не осталось опрашиваемых объектов, и список пора обновить."""
        return not bool(self.events)

    def set_queried_objects(self, objects: t.Collection[_T], start: datetime.datetime) -> None:
        """Задаёт список объектов, которые должны быть опрошены в течение одного интервала.
        Интервал начинается с указанного момента, объекты распределяются по нему равномерно,
        группами не более заданного размера.

        :param objects: Коллекция опрашиваемых объектов.
        :param start: С какого момента начать отсчёт интервала."""
        self.events.clear()
        if not objects:
            return

        if self.batch_size > 0:
            batch_count = len(objects) // self.batch_size + (1 if len(objects) % self.batch_size > 0 else 0)
            batch_interval = self.duration / batch_count
            ts = start.astimezone(datetime.timezone.utc) + batch_interval * self.alignment
            for chunk in itertools.batched(objects, self.batch_size):
                self.events.append((ts, chunk))
                ts = ts + batch_interval
            if self.alignment < 1.0:
                self.events.append((ts, ()))
        else:
            ts = start.astimezone(datetime.timezone.utc) + self.duration
            self.events.append((ts, tuple(objects)))

    def pop_all_objects(self) -> list[_T]:
        """Извлекает и возвращает список всех оставшихся объектов."""
        all_objs = []
        for _ts, objects in self.events:
            all_objs.extend(objects)
        self.events.clear()
        return all_objs

    def pop_triggered_objects(self, now: datetime.datetime) -> list[_T]:
        """Извлекает и возвращает список объектов, которые следует опросить к моменту now. Может вернуть пустой список!
        Объекты удаляются из списка отслеживаемых, чтобы избежать их повторного опроса.
        :param now: Текущий момент времени.
        :returns: Список объектов, которые следует опросить. Может быть пуст."""
        now = now.astimezone(datetime.timezone.utc)
        past = []
        for i in range(len(self.events) - 1, -1, -1):
            ts, objects = self.events[i]
            if ts <= now:
                del self.events[i]
                past.extend(objects)
        return past

    def get_next_trigger_time(self) -> t.Optional[datetime.datetime]:
        """Возвращает время, когда нужно будет опросить следующую партию объектов, или None, если опрашивать нечего."""
        if not self.events:
            return None
        return self.events[0][0]
