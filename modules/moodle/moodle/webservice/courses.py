"""This submodule deals with retrieving course information."""
from typing import Optional, Any, Collection, Union
from enum import StrEnum, IntEnum
from pydantic import BaseModel, AnyHttpUrl, Field, TypeAdapter
from .common import *
from .cm_availability import AvOperator


__all__ = [
    'CoursesMixin',
    'CourseTimelineClassification', 'RCourse', 'RPaginatedCourses',
]


class CompletionType(IntEnum):
    """Type of completion tracking for a module."""
    NONE = 0
    MANUAL = 1
    AUTO = 2


class GroupMode(IntEnum):
    """Group mode for a module."""
    NONE = 0
    SEPARATE = 1
    VISIBLE = 2


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
    id: MoodleID
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


class RCourseModuleDate(BaseModel):
    """A component of module description."""
    label: str
    timestamp: Timestamp
    relativeto: Optional[Timestamp] = None
    dataid: Optional[str] = None


class RCourseModuleContents(BaseModel):
    """Files attached to a course module."""
    type: str
    filename: str
    filepath: Optional[str]
    filesize: int
    fileurl: AnyHttpUrl
    isexternalfile: Optional[bool] = None
    repositorytype: Optional[Any] = None
    content: Any = None
    timemodified: Optional[Timestamp] = None
    timecreated: Optional[Timestamp] = None
    sortorder: Optional[int] = None
    userid: Optional[MoodleID] = None
    author: Optional[str] = None
    license: Optional[str] = None
    tags: list = Field(default_factory=list)


class RContentsInfo(BaseModel):
    """Contents summary for a course module."""
    filescount: int
    filessize: int
    lastmodified: Timestamp
    mimetypes: list[str]
    repositorytype: str


class RCourseModule(BaseModel):
    """A module contained within the course."""
    id: MoodleID
    name: str
    modicon: AnyHttpUrl
    modname: str
    modplural: str
    purpose: str
    indent: int
    url: Optional[AnyHttpUrl] = None
    branded: Optional[bool] = None
    description: Optional[str] = None
    visible: Optional[bool] = None
    uservisible: Optional[bool] = None
    availabilityinfo: Optional[str] = None
    availability: Optional[str] = None
    visibleoncoursepage: Optional[bool] = None
    instance: Optional[OptionalMoodleID] = None
    contextid: Optional[OptionalMoodleID] = None
    onclick: Optional[str] = None
    afterlink: Optional[str] = None
    activitybadge: Optional[Any] = None
    customdata: Optional[str] = None
    noviewlink: Optional[bool] = None
    candisplay: Optional[bool] = None
    completion: Optional[CompletionType] = None
    completiondata: Optional[Any] = None
    downloadcontent: Optional[int] = None
    dates: list[RCourseModuleDate] = Field(default_factory=list)
    groupmode: Optional[GroupMode] = None
    contents: list[RCourseModuleContents] = Field(default_factory=list)
    contentsinfo: Optional[RContentsInfo] = None

    @property
    def availability_conditions(self) -> Optional[AvOperator]:
        """Presents availability string as condition object tree."""
        if self.availability is None:
            return None
        adapter = TypeAdapter(AvOperator)
        return adapter.validate_json(self.availability)


class RCourseSection(BaseModel):
    """A section within the course."""
    id: MoodleID
    name: str
    summary: str
    modules: list[RCourseModule]
    visible: Optional[bool] = None
    uservisible: Optional[bool] = None
    availabilityinfo: Optional[str] = None
    section: Optional[int] = None
    summaryformat: FormatEnum = FormatEnum.FORMAT_HTML
    component: Optional[Any] = None
    itemid: Optional[OptionalMoodleID] = None


class RAdvancedGrading(BaseModel):
    """Describes advanced grading."""
    area: str
    method: Optional[str]


class RGradingOutcome(BaseModel):
    """Describes a grading outcome."""
    id: str
    name: str
    scale: str


class RCourseModulePart(BaseModel):
    """Describes a course module."""
    id: MoodleID
    course: MoodleID
    module: int
    name: str
    modname: str
    instance: MoodleID
    section: MoodleID
    sectionnum: int
    groupmode: GroupMode
    groupingid: OptionalMoodleID
    completion: CompletionType
    idnumber: Optional[str] = None
    added: Optional[Timestamp] = None
    score: Optional[int] = None
    indent: Optional[int] = None
    visible: Optional[bool] = None
    visibleoncoursepage: Optional[bool] = None
    visibleold: Optional[bool] = None

    completiongradeitemnumber: Optional[int] = None
    completionpassgrade: Optional[int] = None
    completionview: Optional[int] = None
    completionexpected: Optional[Timestamp] = None

    showdescription: Optional[bool] = None
    downloadcontent: Optional[bool] = None
    availability: Optional[str] = None

    grade: Optional[float | int | str] = None
    gradepass: Optional[float] = None
    gradecat: Optional[MoodleID] = None
    scale: Optional[str] = None
    advancedgrading: list[RAdvancedGrading] = Field(default_factory=list)
    outcomes: list[RGradingOutcome] = Field(default_factory=list)


class RCourseModuleResponse(BaseModel):
    """A response to querying a course module."""
    cm: Optional[RCourseModulePart] = None
    warnings: list[RWarning] = Field(default_factory=list)


class CoursesMixin(WebServiceFunctions):
    """Mixin providing methods for working with courses."""
    async def get_course_contents(
            self,
            courseid: MoodleID,
            *,
            excludemodules: bool = None,
            excludecontents: bool = None,
            includestealthmodules: bool = None,
            sectionid: MoodleID = None,
            sectionnumber: int = None,
            cmid: MoodleID = None,
            modname: str = None,
            modid: MoodleID = None,
            options: Collection[Option] = ()
    ) -> list[RCourseSection]:
        """Retrieves course contents.
        The expected keys (value format) are:
            ``excludemodules`` (bool) Do not return modules, return only the sections structure
            ``excludecontents`` (bool) Do not return module contents (i.e: files inside a resource)
            ``includestealthmodules`` (bool) Return stealth modules for students in a special section (with id -1)
            ``sectionid`` (int) Return only this section
            ``sectionnumber`` (int) Return only this section with number (order)
            ``cmid`` (int) Return only this module information (among the whole sections structure)
            ``modname`` (string) Return only modules with this name "label, forum, etc..."
            ``modid`` (int) Return only the module with this id"""
        opts = list(options)
        if excludemodules is not None:
            opts.append({'name': 'excludemodules', 'value': excludemodules})
        if excludecontents is not None:
            opts.append({'name': 'excludecontents', 'value': excludecontents})
        if includestealthmodules is not None:
            opts.append({'name': 'includestealthmodules', 'value': includestealthmodules})
        if sectionid is not None:
            opts.append({'name': 'sectionid', 'value': sectionid})
        if sectionnumber is not None:
            opts.append({'name': 'sectionnumber', 'value': sectionnumber})
        if cmid is not None:
            opts.append({'name': 'cmid', 'value': cmid})
        if modname is not None:
            opts.append({'name': 'modname', 'value': modname})
        if modid is not None:
            opts.append({'name': 'modid', 'value': modid})
        return await self._owner('core_course_get_contents', dict(
            courseid=courseid, options=opts
        ), model=list[RCourseSection])

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

    async def get_course_module_by_instance(
            self,
            module: str,
            instance: MoodleID
    ) -> RCourseModuleResponse:
        """Retrieves a course module by its plugin name and instance ID (the latter makes sense only for the plugin)."""
        return await self._owner('core_course_get_course_module_by_instance', dict(
            module=module, instance=instance
        ), model=RCourseModuleResponse)

    async def get_course_module(self, cmid: MoodleID) -> RCourseModuleResponse:
        """Retrieves course module by its cmid. CMID only makes sense for the course itself, and not for plugins."""
        return await self._owner('core_course_get_course_module', dict(cmid=cmid), model=RCourseModuleResponse)
