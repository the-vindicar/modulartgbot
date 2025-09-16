"""This submodule deals with retrieving assignments and submissions to them."""
from typing import Optional, Collection, Literal, Union
from enum import StrEnum
from datetime import datetime
from pydantic import BaseModel, PositiveInt, Field
from .common import *


__all__ = [
    'AssignMixin',
    'RAssignment', 'RAssignmentsPerCourse', 'RAssignments',
    'RAssignmentGradeset', 'RAssignmentsGrades', 'RAssignmentGrade',
    'RSubmissions', 'RSubmission', 'RAssignmentMention',
    'RSubmissionPlugin', 'RSubmissionEditorField', 'RSubmissionFileArea',
    'UngroupedWarning', 'RSubmissionStatus', 'RSubmissionStatusGradingSummary', 'RSubmissionStatusFeedback',
    'RSubmissionStatusLastAttempt', 'RSubmissionStatusAssignData', 'RSubmissionStatusAssignDataAttachments',
]


class SubmissionStatus(StrEnum):
    """Possible assignment submission status values."""
    NEW = 'new'
    DRAFT = 'draft'
    SUBMITTED = 'submitted'
    REOPENED = 'reopened'


class GradingStatus(StrEnum):
    """Possible grading status values."""
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
    grade: Optional[int] = None
    gradepenalty: Optional[int] = None
    markingworkflow: Optional[bool] = None
    markingallocation: Optional[bool] = None
    markinganonymous: Optional[bool] = None
    requiresubmissionstatement: Optional[bool] = None
    preventsubmissionnotingroup: Optional[bool] = None
    submissionstatement: Optional[str] = None
    submissionstatementformat: Optional[FormatEnum] = None
    intro: Optional[str] = None
    introformat: Optional[FormatEnum] = None
    introfiles: list[File] = Field(default_factory=list)
    introattachments: list[File] = Field(default_factory=list)
    activity: Optional[str] = None
    activityformat: Optional[FormatEnum] = None
    activityattachments: list[File] = Field(default_factory=list)
    timelimit: Optional[int] = None
    submissionattachments: Optional[bool] = None


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
    files: list[File] = Field(default_factory=list)


class RSubmissionEditorField(BaseModel):
    name: str
    description: str
    text: str
    format: FormatEnum


class RSubmissionPlugin(BaseModel):
    type: str
    name: str
    fileareas: list[RSubmissionFileArea] = Field(default_factory=list)
    editorfields: list[RSubmissionEditorField] = Field(default_factory=list)


class RSubmission(BaseModel):
    id: PositiveInt
    userid: PositiveInt
    attemptnumber: int
    timecreated: Timestamp
    timemodified: Timestamp
    timestarted: Optional[Timestamp]
    status: SubmissionStatus
    groupid: int
    assignment: Optional[PositiveInt] = None
    latest: Optional[int] = None
    plugins: list[RSubmissionPlugin] = Field(default_factory=list)
    gradingstatus: Optional[GradingStatus] = None


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
    gradefordisplay: Optional[str] = None


class RAssignmentGradeset(BaseModel):
    assignmentid: PositiveInt
    grades: list[RAssignmentGrade]


class RAssignmentsGrades(BaseModel):
    assignments: list[RAssignmentGradeset]
    warnings: list[RWarning]


class UngroupedWarning(StrEnum):
    """How should we treat the situation where some users are not in groups?"""
    REQUIRED = 'warningrequired'
    OPTIONAL = 'warningoptional'
    NONE = ''


class RSubmissionStatusGradingSummary(BaseModel):
    participantcount: int
    submissiondraftscount: int
    submissionsenabled: bool
    submissionssubmittedcount: int
    submissionsneedgradingcount: int
    warnofungroupedusers: UngroupedWarning


class RSubmissionStatusLastAttempt(BaseModel):
    submissionsenabled: bool
    locked: bool
    graded: bool
    canedit: bool
    caneditowner: bool
    cansubmit: bool
    extensionduedate: Timestamp
    blindmarking: bool
    gradingstatus: GradingStatus
    usergroups: list[PositiveInt]
    timelimit: Optional[Timestamp] = None
    submissiongroup: Optional[int] = None
    submission: Optional[RSubmission] = None
    teamsubmission: Optional[RSubmission] = None
    submissiongroupmemberswhoneedtosubmit: list[PositiveInt] = Field(default_factory=list)


class RSubmissionStatusFeedback(BaseModel):
    grade: Optional[RAssignmentGrade]
    gradefordisplay: str
    gradeddate: Timestamp
    plugins: list[RSubmissionPlugin]


class RSubmissionStatusAssignDataAttachments(BaseModel):
    intro: list[File] = Field(default_factory=list)
    activity: list[File] = Field(default_factory=list)


class RSubmissionStatusAssignData(BaseModel):
    attachments: Optional[RSubmissionStatusAssignDataAttachments] = None
    activity: Optional[str] = None
    activityformat: Optional[FormatEnum] = None


class RSubmissionStatus(BaseModel):
    gradingsummary: RSubmissionStatusGradingSummary
    assignmentdata: RSubmissionStatusAssignData
    lastattempt: Optional[RSubmissionStatusLastAttempt] = None
    feedback: Optional[RSubmissionStatusFeedback] = None
    previousattempts: list = Field(default_factory=list)
    warnings: list[RWarning] = Field(default_factory=list)


class AssignMixin:
    """Mixin providing methods for working with users."""
    async def mod_assign_get_assignments(
            self: WebServiceAdapter,
            courseids: Collection[int] = (),
            capabilities: Collection[str] = (),
            includenotenrolledcourses: bool = False
    ) -> RAssignments:
        """Retrieves all assignments from the specified courses.
        :param courseids: IDs of the courses we want to get assignments from.
        :param capabilities: Only retrieve assignments, for which we have specified capabilities.
        :param includenotenrolledcourses: If False, any courses we are not enrolled in will be dropped from the list.
        :returns: List of assignments, grouped by course."""
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
            since: Union[datetime, int] = 0, before: Union[datetime, int] = 0
    ) -> RSubmissions:
        """Retrieves submissions for the specified assignments.
        :param assignmentids: IDs of the assignments we want to retrieve submissions for.
        :param status: If not empty, only retrieve submissions with this status.
        :param since: If not 0, only retrieve submissions sent at or after the specified timestamp.
        :param before: If not 0, only retrieve submissions sent at or before the specified timestamp.
        :returns: List of submissions, grouped by assignment."""
        return await self(
            'mod_assign_get_submissions', dict(
                assignmentids=assignmentids, status=status, since=since, before=before
            ), model=RSubmissions
        )

    async def mod_assign_get_grades(
            self: WebServiceAdapter,
            assignmentids: Collection[int],
            since: Union[datetime, int] = 0
    ) -> RAssignmentsGrades:
        """Retrieves user grades for the given assignments.
        :param assignmentids: IDs of the assignments we want to retrieve grades for.
        :param since: If not 0, only retrieve grades created at or after the specified timestamp.
        :returns: List of grades, grouped by assignment."""
        return await self(
            'mod_assign_get_grades', dict(
                assignmentids=assignmentids, since=since
            ), model=RAssignmentsGrades
        )

    async def mod_assign_get_submission_status(
            self: WebServiceAdapter,
            assignid: int,
            userid: int = 0,
            groupid: Union[int, Literal['']] = 0
    ) -> RSubmissionStatus:
        """Retrieves a single submission's status for the given assignment.
        :param assignid: ID of the assignment.
        :param userid: User that had sent/could have sent the submission.
        :param groupid: Group that had sent/could have sent the submission, in case of group submission being enabled.
        :returns: Submisison status information."""
        return await self(
            'mod_assign_get_submission_status', dict(
                assignid=assignid, userid=userid, groupid=groupid
            ), model=RSubmissionStatus
        )
