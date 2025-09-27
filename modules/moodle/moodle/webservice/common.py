"""General types and utilities to facilitate Web API function calls."""
from typing import Optional, Any, Annotated, TypeVar, TypedDict, Protocol, Type
from enum import Enum
from annotated_types import *
from pydantic import BaseModel, PositiveInt, AnyHttpUrl


__all__ = [
    'ModelType', 'WebServiceAdapter', 'WebServiceFunctions',
    'Timestamp', 'Option', 'FormatEnum', 'File', 'RWarning',
]
Timestamp = Annotated[int, Ge(0)]
ModelType = TypeVar('ModelType')


class WebServiceAdapter(Protocol):
    """A quick stub representing MoodleFunctions class. We only need one method of it anyway."""
    async def __call__(self, func: str, params: dict[str, Any], *, model: Type[ModelType]) -> ModelType:
        ...


class WebServiceFunctions:
    """A base for any functions pack class."""
    __slots__ = ('_owner',)

    def __init__(self, owner: WebServiceAdapter):
        self._owner = owner


class FormatEnum(Enum):
    """Possible text formats used in Moodle."""
    FORMAT_MOODLE = 0
    FORMAT_HTML = 1
    FORMAT_PLAIN = 2
    FORMAT_WIKI = 3
    FORMAT_MARKDOWN = 4


class Option(TypedDict):
    """Some API calls allow for a set of options in form of a list of name-value pairs."""
    name: str
    value: Any


class File(BaseModel):
    """Some file available on the Moodle server. Can be placed by teacher, student, or someone else."""
    filename: str
    filepath: str
    filesize: int
    fileurl: AnyHttpUrl
    timemodified: Timestamp
    mimetype: str
    isexternalfile: Optional[bool] = None
    repositorytype: Optional[Any] = None
    icon: Optional[str] = None


class RWarning(BaseModel):
    """Some API calls return a list of warnings if not all requested data could be returned."""
    item: str
    itemid: PositiveInt
    warningcode: Any
    message: str
