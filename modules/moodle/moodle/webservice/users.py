"""This submodule deals with retrieving users, be that in general or course participants."""
from typing import Optional, Any, Collection
from enum import StrEnum

from pydantic import BaseModel, PositiveInt, AnyHttpUrl, Field

from .common import *


__all__ = [
    'UsersMixin',
    'RCourseMention', 'REnrolledUser',
    'RGroup', 'RRole', 'RPreference', 'RCustomField',
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


class RGroup(BaseModel):
    id: PositiveInt
    name: str
    description: Optional[str]
    descriptionformat: Any


class RRole(BaseModel):
    roleid: PositiveInt
    name: str
    shortname: str
    sortorder: int


class RCourseMention(BaseModel):
    id: PositiveInt
    fullname: str
    shortname: str


class _RBaseUser(BaseModel):
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


class REnrolledUser(_RBaseUser):
    lastcourseaccess: Optional[Timestamp] = None
    groups: list[RGroup] = Field(default_factory=list)
    roles: list[RRole] = Field(default_factory=list)
    enrolledcourses: list[RCourseMention] = Field(default_factory=list)


class RUserDescription(_RBaseUser):
    theme: Optional[str] = None
    timezone: Optional[str] = None


class UserByField(StrEnum):
    """Fields that can be used to search users on Moodle server."""
    ID = 'id'
    ID_NUMBER = 'idnumber'
    USERNAME = 'username'
    EMAIL = 'email'


class UsersMixin:
    """Mixin providing methods for working with users."""
    async def core_enrol_get_enrolled_users(
            self: WebServiceAdapter,
            courseid: int,
            options: Collection[Option]
    ) -> list[REnrolledUser]:
        """Retrieves all users, enrolled into the given course.
        :param courseid: ID of the course in question.
        :param options: Search options: withcapability, groupid, onlyactive, onlysuspended, userfields,
            limitfrom, limitnumber, sortby, sortdirection.
        :returns: List of enrolled users."""
        return await self(
            'core_enrol_get_enrolled_users', dict(
                courseid=courseid, options=options
            ), model=list[REnrolledUser])

    async def core_user_get_users_by_field(
            self: WebServiceAdapter,
            field: UserByField | str,
            values: Collection[int | str]
    ) -> list[RUserDescription]:
        """Find users by given filter.
        :param field: Field name.
        :param values: Set of values to match.
        :returns: List of users."""
        return await self(
            'core_user_get_users_by_field', dict(
                field=field, values=values
            ), model=list[RUserDescription])
