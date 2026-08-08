"""This submodule deals with course module availability. It is exposed as a part of courses submodule."""
from typing import Optional, Any, Union, Literal, Annotated, Self
from datetime import datetime
from enum import IntEnum, StrEnum
from pydantic import BaseModel, Field, ConfigDict
from .common import *


__all__ = [
    'CompletionState',
    'FieldOperators',
    'StandardProfileFields',
    'AvConditionCompletion',
    'AvConditionDate',
    'AvConditionGrade',
    'AvConditionGroup',
    'AvConditionGrouping',
    'AvConditionProfile',
    'AvConditionUnknown',
    'AvailabilityCondition',
    'AvOperator',
]


class AvConditionBase(BaseModel):
    model_config = ConfigDict(extra='allow')

    def __invert__(self) -> 'AvOperator':
        return AvOperator(op='!&', c=[self], showc=[True])

    def __and__(self, other: Union['AvConditionBase', 'AvOperator']) -> 'AvOperator':
        if isinstance(other, AvOperator) and other.op == '&':
            return AvOperator(op=other.op, c=[self]+other.c, showc=[True]+other.showc)
        else:
            return AvOperator(op='&', c=[self, other], showc=[True, True])

    def __or__(self, other: Union['AvConditionBase', 'AvOperator']) -> 'AvOperator':
        if isinstance(other, AvOperator) and other.op == '|':
            return AvOperator(op=other.op, c=[self]+other.c, showc=[True]+other.showc)
        else:
            return AvOperator(op='|', c=[self, other], showc=[True, True])

    def __iand__(self, other: Union['AvConditionBase', 'AvOperator']) -> 'AvOperator':
        if isinstance(other, AvOperator) and other.op == '&':
            return AvOperator(op=other.op, c=other.c+[self], showc=other.showc+[True])
        else:
            return AvOperator(op='&', c=[other, self], showc=[True, True])

    def __ior__(self, other: Union['AvConditionBase', 'AvOperator']) -> 'AvOperator':
        if isinstance(other, AvOperator) and other.op == '|':
            return AvOperator(op=other.op, c=other.c+[self], showc=other.showc+[True])
        else:
            return AvOperator(op='|', c=[other, self], showc=[True, True])


class AvConditionDate(AvConditionBase):
    type: Literal['date']
    d: Literal['>=', '<']
    t: Timestamp

    def __str__(self):
        return f'(date {self.d} {datetime.fromtimestamp(self.t).isoformat()})'


class CompletionState(IntEnum):
    """Describes module completion state."""
    INCOMPLETE = 0
    COMPLETE = 1
    PASS = 2
    FAIL = 3


class AvConditionCompletion(AvConditionBase):
    type: Literal['completion']
    cm: Union[MoodleID | Literal[-1]]
    e: CompletionState

    def __str__(self):
        return f'({self.cm} == {self.e.name})'


class AvConditionGrade(AvConditionBase):
    type: Literal['grade']
    id: MoodleID
    min: float | None = None
    max: float | None = None

    def __str__(self):
        less = f'{self.min} <= ' if self.min is not None else ''
        more = f' < {self.max}' if self.max is not None else ''
        return f'({less}grade for #{self.id}{more})' if less or more else f'(has a grade for #{self.id})'


class AvConditionGroup(AvConditionBase):
    type: Literal['group']
    id: OptionalMoodleID = 0

    def __str__(self):
        return f'(in group #{self.id})' if self.id > 0 else '(in any group)'


class AvConditionGrouping(AvConditionBase):
    type: Literal['grouping']
    id: OptionalMoodleID = 0
    activity: bool = False

    def __str__(self):
        return f'(in grouping #{self.id})' if not self.activity else "(in activity's grouping)"


class StandardProfileFields(StrEnum):
    """User profile field names that are available by default"""
    FIRSTNAME = 'firstname'
    LASTNAME = 'lastname'
    EMAIL = 'email'
    CITY = 'city'
    COUNTRY = 'country'
    IDNUMBER = 'idnumber'
    INSTITUTION = 'institution'
    DEPARTMENT = 'department'
    PHONE1 = 'phone1'
    PHONE2 = 'phone2'
    ADDRESS = 'address'


class FieldOperators(StrEnum):
    """Profile field check operators"""
    CONTAINS = 'contains'
    DOESNOTCONTAIN = 'doesnotcontain'
    ISEQUALTO = 'isequalto'
    STARTSWITH = 'startswith'
    ENDSWITH = 'endswith'
    ISEMPTY = 'isempty'
    ISNOTEMPTY = 'isnotempty'


class AvConditionProfile(AvConditionBase):
    type: Literal['profile']
    sf: Union[StandardProfileFields, str]
    op: Union[FieldOperators, str]
    v: Optional[str] = None

    def __str__(self):
        value = '' if self.op in (FieldOperators.ISEMPTY, FieldOperators.ISNOTEMPTY) else f' {self.v!r}'
        return f'({self.sf!s} {self.op!s}{value})'


class AvConditionUnknown(AvConditionBase):
    model_config = ConfigDict(extra='allow')
    type: str
    __pydantic_extra__: dict[str, Any]

    @property
    def parameters(self) -> dict[str, Any]:
        """Parameters for an unknown availability condition."""
        return self.__pydantic_extra__

    def __str__(self):
        params = ', '.join(f'{n}={v!r}' for n, v in self.__pydantic_extra__)
        return f'({self.type: {params}})'


AvailabilityCondition = Annotated[
    Union[
        AvConditionDate,
        AvConditionCompletion,
        AvConditionGrade,
        AvConditionGroup,
        AvConditionGrouping,
        AvConditionProfile,
        AvConditionUnknown,
    ],
    Field(union_mode="left_to_right"),
]


class AvOperator(BaseModel):
    op: Literal['&', '!&', '|', '!|']
    c: list[Union['AvailabilityCondition', 'AvOperator']]
    showc: list[bool]

    def __str__(self):
        prefix, op = (self.op[0], self.op[1:]) if self.op.startswith('!') else ('', self.op)
        if len(self.c) > 1:
            values = f' {op} '.join(str(c) for c in self.c)
            return f'{prefix}({values})'
        else:
            return f'{prefix}{self.c[0]!s}'

    def __invert__(self) -> Self:
        newop = f'!{self.op}' if self.op in ('&', '|') else self.op[1:]
        return AvOperator(op=newop, c=list(self.c), showc=list(self.showc))

    def __and__(self, other: Union['AvConditionBase', 'AvOperator']) -> 'AvOperator':
        if isinstance(other, AvOperator) and other.op == '&' and self.op == '&':
            return AvOperator(op=other.op, c=self.c+other.c, showc=self.showc+other.showc)
        else:
            return AvOperator(op='&', c=[self, other], showc=[True, True])

    def __or__(self, other: Union['AvConditionBase', 'AvOperator']) -> 'AvOperator':
        if isinstance(other, AvOperator) and other.op == '|' and self.op == '|':
            return AvOperator(op=other.op, c=self.c+other.c, showc=self.showc+other.showc)
        else:
            return AvOperator(op='|', c=[self, other], showc=[True, True])

    def __iand__(self, other: Union['AvConditionBase', 'AvOperator']) -> 'AvOperator':
        if isinstance(other, AvOperator) and other.op == '&' and self.op == '&':
            return AvOperator(op=other.op, c=other.c+self.c, showc=other.showc+self.showc)
        else:
            return AvOperator(op='&', c=[other, self], showc=[True, True])

    def __ior__(self, other: Union['AvConditionBase', 'AvOperator']) -> 'AvOperator':
        if isinstance(other, AvOperator) and other.op == '|' and self.op == '|':
            return AvOperator(op=other.op, c=other.c+self.c, showc=other.showc+self.showc)
        else:
            return AvOperator(op='|', c=[other, self], showc=[True, True])
