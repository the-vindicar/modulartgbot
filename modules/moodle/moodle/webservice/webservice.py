import typing as tp
import warnings

from pydantic import JsonValue

if tp.TYPE_CHECKING:
    from modules.moodle.moodle import Moodle

from .common import ModelType
from .siteinfo import SiteInfoMixin
from .courses import CoursesMixin
from .users import UsersMixin
from .assignments import AssignMixin
from .grades import GradesMixin


__all__ = ['MoodleFunctions']


class MoodleFunctions(CoursesMixin, UsersMixin, AssignMixin, SiteInfoMixin, GradesMixin):
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
                       ) -> JsonValue:
        ...

    async def __call__(self, func: str, params: tp.Dict[str, tp.Any],
                       *, model: tp.Type[ModelType] = None
                       ) -> tp.Union[ModelType, JsonValue]:
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
