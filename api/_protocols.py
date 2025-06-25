"""Описание основных протоколов взаимодействия ядра и модулей."""
import typing as t

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncAttrs
from quart import Blueprint


__all__ = [
    'CoreAPI', 'PluginAPI', 'APIProvider',
    'ConfigManager', 'DBModel'
]
_T = t.TypeVar('_T', infer_variance=True)
_Provider = t.Coroutine[t.Any, t.Any, _T]


class DBModel(AsyncAttrs, DeclarativeBase):
    """Основная модель SQLAlchemy для работы с базой данных."""
    pass


class ConfigManager(t.Protocol[_T]):
    """Менеджер конфигурации, обеспечивающий загрузку и сохранение конфигов модулей."""
    async def load(self, name: str, dataclass: t.Type[_T]) -> _T:
        """Загружает конфиг с указанным именем, помещая значения в экземпляр указанного датакласса.
        :param name: Имя конфига (обычно совпадает с именем модуля).
        :param dataclass: Датакласс, в который следует обернуть содержимое конфига."""
        ...

    async def save(self, name: str, config: _T) -> None:
        """Сохраняет конфиг с указанным именем, забирая значения из экземпляра датакласса.
        :param name: Имя конфига (обычно совпадает с именем модуля).
        :param config: Объект, из которого следует взять содержимое конфига."""
        ...


class APIProvider(t.Protocol[_T]):
    """Провайдер, предоставляющий объект-зависимость по запросу модуля."""
    async def __call__(self) -> _T:
        ...


class CoreAPI(t.Protocol[_T]):
    """API, предоставляемое ядром программы модулям."""
    config: ConfigManager

    def register_api_provider(self, provider: t.Union[APIProvider[_T], _T], klass: t.Type[_T]) -> None:
        """Позволяет предоставить объект для использования другими модулями.
        :param provider: Либо непосредственно предоставляемый объект, либо корутина без параметров,
        возвращающая предоставляемый объект.
        :param klass: Класс, которому принадлежит предоставляемый объект. Модули-получатели будут указывать его
        при запросе этого объекта.
        """
        ...

    def get_api_provider(self, klass: t.Type[_T]) -> APIProvider[_T]:
        """Позволяет получить провайдер-посредник, через который можно получать объекты из других модулей.
        :param klass: Класс, которому принадлежит желаемый объект.
        :returns: Корутина без параметров, которая вернёт экземпляр указанного класса."""
        ...

    async def __call__(self, klass: t.Type[_T]) -> _T:
        """Позволяет получить экземпляр желаемого класса, экспортируемого другим модулем."""
        ...

    def register_web_router(self, blueprint: Blueprint) -> None:
        """Позволяет зарегистрировать blueprint в веб-сервере."""
        ...


class PluginAPI(t.Protocol):
    """Описание API, предоставляемого плагином."""
    requires: t.Iterable[t.Union[t.Type[_T], str]]  # список классов, экспортируемых другими модулями, или имён модулей
    provides: t.Iterable[t.Type[_T]]  # список классов, экспортируемых этим модулем

    @staticmethod
    def lifetime(api: CoreAPI) -> t.AsyncGenerator:
        """Тело модуля. Код до yield должен подготавливать работу модуля, код после - завершать её."""
        ...
