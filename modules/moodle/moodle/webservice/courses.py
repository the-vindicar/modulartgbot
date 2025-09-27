"""This submodule deals with retrieving course information."""
from typing import Optional, Any, Collection, Union
from enum import StrEnum
from pydantic import BaseModel, PositiveInt
from .common import *


__all__ = [
    'CoursesMixin',
    'CourseTimelineClassification', 'RCourse', 'RPaginatedCourses',
]


class CourseTimelineClassification(StrEnum):
    """See core_course_get_enrolled_courses_by_timeline_classification()."""
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


class CoursesMixin(WebServiceFunctions):
    """Mixin providing methods for working with courses."""
    async def get_enrolled_courses_by_timeline_classification(
            self,
            classification: Union[str, CourseTimelineClassification],
            limit: int = 0,
            offset: int = 0,
            sort: str = None,
            customfieldname: str = None,
            customfieldvalue: str = None,
            searchvalue: str = None,
            requiredfields: Collection[str] = None
    ) -> RPaginatedCourses:
        """Retrieves courses we are enrolled in, with given position on the timeline.
        :param classification: Which courses to retrieve (past, current, future, hidden, etc).
        :param limit: Pagination - how many courses to retrieve.
        :param offset: Pagination - how many courses to skip. See RPaginatedCourses.nextoffset.
        :param sort: SQL sort string for results. Hopefully not vulnerable to injections.
        :param customfieldname: If classification == 'customfield', specifies a name for a course field to filter by.
        :param customfieldvalue: If classification == 'customfield', specifies a value for a course field to filter by.
        :param searchvalue: If we want to filter courses via search as well.
        :param requiredfields: Which fields to return about each course. Useful to reduce the bandwidth usage.
        :returns: A page from the list of courses.
        """
        return await self._owner(
            'core_course_get_enrolled_courses_by_timeline_classification', dict(
                classification=classification,
                limit=limit, offset=offset, sort=sort,
                customfieldname=customfieldname, customfieldvalue=customfieldvalue, searchvalue=searchvalue,
                requiredfields=requiredfields
            ), model=RPaginatedCourses)
