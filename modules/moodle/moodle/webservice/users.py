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
    username: Optional[str]
    firstname: Optional[str]
    lastname: Optional[str]
    fullname: str
    email: Optional[str]
    address: Optional[str]
    phone1: Optional[str]
    phone2: Optional[str]
    department: Optional[str]
    institution: Optional[str]
    idnumber: Optional[Any]
    interests: Optional[str]
    firstaccess: Optional[Timestamp]
    lastaccess: Optional[Timestamp]
    lastcourseaccess: Optional[Timestamp]
    description: Optional[str]
    descriptionformat: Optional[FormatEnum]
    city: Optional[str]
    country: Optional[str]
    profileimageurlsmall: Optional[AnyHttpUrl]
    profileimageurl: Optional[AnyHttpUrl]
    customfields: Optional[list[RCustomField]]
    groups: Optional[list[RGroup]]
    roles: Optional[list[RRole]]
    preferences: Optional[list[RPreference]]
    enrolledcourses: Optional[list[RCourseMention]]


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
