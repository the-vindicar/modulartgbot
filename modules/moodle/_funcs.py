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

    async def __call__(self, func: str, kwargs: tp.Dict[str, tp.Any],
                       key: tp.Union[str, None] = None
                       ) -> tp.Union[tp.List, tp.Dict[str, tp.Any]]:
        params = {
            'wsfunction': func,
            'wstoken': self.__owner.token,
            'moodlewsrestformat': 'json'
        }
        for name, value in kwargs.items():
            if isinstance(value, (tuple, list, set, frozenset)):
                value = list(value)
                if isinstance(value[0], dict):
                    for i, val in enumerate(value):
                        for k, v in val.items():
                            params[f'{name}[{i}][{k}]'] = v
                else:
                    params[f'{name}[]'] = value
            else:
                params[name] = value
        result = await self.__owner.query(self.__owner.base_url + 'webservice/rest/server.php',
                                          key=key, params=params)
        return result
