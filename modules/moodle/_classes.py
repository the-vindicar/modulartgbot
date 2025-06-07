import typing as t
import dataclasses
import datetime


__all__ = [
    'user_id', 'course_id', 'group_id', 'assignment_id', 'submission_id',
    'User', 'Course', 'Participant', 'Role', 'Group',
    'Assignment', 'Submission', 'SubmittedFile',
]

_IDType = t.TypeVar('_IDType')
user_id = t.NewType('user_id', int)
role_id = t.NewType('role_id', int)
group_id = t.NewType('group_id', int)
course_id = t.NewType('course_id', int)
assignment_id = t.NewType('assignment_id', int)
submission_id = t.NewType('submission_id', int)


class _IDMixin(t.Generic[_IDType]):
    id: _IDType

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other) -> bool:
        return self.id == other.id

    def __ne__(self, other) -> bool:
        return self.id == other.id


@dataclasses.dataclass(frozen=True, init=True)
class User(_IDMixin[user_id]):
    id: user_id
    name: str
    email: t.Optional[str] = None


@dataclasses.dataclass(frozen=True, init=True)
class Role(_IDMixin[role_id]):
    id: role_id
    name: str


@dataclasses.dataclass(frozen=True, init=True)
class Group(_IDMixin[group_id]):
    id: group_id
    name: str


@dataclasses.dataclass(frozen=True, init=True)
class Participant:
    user: User
    groups: tuple[Group, ...]

    def __eq__(self, other: 'Participant') -> bool:
        return self.user == other.user

    def __neq__(self, other: 'Participant') -> bool:
        return self.user != other.user

    def __hash__(self) -> int:
        return hash(self.user)


@dataclasses.dataclass(frozen=True, init=True)
class Course(_IDMixin[course_id]):
    """Описывает один курс в Moodle."""
    id: course_id
    shortname: str
    fullname: str
    students: tuple[Participant, ...]
    teachers: tuple[Participant, ...]
    starts: t.Optional[datetime.datetime] = None
    ends: t.Optional[datetime.datetime] = None


@dataclasses.dataclass(frozen=True, init=True)
class Assignment(_IDMixin[assignment_id]):
    """Описывает задание в Moodle."""
    id: assignment_id
    course_id: course_id
    name: str
    opening: t.Optional[datetime.datetime]
    closing: t.Optional[datetime.datetime]
    cutoff: t.Optional[datetime.datetime]


@dataclasses.dataclass(frozen=True, init=True)
class SubmittedFile:
    """Описывает файл, прикреплённый к ответу на задание в Moodle."""
    submission_id: submission_id
    filename: str
    mimetype: str
    filesize: int
    url: str
    uploaded: datetime.datetime

    def __eq__(self, other: 'SubmittedFile') -> bool:
        return self.submission_id == other.submission_id and self.filename == other.filename

    def __ne__(self, other: 'SubmittedFile') -> bool:
        return self.submission_id != other.submission_id or self.filename != other.filename

    def __hash__(self) -> int:
        return hash((self.submission_id, self.filename))


@dataclasses.dataclass(frozen=True, init=True)
class Submission(_IDMixin[submission_id]):
    """Описывает ответ на задание в Moodle."""
    id: submission_id
    assignment_id: assignment_id
    user_id: user_id
    updated: datetime.datetime
    files: tuple[SubmittedFile, ...]
