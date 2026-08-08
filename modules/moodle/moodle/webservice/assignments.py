"""This submodule deals with retrieving assignments and submissions to them."""
from typing import Optional, Collection, Literal, Union
from enum import StrEnum
from datetime import datetime, timedelta
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
    'ROverrides', 'ROverride', 'ROverrideIDs', 'Override'
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
    id: MoodleID
    cmid: MoodleID
    course: MoodleID
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
    teamsubmissiongroupingid: OptionalMoodleID
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
    id: MoodleID
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
    id: MoodleID
    userid: MoodleID
    attemptnumber: int
    timecreated: Timestamp
    timemodified: Timestamp
    timestarted: Optional[Timestamp]
    status: SubmissionStatus
    groupid: OptionalMoodleID
    assignment: Optional[OptionalMoodleID] = None
    latest: Optional[int] = None
    plugins: list[RSubmissionPlugin] = Field(default_factory=list)
    gradingstatus: Optional[GradingStatus] = None


class RAssignmentMention(BaseModel):
    assignmentid: MoodleID
    submissions: list[RSubmission]


class RSubmissions(BaseModel):
    assignments: list[RAssignmentMention]
    warnings: list[RWarning]


class RAssignmentGrade(BaseModel):
    id: MoodleID
    userid: MoodleID
    attemptnumber: int
    timecreated: Timestamp
    timemodified: Timestamp
    grader: MoodleID
    grade: str
    gradefordisplay: Optional[str] = None


class RAssignmentGradeset(BaseModel):
    assignmentid: MoodleID
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
    usergroups: list[MoodleID]
    timelimit: Optional[Timestamp] = None
    submissiongroup: Optional[OptionalMoodleID] = None
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


class Override(BaseModel):
    """Describes a newly created or updated time override for an assignment."""
    id: Optional[MoodleID]
    groupid: Optional[MoodleID] = None
    userid: Optional[MoodleID] = None
    allowsubmissionsfromdate: Union[datetime, int, None] = None
    duedate: Union[datetime, int, None] = None
    cutoffdate: Union[datetime, int, None] = None
    timelimit: Union[timedelta, int, None] = None
    reason: Optional[str] = None
    reasonformat: Optional[FormatEnum] = FormatEnum.FORMAT_MOODLE


class ROverride(BaseModel):
    """A time override (start/due/cutoff) for an assignment."""
    id: MoodleID
    assignid: MoodleID
    userid: Optional[OptionalMoodleID] = None
    groupid: Optional[OptionalMoodleID] = None
    sortorder: Optional[int] = None
    allowsubmissionsfromdate: Optional[Timestamp] = None
    duedate: Optional[Timestamp] = None
    cutoffdate: Optional[Timestamp] = None
    timelimit: Optional[timedelta] = None
    reason: Optional[str] = None
    reasonformat: FormatEnum = FormatEnum.FORMAT_MOODLE


class ROverrideIDs(BaseModel):
    """List of IDs for created/updated/deleted overrides."""
    ids: list[int]


class ROverrides(BaseModel):
    """List of start/due/cutoff time overrides for an assignment."""
    overrides: list[ROverride]


class AssignMixin (WebServiceFunctions):
    """Mixin providing methods for working with users."""
    async def get_assignments(
            self,
            courseids: Collection[MoodleID] = (),
            capabilities: Collection[str] = (),
            includenotenrolledcourses: bool = False
    ) -> RAssignments:
        """Retrieves all assignments from the specified courses.
        :param courseids: IDs of the courses we want to get assignments from.
        :param capabilities: Only retrieve assignments, for which we have specified capabilities.
        :param includenotenrolledcourses: If False, any courses we are not enrolled in will be dropped from the list.
        :returns: List of assignments, grouped by course."""
        return await self._owner(
            'mod_assign_get_assignments', dict(
                courseids=courseids, capabilities=capabilities,
                includenotenrolledcourses=includenotenrolledcourses
            ), model=RAssignments
        )

    async def get_submissions(
            self,
            assignmentids: Collection[MoodleID],
            status: str = '',
            since: Union[datetime, int] = 0, before: Union[datetime, int] = 0
    ) -> RSubmissions:
        """Retrieves submissions for the specified assignments.
        :param assignmentids: IDs of the assignments we want to retrieve submissions for.
        :param status: If not empty, only retrieve submissions with this status.
        :param since: If not 0, only retrieve submissions sent at or after the specified timestamp.
        :param before: If not 0, only retrieve submissions sent at or before the specified timestamp.
        :returns: List of submissions, grouped by assignment."""
        return await self._owner(
            'mod_assign_get_submissions', dict(
                assignmentids=assignmentids, status=status, since=since, before=before
            ), model=RSubmissions
        )

    async def get_grades(
            self: WebServiceAdapter,
            assignmentids: Collection[MoodleID],
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

    async def get_submission_status(
            self,
            assignid: MoodleID,
            userid: OptionalMoodleID = 0,
            groupid: Union[int, Literal['']] = 0
    ) -> RSubmissionStatus:
        """Retrieves a single submission's status for the given assignment.
        :param assignid: ID of the assignment.
        :param userid: User that had sent/could have sent the submission.
        :param groupid: Group that had sent/could have sent the submission, in case of group submission being enabled.
        :returns: Submisison status information."""
        return await self._owner(
            'mod_assign_get_submission_status', dict(
                assignid=assignid, userid=userid, groupid=groupid
            ), model=RSubmissionStatus
        )

    async def get_overrides(
            self,
            assignid: MoodleID
    ) -> ROverrides:
        """Retrieves time overrides for the given assignment.
        :param assignid: ID of the assignment to retrieve the overrides for."""
        return await self._owner(
            'mod_assign_get_overrides', dict(
                assignid=assignid,
            ), model=ROverrides
        )

    async def save_overrides(
            self,
            assignid: MoodleID,
            overrides: Collection[Override],
            recalculatepenalties: bool = False
    ) -> ROverrideIDs:
        """
        Updates or adds assignment time overrides.
        :param assignid: Assignment ID for which overrides are updated.
        :param overrides: Collection of override descriptions. If id field is None, a new override will be added,
            otherwise an existing override will be updated.
        :param recalculatepenalties: If True, penalties for late students will be recalculated according to
            the new overrides.
        :return:
        """
        return await self._owner(
            'mod_assign_save_overrides', dict(
                data=dict(
                    assignid=assignid,
                    overrides=list(overrides),
                    recalculatepenalties=recalculatepenalties
                ),
            ), model=ROverrideIDs
        )

    async def delete_overrides(
            self,
            assignid: MoodleID,
            ids: Collection[MoodleID],
            recalculatepenalties: bool = False
    ) -> ROverrideIDs:
        """
        Deletes assignment time overrides with the given IDs.
        :param assignid: Assignment ID for which overrides are updated.
        :param ids: Collection of override IDs.
        :param recalculatepenalties: If True, penalties for late students will be recalculated according to
            the remaining overrides.
        :return:
        """
        return await self._owner(
            'mod_assign_save_overrides', dict(
                data=dict(
                    assignid=assignid,
                    ids=list(ids),
                    recalculatepenalties=recalculatepenalties
                ),
            ), model=ROverrideIDs
        )
