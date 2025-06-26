"""This submodule deals with retrieving grades."""
from typing import Optional, Any
from pydantic import BaseModel, Field, ConfigDict, PositiveInt
from .common import *


__all__ = [
    'GradesMixin',
    'RGradeItem', 'RGradeLeader', 'RGradeColumn', 'RUserGrade', 'RUserGradeTable', 'RGradesTables',
    'RGradeItemsItem', 'RGradeItems', 'RGradeItemsUserGrade', 'RGradeItems'
]


class RGradeItem(BaseModel):
    classname: str = Field(alias='class')
    colspan: int
    content: str
    id: str

    model_config = ConfigDict(populate_by_name=True)


class RGradeLeader(BaseModel):
    classname: str = Field(alias='class')
    rowspan: int

    model_config = ConfigDict(populate_by_name=True)


class RGradeColumn(BaseModel):
    classname: str = Field(alias='class')
    content: str
    headers: str

    model_config = ConfigDict(populate_by_name=True)


class RUserGrade(BaseModel):
    parentcategories: list[int]
    itemname: Optional[RGradeItem] = None
    leader: Optional[RGradeLeader] = None
    weight: Optional[RGradeColumn] = None
    grade: Optional[RGradeColumn] = None
    range: Optional[RGradeColumn] = None
    percentage: Optional[RGradeColumn] = None
    lettergrade: Optional[RGradeColumn] = None
    rank: Optional[RGradeColumn] = None
    average: Optional[RGradeColumn] = None
    feedback: Optional[RGradeColumn] = None
    contributiontocoursetotal: Optional[RGradeColumn] = None


class RUserGradeTable(BaseModel):
    courseid: PositiveInt
    userid: PositiveInt
    userfullname: str
    maxdepth: int
    tabledata: list[RUserGrade]


class RGradesTables(BaseModel):
    tables: list[RUserGradeTable]
    warnings: list[RWarning]


class RGradeItemsItem(BaseModel):
    id: PositiveInt
    itemname: Optional[str]
    itemtype: str
    itemmodule: Optional[str]
    iteminstance: PositiveInt
    itemnumber: Optional[int]
    idnumber: Any
    categoryid: Optional[PositiveInt]
    outcomeid: Optional[int] = None
    scaleid: Optional[int] = None
    locked: Optional[bool] = None
    cmid: Optional[int] = None
    weightraw: Optional[float] = None
    weightformatted: Optional[str] = None
    status: Optional[str] = None
    graderaw: Optional[float] = None
    grademin: Optional[float] = None
    grademax: Optional[float] = None
    gradedatesubmitted: Optional[Timestamp] = None
    gradedategraded: Optional[Timestamp] = None
    gradehiddenbydate: Optional[bool] = None
    gradeneedsupdate: Optional[bool] = None
    gradeishidden: Optional[bool] = None
    gradeislocked: Optional[bool] = None
    gradeisoverridden: Optional[bool] = None
    gradeformatted: Optional[str] = None
    rangeformatted: Optional[str] = None
    percentageformatted: Optional[str] = None
    lettergradeformatted: Optional[str] = None
    averageformatted: Optional[str] = None
    rank: Optional[int] = None
    numusers: Optional[int] = None
    feedback: Optional[str] = None
    feedbackformat: Optional[FormatEnum] = None


class RGradeItemsUserGrade(BaseModel):
    courseid: PositiveInt
    courseidnumber: Any
    userid: PositiveInt
    userfullname: str
    useridnumber: Any
    maxdepth: int
    gradeitems: list[RGradeItemsItem]


class RGradeItems(BaseModel):
    usergrades: list[RGradeItemsUserGrade]
    warnings: list[RWarning]


class GradesMixin:
    """Mixin providing methods for working with grades."""
    async def gradereport_user_get_grades_table(
            self: WebServiceAdapter,
            courseid: int,
            userid: int = None,
            groupid: int = None
    ) -> RGradesTables:
        """Get the user's report grades table for a course. If you just want to know the grades,
        consider using gradereport_user_get_grade_items() instead.
        :param courseid: ID of the course for which grades are retrieved.
        :param userid: ID of the user for whom grades are retrieved. None means all users.
        :param groupid: ID of the group for which grades are retrieved. None means all groups.
        :returns: Grade report table.
        """
        return await self('gradereport_user_get_grades_table', dict(
            courseid=courseid, userid=userid, groupid=groupid
        ), model=RGradesTables)

    async def gradereport_user_get_grade_items(
            self: WebServiceAdapter,
            courseid: int,
            userid: int = None,
            groupid: int = None
    ) -> RGradeItems:
        """Returns the complete list of grade items for users in a course.
        :param courseid: ID of the course for which grades are retrieved.
        :param userid: ID of the user for whom grades are retrieved. None means all users.
        :param groupid: ID of the group for which grades are retrieved. None means all groups.
        :returns: List of grades.
        """
        return await self('gradereport_user_get_grade_items', dict(
            courseid=courseid, userid=userid, groupid=groupid
        ), model=RGradeItems)
