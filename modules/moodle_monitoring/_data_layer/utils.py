import typing as t
import datetime


__all__ = ['ts2int', 'int2ts']


@t.overload
def ts2int(ts: datetime.datetime) -> int:
    ...


@t.overload
def ts2int(ts: None) -> None:
    ...


def ts2int(ts: t.Optional[datetime.datetime]) -> t.Optional[int]:
    """Преобразует дату-время в любой часовой зоне в Unix timestamp в часовой зоне UTC, округляя её до секунды."""
    return int(ts.astimezone(datetime.timezone.utc).timestamp()) if ts is not None else None


@t.overload
def int2ts(val: int) -> datetime.datetime:
    ...


@t.overload
def int2ts(val: None) -> None:
    ...


def int2ts(val: t.Optional[int]) -> t.Optional[datetime.datetime]:
    """Преобразует Unix timestamp в часовой зоне UTC в дату-время в той же часовой зоне."""
    return datetime.datetime.fromtimestamp(val, datetime.timezone.utc) if val is not None else None
