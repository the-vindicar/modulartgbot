from typing import Optional, Any, Annotated, TypeVar, TypedDict, Protocol, Type
from enum import StrEnum
from annotated_types import *
from pydantic import BaseModel, PositiveInt


__all__ = [
    'ModelType', 'WebServiceAdapter',
    'Timestamp', 'Option', 'FormatEnum', 'File', 'RWarning',

]
Timestamp = Annotated[int, Ge(0)]
ModelType = TypeVar('ModelType')


class WebServiceAdapter(Protocol):
    async def __call__(self, fn: str, params: dict[str, Any], *, model: Type[ModelType]) -> ModelType:
        ...


class FormatEnum(StrEnum):
    FORMAT_MOODLE = '0'
    FORMAT_HTML = '1'
    FORMAT_PLAIN = '2'
    FORMAT_WIKI = '3'
    FORMAT_MARKDOWN = '4'


class Option(TypedDict):
    name: str
    value: Any


class File(BaseModel):
    filename: Optional[str]
    filepath: Optional[str]
    filesize: Optional[int]
    fileurl: Optional[str]
    timemodified: Optional[Timestamp]
    mimetype: Optional[str]
    isexternalfile: Optional[bool]
    repositorytype: Optional[Any]
    icon: Optional[str]


class RWarning(BaseModel):
    item: str
    itemid: PositiveInt
    warningcode: Any
    message: str
