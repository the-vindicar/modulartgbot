"""This submodule deals with retrieving course participants."""
from typing import Optional, Any, Collection

from pydantic import BaseModel, PositiveInt, Field

from .common import *
from .users import RCustomField, RPreference, RBaseUser

__all__ = [
    'EnrolMixin',
    'RCourseMention', 'REnrolledUser',
    'RGroup', 'RRole', 'RPreference', 'RCustomField', 'RBaseUser'
]


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


class REnrolledUser(RBaseUser):
    lastcourseaccess: Optional[Timestamp] = None
    groups: list[RGroup] = Field(default_factory=list)
    roles: list[RRole] = Field(default_factory=list)
    enrolledcourses: list[RCourseMention] = Field(default_factory=list)


class EnrolMixin(WebServiceFunctions):
    """Mixin providing methods for working with course participants."""
    async def get_enrolled_users(
            self,
            courseid: int,
            options: Collection[Option]
    ) -> list[REnrolledUser]:
        """Retrieves all users, enrolled into the given course.
        :param courseid: ID of the course in question.
        :param options: Search options: withcapability, groupid, onlyactive, onlysuspended, userfields,
            limitfrom, limitnumber, sortby, sortdirection.
        :returns: List of enrolled users."""
        return await self._owner(
            'core_enrol_get_enrolled_users', dict(
                courseid=courseid, options=options
            ), model=list[REnrolledUser])
