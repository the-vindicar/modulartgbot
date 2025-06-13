from typing import Optional, Collection
from enum import StrEnum
from datetime import datetime
from pydantic import BaseModel, PositiveInt
from .common import *


__all__ = [
    'AssignMixin',
    'RAssignment', 'RAssignmentsPerCourse', 'RAssignments',
    'RAssignmentGradeset', 'RAssignmentsGrades', 'RAssignmentGrade',
    'RSubmissions', 'RSubmission', 'RAssignmentMention',
    'RSubmissionPlugin', 'RSubmissionEditorField', 'RSubmissionFileArea'
]


class SubmissionStatus(StrEnum):
    NEW = 'new'
    DRAFT = 'draft'
    SUBMITTED = 'submitted'
    REOPENED = 'reopened'


class GradingStatus(StrEnum):
    GRADED = 'graded'
    NOT_GRADED = 'notgraded'


class RAssignment(BaseModel):
    id: PositiveInt
    cmid: PositiveInt
    course: PositiveInt
    name: str
    nosubmissions: bool
    submissiondrafts: bool
    sendnotifications: bool
    sendlatenotifications: bool
    sendstudentnotifications: bool
    duedate: Timestamp
    allowsubmissionsfromdate: Timestamp
    grade: int
    gradepenalty: int
    timemodified: Timestamp
    completionsubmit: int
    cutoffdate: Timestamp
    gradingduedate: Timestamp
    teamsubmission: bool
    requireallteammemberssubmit: bool
    teamsubmissiongroupingid: int
    blindmarking: bool
    hidegrader: bool
    revealidentities: bool
    attemptreopenmethod: str
    maxattempts: int
    markingworkflow: bool
    markingallocation: bool
    markinganonymous: bool
    requiresubmissionstatement: bool
    preventsubmissionnotingroup: Optional[bool]
    submissionstatement: Optional[str]
    submissionstatementformat: Optional[FormatEnum]
    intro: Optional[str]
    introformat: Optional[FormatEnum]
    introfiles: Optional[list[File]]
    introattachments: Optional[list[File]]
    activity: Optional[str]
    activityformat: Optional[FormatEnum]
    activityattachments: Optional[list[File]]
    timelimit: Optional[int]
    submissionattachments: Optional[bool]


class RAssignmentsPerCourse(BaseModel):
    id: int
    fullname: str
    shortname: str
    timemodified: Timestamp
    assignments: list[RAssignment]


class RAssignments(BaseModel):
    courses: list[RAssignmentsPerCourse]
    warnings: list[RWarning]


class RSubmissionFileArea(BaseModel):
    area: str
    files: Optional[list[File]]


class RSubmissionEditorField(BaseModel):
    name: str
    description: str
    text: str
    format: FormatEnum


class RSubmissionPlugin(BaseModel):
    type: str
    name: str
    fileareas: Optional[list[RSubmissionFileArea]]
    editorfields: Optional[list[RSubmissionEditorField]]


class RSubmission(BaseModel):
    id: PositiveInt
    userid: PositiveInt
    attemptnumber: int
    timecreated: Timestamp
    timemodified: Timestamp
    timestarted: Optional[Timestamp]
    status: SubmissionStatus
    groupid: int
    assignment: Optional[PositiveInt]
    latest: Optional[int]
    plugins: Optional[list[RSubmissionPlugin]]
    gradingstatus: Optional[GradingStatus]


class RAssignmentMention(BaseModel):
    assignmentid: PositiveInt
    submissions: list[RSubmission]


class RSubmissions(BaseModel):
    assignments: list[RAssignmentMention]
    warnings: list[RWarning]


class RAssignmentGrade(BaseModel):
    id: PositiveInt
    userid: PositiveInt
    attemptnumber: int
    timecreated: Timestamp
    timemodified: Timestamp
    grader: PositiveInt
    grade: str


class RAssignmentGradeset(BaseModel):
    assignmentid: PositiveInt
    grades: list[RAssignmentGrade]


class RAssignmentsGrades(BaseModel):
    assignments: list[RAssignmentGradeset]
    warnings: list[RWarning]


class AssignMixin:
    async def mod_assign_get_assignments(
            self: WebServiceAdapter,
            courseids: Collection[int] = (),
            capabilities: Collection[str] = (),
            includenotenrolledcourses: bool = False
    ) -> RAssignments:
        return await self(
            'mod_assign_get_assignments', dict(
                courseids=courseids, capabilities=capabilities,
                includenotenrolledcourses=includenotenrolledcourses
            ), model=RAssignments
        )

    async def mod_assign_get_submissions(
            self: WebServiceAdapter,
            assignmentids: Collection[int],
            status: str = '',
            since: datetime | int = 0, before: datetime | int = 0
    ) -> RSubmissions:
        return await self(
            'mod_assign_get_submissions', dict(
                assignmentids=assignmentids, status=status, since=since, before=before
            ), model=RSubmissions
        )

    async def mod_assign_get_grades(
            self: WebServiceAdapter,
            assignmentids: Collection[int],
            since: datetime | int = 0
    ) -> RAssignmentsGrades:
        return await self(
            'mod_assign_get_grades', dict(
                assignmentids=assignmentids, since=since
            ), model=RAssignmentsGrades
        )
