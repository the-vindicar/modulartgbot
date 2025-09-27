"""This submodule deals with retrieving users in general."""
from typing import Optional, Any, Collection, Union
from enum import StrEnum

from pydantic import BaseModel, PositiveInt, AnyHttpUrl, Field

from .common import *


__all__ = [
    'UsersMixin', 'RPreference', 'RCustomField', 'RBaseUser',
    'UserByField', 'RUserDescription'
]


class RCustomField(BaseModel):
    type: str
    value: Any
    name: str
    shortname: str


class RPreference(BaseModel):
    name: str
    value: Any


class RBaseUser(BaseModel):
    id: PositiveInt
    fullname: Optional[str] = None
    username: Optional[str] = None
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    phone1: Optional[str] = None
    phone2: Optional[str] = None
    department: Optional[str] = None
    institution: Optional[str] = None
    idnumber: Optional[Any] = None
    interests: Optional[str] = None
    firstaccess: Optional[Timestamp] = None
    lastaccess: Optional[Timestamp] = None
    city: Optional[str] = None
    country: Optional[str] = None
    customfields: list[RCustomField] = Field(default_factory=list)
    description: Optional[str] = None
    descriptionformat: Optional[FormatEnum] = None
    preferences: list[RPreference] = Field(default_factory=list)
    profileimageurlsmall: Optional[AnyHttpUrl] = None
    profileimageurl: Optional[AnyHttpUrl] = None


class RUserDescription(RBaseUser):
    theme: Optional[str] = None
    timezone: Optional[str] = None


class UserByField(StrEnum):
    """Fields that can be used to search users on Moodle server."""
    ID = 'id'
    ID_NUMBER = 'idnumber'
    USERNAME = 'username'
    EMAIL = 'email'


class UsersMixin(WebServiceFunctions):
    """Mixin providing methods for working with users."""
    async def get_users_by_field(
            self,
            field: Union[UserByField, str],
            values: Collection[Union[int, str]]
    ) -> list[RUserDescription]:
        """Find users by given filter.
        :param field: Field name.
        :param values: Set of values to match.
        :returns: List of users."""
        return await self._owner(
            'core_user_get_users_by_field', dict(
                field=field, values=values
            ), model=list[RUserDescription])
