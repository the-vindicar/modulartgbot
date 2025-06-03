import typing as t

from quart import Blueprint


__all__ = [
    'CoreAPI', 'PluginAPI', 'APIProvider',
    # 'DBRow', 'AsyncDBCursor', 'AsyncDBConnection', 'AsyncDBAcquire',
    'ConfigManager'
]
_T = t.TypeVar('_T', infer_variance=True)
_Provider = t.Coroutine[t.Any, t.Any, _T]


class ConfigManager(t.Protocol[_T]):
    async def load(self, name: str, dataclass: t.Type[_T]) -> _T:
        ...

    async def save(self, name: str, config: _T) -> None:
        ...


class APIProvider(t.Protocol[_T]):
    async def __call__(self) -> _T:
        ...


class CoreAPI(t.Protocol[_T]):
    config: ConfigManager

    def register_api_provider(self, provider: APIProvider[_T], klass: t.Type[_T]) -> None:
        ...

    def get_api_provider(self, klass: t.Type[_T]) -> APIProvider[_T]:
        ...

    async def __call__(self, klass: t.Type[_T]) -> _T:
        ...

    def register_web_router(self, blueprint: Blueprint) -> None:
        ...


class PluginAPI(t.Protocol):
    requires: t.Iterable[t.Type[_T]]
    provides: t.Iterable[t.Type[_T]]

    @staticmethod
    def lifetime(api: CoreAPI) -> t.AsyncGenerator:
        ...
