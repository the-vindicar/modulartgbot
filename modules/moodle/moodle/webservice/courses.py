from typing import Optional, Any, Collection, Union
from enum import StrEnum
from pydantic import BaseModel, PositiveInt
from .common import *


__all__ = [
    'CoursesMixin',
    'CourseTimelineClassification', 'RCourse', 'RPaginatedCourses',
]


class CourseTimelineClassification(StrEnum):
    ALL_INCLUDING_HIDDEN = 'allincludinghidden'
    ALL = 'all'
    PAST = 'past'
    IN_PROGRESS = 'inprogress'
    FUTURE = 'future'
    HIDDEN = 'hidden'
    SEARCH = 'search'
    CUSTOM_FIELD = 'customfield'


class RCourse(BaseModel):
    id: PositiveInt
    fullname: str
    shortname: str
    idnumber: Any
    summary: Optional[Any]
    summaryformat: FormatEnum
    startdate: Timestamp
    enddate: Timestamp
    visible: bool
    showactivitydates: Optional[bool]
    showcompletionconditions: Optional[bool] = None
    pdfexportfont: Optional[str] = None


class RPaginatedCourses(BaseModel):
    courses: list[RCourse]
    nextoffset: int


class CoursesMixin:
    async def core_course_get_enrolled_courses_by_timeline_classification(
            self: WebServiceAdapter,
            classification: Union[str, CourseTimelineClassification],
            limit: int = 0,
            offset: int = 0,
            sort: str = None,
            customfieldname: str = None,
            customfieldvalue: str = None,
            searchvalue: str = None,
            requiredfields: Collection[str] = tuple()
    ) -> RPaginatedCourses:
        return await self(
            'core_course_get_enrolled_courses_by_timeline_classification', dict(
                classification=classification,
                limit=limit, offset=offset, sort=sort,
                customfieldname=customfieldname, customfieldvalue=customfieldvalue, searchvalue=searchvalue,
                requiredfields=requiredfields
            ), model=RPaginatedCourses)
