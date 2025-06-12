import typing as tp

__all__ = ['MoodleFunctions']

if tp.TYPE_CHECKING:
    from modules.moodle.moodle import Moodle

from .common import *
from .courses import *
from .users import *
from .assignments import *


class MoodleFunctions(CoursesMixin, UsersMixin, AssignMixin):
    """Этот класс служит для вызова функций Moodle Web API."""
    __slots__ = ('__owner', )

    def __init__(self, owner: 'Moodle'):
        self.__owner = owner

    @tp.overload
    async def __call__(self, func: str, params: tp.Dict[str, tp.Any],
                       *, model: tp.Type[ModelType]
                       ) -> ModelType:
        ...

    @tp.overload
    async def __call__(self, func: str, params: tp.Dict[str, tp.Any],
                       *, model: None = None
                       ) -> tp.Union[tp.List, tp.Dict[str, tp.Any]]:
        ...

    async def __call__(self, func: str, params: tp.Dict[str, tp.Any],
                       *, model: tp.Type[ModelType] = None
                       ) -> tp.Union[ModelType, tp.List, tp.Dict[str, tp.Any]]:
        """Вызываем указанную функцию Moodle Web API.
        :param func: Имя функции, например, 'core_webservice_get_site_info'.
        :param params: Аргументы, передаваемые функции.
        :param model: Модель Pydantic, которой должен соответствовать ответ.
        :returns: Ответ сервера, декодированный из JSON."""
        params.update({
            'wsfunction': func,
            'wstoken': self.__owner.token,
            'moodlewsrestformat': 'json'
        })
        result = await self.__owner.query('webservice/rest/server.php', params=params, model=model)
        return result
