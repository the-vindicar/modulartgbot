import datetime
import typing as tp

__all__ = ['MoodleFunctions']

if tp.TYPE_CHECKING:
    from ._moodle import Moodle


class MoodleFuncWrapper(tp.Protocol):
    async def __call__(self, *,
                       key: tp.Union[str, None] = None,
                       **kwargs
                       ) -> tp.Union[tp.List, tp.Dict[str, tp.Any]]:
        ...


class MoodleFunctions:
    __slots__ = ('__owner', )

    def __init__(self, owner: 'Moodle'):
        self.__owner = owner

    def __getattr__(self, item) -> MoodleFuncWrapper:
        async def wrapper(*, key: tp.Union[str, None] = None, **kwargs):
            return await self(func=item, kwargs=kwargs, key=key)
        wrapper.__name__ = item
        return wrapper  # noqa

    def transform_param(self, name: str, value: tp.Any) -> dict[str, tp.Any]:
        if isinstance(value, (tuple, list, set, frozenset)):
            result = {}
            for i, val in enumerate(value):
                result.update(self.transform_param(f'{name}[{i}]', val))
            return result
        elif isinstance(value, dict):
            result = {}
            for key, val in value.items():
                result.update(self.transform_param(f'{name}[{key}]', val))
            return result
        elif isinstance(value, datetime.datetime):
            return {name: int(value.astimezone(self.__owner.timezone).timestamp())}
        elif isinstance(value, (int, float, str)):
            return {name: value}
        else:
            raise TypeError(f'Unsupported type for parameter {name!r}: {type(value)!r}')

    async def __call__(self, func: str, kwargs: tp.Dict[str, tp.Any],
                       key: tp.Union[str, None] = None
                       ) -> tp.Union[tp.List, tp.Dict[str, tp.Any]]:
        params = {}
        for name, value in kwargs.items():
            params.update(self.transform_param(name, value))
        params.update({
            'wsfunction': func,
            'wstoken': self.__owner.token,
            'moodlewsrestformat': 'json'
        })
        result = await self.__owner.query(self.__owner.base_url + 'webservice/rest/server.php',
                                          key=key, params=params)
        return result
