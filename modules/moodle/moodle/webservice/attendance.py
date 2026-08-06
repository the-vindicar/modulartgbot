"""
This submodule works with mod_attendance.

https://marketplace.moodle.com/plugins/mod_attendance
https://github.com/danmarsden/moodle-mod_attendance
"""

from typing import Optional, Any, Collection, Union
from datetime import datetime, timedelta

from pydantic import BaseModel

from .common import *


__all__ = [
    'AttendanceMixin',
    'RSession', 'RStatus', 'RSessionStudent', 'RExtendedSession',
    'RCreatedSession', 'RAttendanceInstance', 'RAttendanceCourse', 'RAttendanceLogItem'
]


class RSession(BaseModel):
    """Describes an attendance session."""
    id: MoodleID
    attendanceid: MoodleID
    groupid: OptionalMoodleID
    sessdate: Timestamp
    duration: timedelta
    lasttaken: Timestamp
    lasttakenby: OptionalMoodleID
    timemodified: Timestamp
    description: str
    descriptionformat: FormatEnum
    studentscanmark: bool
    absenteereport: bool
    autoassignstatus: int
    preventsharedip: bool
    preventsharediptime: timedelta
    statusset: int
    includeqrcode: bool
    studentsearlyopentime: timedelta


class RStatus(BaseModel):
    """Describes one of the statuses a student can have for a session."""
    id: MoodleID
    attendanceid: MoodleID
    acronym: str
    description: str
    grade: float
    visible: bool
    deleted: bool
    setnumber: int


class RSessionStudent(BaseModel):
    """Mention of a student who has taken a session."""
    id: MoodleID
    firstname: str
    lastname: str


class RAttendanceLogItem(BaseModel):
    """A single attendance log mark linking the student, the session and the status."""
    studentid: MoodleID
    statusid: str
    remarks: str
    id: str


class RExtendedSession(RSession):
    """Extended attendance session information."""
    courseid: MoodleID
    statuses: list[RStatus]
    users: list[RSessionStudent]
    attendance_log: list[RAttendanceLogItem]


class RCreatedSession:
    """Response to session creation."""
    sessionid: MoodleID


class RAttendanceInstance(BaseModel):
    """Instance of attendance module."""
    name: str
    today_sessions: list[RSession]


class RAttendanceCourse(BaseModel):
    """A course that has an attendance module."""
    shortname: str
    fullname: str
    attendance_instances: list[RAttendanceInstance]


class AttendanceMixin(WebServiceFunctions):
    """Mixin that works with attendance module webservices."""
    async def add_session(
            self,
            attendanceid: MoodleID,
            description: str,
            sessiontime: Union[datetime, Timestamp],
            duration: Union[timedelta, int],  # in seconds
            groupid: int = 0,
            addcalendarevent: bool = True
    ) -> RCreatedSession:
        """Adds a new session to the given attendance instance, and returns session's ID."""
        return await self._owner('mod_attendance_add_session', dict(
            attendanceid=attendanceid, description=description,
            sessiontime=sessiontime, duration=duration,
            groupid=groupid, addcalendarevent=addcalendarevent
        ), model=RCreatedSession)

    async def remove_session(
            self,
            sessionid: MoodleID
    ) -> bool:
        """Deletes the session with the given ID, returning True on success.
        The actual implementation seems to always return True, though..."""
        return await self._owner('mod_attendance_remove_session', dict(sessionid=sessionid), model=bool)

    async def get_session(
            self,
            sessionid: MoodleID
    ) -> RExtendedSession:
        """Retrieves session information by ID."""
        return await self._owner('mod_attendance_get_session', dict(sessionid=sessionid), model=RExtendedSession)

    async def get_sessions(
            self,
            attendanceid: MoodleID
    ) -> list[RExtendedSession]:
        """Retrieves all sessions in the given attendance instance."""
        return await self._owner('mod_attendance_get_sessions', dict(attendanceid=attendanceid),
                                 model=list[RExtendedSession])

    async def get_courses_with_today_sessions(
            self,
            userid: OptionalMoodleID = 0
    ) -> list[RAttendanceCourse]:
        """Returns a list of courses and corresponding attendance instances for the given user,
        but only those that have at least one session scheduled today."""
        return await self._owner('get_courses_with_today_sessions', dict(userid=userid),
                                 model=list[RAttendanceCourse])
