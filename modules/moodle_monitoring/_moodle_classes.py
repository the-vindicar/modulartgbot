import typing as t
import dataclasses
import datetime


__all__ = [
    'User', 'Course', 'Participant', 'Role', 'Group',
    'Assignment', 'Submission', 'SubmittedFile'
]


class _IDMixin:
    id: int

    def __hash__(self) -> int:
        return self.id

    def __eq__(self, other) -> bool:
        return self.id == other.id

    def __ne__(self, other) -> bool:
        return self.id == other.id


@dataclasses.dataclass(frozen=True, init=True)
class User(_IDMixin):
    id: int
    name: str
    email: t.Optional[str] = None


@dataclasses.dataclass(frozen=True, init=True)
class Role(_IDMixin):
    id: int
    name: str


@dataclasses.dataclass(frozen=True, init=True)
class Group(_IDMixin):
    id: int
    name: str


@dataclasses.dataclass(frozen=True, init=True)
class Participant:
    user: User
    roles: tuple[Role, ...]
    groups: tuple[Group, ...]

    def __eq__(self, other: 'Participant') -> bool:
        return self.user == other.user

    def __neq__(self, other: 'Participant') -> bool:
        return self.user != other.user

    def __hash__(self) -> int:
        return self.user.id


@dataclasses.dataclass(frozen=True, init=True)
class Course(_IDMixin):
    """Описывает один курс в Moodle."""
    id: int
    shotname: str
    fullname: str
    students: tuple[Participant, ...]
    teachers: tuple[Participant, ...]
    starts: t.Optional[datetime.datetime] = None
    ends: t.Optional[datetime.datetime] = None


@dataclasses.dataclass(frozen=True, init=True)
class Assignment(_IDMixin):
    """Описывает задание в Moodle."""
    id: int
    course_id: int
    name: str
    opening: t.Optional[datetime.datetime]
    closing: t.Optional[datetime.datetime]
    cutoff: t.Optional[datetime.datetime]


@dataclasses.dataclass(frozen=True, init=True)
class SubmittedFile:
    """Описывает файл, прикреплённый к ответу на задание в Moodle."""
    submission_id: int
    assignment_id: int
    user_id: int
    filename: str
    mimetype: str
    size: int
    url: str
    uploaded: datetime.datetime

    def __eq__(self, other: 'SubmittedFile') -> bool:
        return self.submission_id == other.submission_id and self.filename == other.filename

    def __ne__(self, other: 'SubmittedFile') -> bool:
        return self.submission_id != other.submission_id or self.filename != other.filename

    def __hash__(self) -> int:
        return hash((self.submission_id, self.filename))


@dataclasses.dataclass(frozen=True, init=True)
class Submission(_IDMixin):
    """Описывает ответ на задание в Moodle."""
    id: int
    assignment_id: int
    user_id: int
    updated: datetime.datetime
    files: tuple[SubmittedFile, ...]
