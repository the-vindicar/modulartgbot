"""Содержит датаклассы, описывающие расписание занятий, а также вспомогательные датаклассы."""
import typing as t
import dataclasses


__all__ = [
    'TimetableMonitorConfig',
    'Lesson', 'TimetableSlot', 'Timetable',
    'TimetableSlotChange'
]


@dataclasses.dataclass
class TimetableMonitorConfig:
    """Конфигурация модуля мониторинга расписания."""
    update_time_utc: str = "15:00:00"
    telegram_delay: float = 1
    website_delay: float = 5
    teachers: dict[str, t.Any] = dataclasses.field(default_factory=dict)
    rooms: list[str] = dataclasses.field(default_factory=list)
    course_shortnames: dict[str, t.Optional[str]] = dataclasses.field(default_factory=dict)

    def __post_init__(self):
        self.course_shortnames = self.course_shortnames or {}
        self.teachers = self.teachers or {}
        self.rooms = self.rooms or []


@dataclasses.dataclass(slots=True, eq=True)
class Lesson:
    """Одно занятие (пара)."""
    room: str
    teacher: str
    course: str
    type: str
    groups: str


@dataclasses.dataclass(slots=True, eq=True)
class TimetableSlot:
    """Слот в расписании. Может содержать разные занятия для чётной и нечётной недель."""
    above: t.Optional[Lesson] = None
    below: t.Optional[Lesson] = None
    both: t.Optional[Lesson] = None

    def replace_course_names(self, renamings: dict[str, t.Optional[str]]) -> 'TimetableSlot':
        """Переименовывает названия дисциплин для занятий в слоте, и возвращает новый слот.
        :param renamings: Набор пар "старое название - новое название"."""
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
    """Описание одного изменения в расписании занятий."""
    week: str
    day: str
    period: int
    old: t.Optional[Lesson]
    new: t.Optional[Lesson]


@dataclasses.dataclass()
class Timetable:
    """Расписание занятий."""
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
        """Перебирает все занятия в расписании, сообщая день, номер пары, неделю и сведения о занятии."""
        for day, periods in enumerate(self.slots):
            for period, slot in enumerate(periods):
                if slot.above:
                    yield day, period, 1, slot.above
                if slot.below:
                    yield day, period, 2, slot.below
                if slot.both:
                    yield day, period, 0, slot.both

    def get_all_courses(self) -> set[str]:
        """Возвращает множество названий курсов в расписании."""
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
        """Сравнивает это расписание с указанным, и возвращает список изменений.
        :param old: Предыдущая версия расписания.
        :returns: Список изменений. Пуст, если оба расписания совпадают."""
        changes = []
        WEEKS: list[str] = ['обе недели', 'над чертой', 'под чертой']
        for day, daydata in enumerate(self.slots):
            for period, slot in enumerate(daydata):
                old_slot = old.slots[day][period]
                new_slot = self.slots[day][period]
                for i, part in enumerate(('both', 'above', 'below')):
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
        """Преобразует строку с перечислением групп.
        :param groups: Строка вида "21-ИСбо-1, 21-ИСбо-2, 21-ИСбо-4, 21-ИИбо-1".
        :returns: Строка вида "21-ИСбо-1,2,4; 21-ИИбо-1".
        """
        splits: list[tuple[str, str, str]] = [g.rpartition('-') for g in groups.split(', ')]
        splits.sort(key=lambda item: item[0])
        result = ''
        last_prefix = None
        for prefix, _, number in splits:
            if prefix != last_prefix:
                if last_prefix is not None:
                    result += '; '
                result += f'{prefix}-{number}'
                last_prefix = prefix
            else:
                result += f',{number}'
        return result
