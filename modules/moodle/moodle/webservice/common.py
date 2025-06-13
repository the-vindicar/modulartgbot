from typing import Optional, Any, Annotated, TypeVar, TypedDict, Protocol, Type
from enum import Enum
from annotated_types import *
from pydantic import BaseModel, PositiveInt, AnyHttpUrl


__all__ = [
    'ModelType', 'WebServiceAdapter',
    'Timestamp', 'Option', 'FormatEnum', 'File', 'RWarning',

]
Timestamp = Annotated[int, Ge(0)]
ModelType = TypeVar('ModelType')


class WebServiceAdapter(Protocol):
    async def __call__(self, fn: str, params: dict[str, Any], *, model: Type[ModelType]) -> ModelType:
        ...


class FormatEnum(Enum):
    FORMAT_MOODLE = 0
    FORMAT_HTML = 1
    FORMAT_PLAIN = 2
    FORMAT_WIKI = 3
    FORMAT_MARKDOWN = 4


class Option(TypedDict):
    name: str
    value: Any


class File(BaseModel):
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
    item: str
    itemid: PositiveInt
    warningcode: Any
    message: str
