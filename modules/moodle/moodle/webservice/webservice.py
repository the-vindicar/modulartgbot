"""Contains classes that simplify working with Moodle Web API."""
import typing as tp

from pydantic import JsonValue

if tp.TYPE_CHECKING:
    from modules.moodle.moodle import Moodle

from .common import ModelType
from .siteinfo import SiteInfoMixin
from .courses import CoursesMixin
from .users import UsersMixin
from .assignments import AssignMixin
from .grades import GradesMixin
from .messages import MessagesMixin


__all__ = ['MoodleFunctions']


class MoodleFunctions(CoursesMixin, UsersMixin, AssignMixin, SiteInfoMixin, GradesMixin, MessagesMixin):
    """Moodle Web API wrapper class that provides methods with properly type-hinted parameters and returns.
    If you need to call an API function that does not have a pre-defined method, use __call__() and provide
    function name first. Optionally, provide a Pydantic model to validate the result against."""
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
        """Calls a Moodle Web API function.
        :param func: Function name, such as `core_webservice_get_site_info`.
        :param params: Dictionary of arguments passed to the function. See .query() in :class:`Moodle`.
        :param model: A Pydantic model used to validate the response. Can be omitted to receive simple decoded JSON.
        :returns: Instance of the provided model. If no model is provided, a dict/list containing server's
            JSON response."""
        params.update({
            'wsfunction': func,
            'wstoken': self.__owner.token,
            'moodlewsrestformat': 'json'
        })
        result = await self.__owner.query('webservice/rest/server.php', params=params, model=model)
        return result
