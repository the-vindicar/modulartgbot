import typing as t
import dataclasses


__all__ = [
    'TimetableMonitorConfig',
    'Lesson', 'TimetableSlot', 'Timetable',
    'TimetableSlotChange'
]


@dataclasses.dataclass
class TimetableMonitorConfig:
    update_time_utc: str = "19:00:00"
    telegram_delay: float = 1
    teachers: dict[str, str] = dataclasses.field(default_factory=dict)
    rooms: list[str] = dataclasses.field(default_factory=list)
    course_shortnames: dict[str, t.Optional[str]] = dataclasses.field(default_factory=dict)

    def __post_init__(self):
        self.course_shortnames = self.course_shortnames or {}
        self.teachers = self.teachers or {}
        self.rooms = self.rooms or []


@dataclasses.dataclass(slots=True, eq=True)
class Lesson:
    room: str
    teacher: str
    course: str
    type: str
    groups: str


@dataclasses.dataclass(slots=True, eq=True)
class TimetableSlot:
    above: t.Optional[Lesson] = None
    below: t.Optional[Lesson] = None
    both: t.Optional[Lesson] = None

    def replace_course_names(self, renamings: dict[str, t.Optional[str]]) -> 'TimetableSlot':
        x = {}
        for p in ('above', 'below', 'both'):
            part: Lesson = getattr(self, p)
            if part is None:
                x[p] = None
            else:
                x[p] = dataclasses.replace(part, course=renamings.get(part.course, None) or part.course)
        return TimetableSlot(**x)


@dataclasses.dataclass(slots=True)
class TimetableSlotChange:
    week: str
    day: str
    period: int
    old: t.Optional[Lesson]
    new: t.Optional[Lesson]


@dataclasses.dataclass()
class Timetable:
    DAYS: t.ClassVar[list[str]] = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
    PERIODS: t.ClassVar[list[str]] = [
        '8:30-10:00', '10:10-11:40', '11:50-13:20', '14:00-15:30', '15:40-17:10', '17:20-18:50', '19:00-20:30'
    ]
    SUBGROUPS: t.ClassVar[dict[str, str]] = {
        ', п/г 1': 'а',
        ', п/г 2': 'б'
    }

    slots: list[list[TimetableSlot]] = dataclasses.field(default_factory=lambda: [
        [TimetableSlot() for _ in Timetable.PERIODS] for _ in Timetable.DAYS
    ])

    def iterate(self) -> t.Iterable[tuple[int, int, int, Lesson]]:
        for day, periods in enumerate(self.slots):
            for period, slot in enumerate(periods):
                if slot.above:
                    yield day, period, 1, slot.above
                if slot.below:
                    yield day, period, 2, slot.below
                if slot.both:
                    yield day, period, 0, slot.both

    def get_all_courses(self) -> set[str]:
        courses = set()
        for lessons in self.slots:
            for slot in lessons:
                if slot.above:
                    courses.add(slot.above.course)
                if slot.below:
                    courses.add(slot.below.course)
                if slot.both:
                    courses.add(slot.both.course)
        return courses

    def changes_from(self, old: 'Timetable') -> list[TimetableSlotChange]:
        changes = []
        WEEKS: list[str] = ['над чертой', 'под чертой', 'обе недели']
        for day, daydata in enumerate(self.slots):
            for period, slot in enumerate(daydata):
                old_slot = old.slots[day][period]
                new_slot = self.slots[day][period]
                for i, part in enumerate(('above', 'below', 'both')):
                    old_part = getattr(old_slot, part)
                    new_part = getattr(new_slot, part)
                    if old_part != new_part:
                        changes.append(TimetableSlotChange(
                            week=WEEKS[i],
                            day=Timetable.DAYS[day],
                            period=period,
                            old=old_part,
                            new=new_part
                        ))
        return changes

    @staticmethod
    def fix_groups(groups: str) -> str:
        splits: list[tuple[str, ...]] = [tuple(g.rsplit('-', 1)) for g in groups.split(', ')]
        splits.sort(key=lambda item: item[0])
        result = ''
        last_prefix = None
        for prefix, number in splits:
            if prefix != last_prefix:
                if last_prefix is not None:
                    result += ', '
                result += f'{prefix}-{number}'
                last_prefix = prefix
            else:
                result += f',{number}'
        return result
