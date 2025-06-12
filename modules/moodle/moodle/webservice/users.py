from typing import Optional, Any, Collection
from pydantic import BaseModel, PositiveInt, AnyHttpUrl, RootModel
from .common import *


__all__ = [
    'UsersMixin',
    'RCourseMention', 'REnrolledUser', 'REnrolledUsers',
    'RGroup', 'RRole', 'RPreference', 'RCustomField',
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


class REnrolledUser(BaseModel):
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
    lastcourseaccess: Optional[Timestamp] = None
    description: Optional[str] = None
    descriptionformat: Optional[FormatEnum] = None
    city: Optional[str] = None
    country: Optional[str] = None
    profileimageurlsmall: Optional[AnyHttpUrl] = None
    profileimageurl: Optional[AnyHttpUrl] = None
    customfields: Optional[list[RCustomField]] = None
    groups: Optional[list[RGroup]] = None
    roles: Optional[list[RRole]] = None
    preferences: Optional[list[RPreference]] = None
    enrolledcourses: Optional[list[RCourseMention]] = None


class REnrolledUsers(RootModel[list[REnrolledUser]]):
    pass


class UsersMixin:
    async def core_enrol_get_enrolled_users(
            self: WebServiceAdapter,
            courseid: int,
            options: Collection[Option]
    ) -> REnrolledUsers:
        return await self(
            'core_enrol_get_enrolled_users', dict(
                courseid=courseid, options=options
            ), model=REnrolledUsers)
