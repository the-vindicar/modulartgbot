"""Скачивает и разбирает PDF с графиком учебного процесса с сайта КГУ."""
import typing as t
import dataclasses
import datetime
import enum
import functools
import io
import os
import re
from urllib.parse import urljoin

import aiohttp
import pdfplumber


__all__ = ['TimePlanActivity', 'TimePlanParser', 'GroupPlan']
TableData = list[list[t.Optional[str]]]


class TimePlanActivity(enum.StrEnum):
    """Виды деятельности в графике обучения."""
    UNUSED = '_'
    REST_PERIOD = 'R'
    HOLIDAY = 'H'
    STUDY = 'S'
    STUDY_PRACTICE = 'P'
    INDUSTRY_PRACTICE = 'I'
    EXAM = 'X'
    GRAD_PROJECT = 'G'


@dataclasses.dataclass(frozen=True)
class GroupPlan(t.Mapping[datetime.date, TimePlanActivity]):
    """Описывает график обучения одной группы в одном учебном году."""
    specialty_code: str
    specialty_name: str
    group_code: str
    year: int
    activity: tuple[TimePlanActivity, ...]

    def get_interval(self, semester: t.Literal['autumn', 'spring'] | str, *activity: TimePlanActivity
                     ) -> tuple[datetime.date, datetime.date]:
        """Возвращает интервал дат, в который умещаются все дни с заданным типом активности.
        :param semester: Какой семестр анализируем.
        :param activity: Какие виды активности ищем.
        :returns: Кортеж вида "первый день, последний день"."""
        if semester == 'autumn':
            start_date, end_date = self.autumn_start, self.autumn_end
        else:
            start_date, end_date = self.autumn_end + datetime.timedelta(days=1), self.spring_end
        while start_date < end_date and self[start_date] not in activity:
            start_date += datetime.timedelta(days=1)
        while start_date < end_date and self[end_date] not in activity:
            end_date -= datetime.timedelta(days=1)
        return start_date, end_date

    @functools.cached_property
    def autumn_start(self) -> datetime.date:
        """Начало осеннего семестра (включительно)."""
        return datetime.date(year=self.year, month=9, day=1)

    @functools.cached_property
    def autumn_end(self) -> datetime.date:
        """Конец осеннего семестра (включительно)."""
        for i in range(1, len(self.activity)):
            if self.activity[i-1] == TimePlanActivity.REST_PERIOD and self.activity[i] != TimePlanActivity.REST_PERIOD:
                return self.autumn_start + datetime.timedelta(days=i+1)
        raise ValueError("No rest period found!")

    @functools.cached_property
    def spring_start(self) -> datetime.date:
        """Начало весеннего семестра (включительно)."""
        return self.autumn_end + datetime.timedelta(days=1)

    @functools.cached_property
    def spring_end(self) -> datetime.date:
        """Конец весеннего семестра (включительно)."""
        return datetime.date(year=self.year+1, month=8, day=31)

    def __len__(self) -> int:
        return (self.spring_end - self.autumn_start).days + 1

    def __iter__(self) -> t.Iterator[datetime.date]:
        step = datetime.timedelta(days=1)
        day = self.autumn_start
        while day <= self.spring_end:
            yield day
            day += step

    def __contains__(self, key: datetime.date) -> bool:
        return self.autumn_start <= key <= self.spring_end

    def __getitem__(self, key: datetime.date) -> TimePlanActivity:
        index = (key - self.autumn_start).days
        if 0 <= index < len(self.activity):
            return self.activity[index]
        raise KeyError(key)

    def prettify(self) -> str:
        """Генерирует "красивый" вид плана-графика в виде строки."""
        ACTIVITY_CODES: dict[TimePlanActivity, str] = {
            TimePlanActivity.STUDY: '.',
            TimePlanActivity.HOLIDAY: '*',
            TimePlanActivity.REST_PERIOD: 'К',
            TimePlanActivity.EXAM: 'Э',
            TimePlanActivity.STUDY_PRACTICE: 'У',
            TimePlanActivity.INDUSTRY_PRACTICE: 'П',
            TimePlanActivity.GRAD_PROJECT: 'Д',
            TimePlanActivity.UNUSED: '=',
        }

        start_days = []
        cells = [[] for _ in range(7)]
        end_day = self.spring_end + datetime.timedelta(days=7 - self.spring_end.weekday())
        for ri, row in enumerate(cells):
            day = self.autumn_start
            day += datetime.timedelta(days=ri - day.weekday())
            row.append(day.strftime('%a'))
            while day < end_day:
                if ri == 0:
                    start_days.append(f'{day.day:2d}')
                if self.autumn_start <= day <= self.spring_end:
                    val = ACTIVITY_CODES[self[day]]
                else:
                    val = ' '
                row.append(f'{val:>2s}')
                day += datetime.timedelta(weeks=1)
        sep = '|'
        shortdaylen = len(self.autumn_start.strftime('%a'))
        start_days.insert(0, ' '*shortdaylen)
        result = [
            sep.join(start_days),
            '-'*shortdaylen + '+--' * len(start_days),
            *(sep.join(row) for row in cells)
        ]
        return '\n'.join(result)


@dataclasses.dataclass(slots=True, frozen=True)
class _DetectedSegment:
    """Описывает область таблицы, содержащую календарный график учёбы групп одного курса одной специальности."""
    start_row: int
    start_column: int
    spec_code: str
    spec_name: str
    groups_codes: tuple[str, ...]


class TimePlanParser:
    """Реализует скачивание с сайта КГУ и разбор графиков учёбы по специальностям."""
    SPEC_CODE: t.ClassVar[re.Pattern] = re.compile(r'^\d{1,2}\.\d{1,2}\.\d{1,2}\.?$')
    GROUP_CODE: t.ClassVar[re.Pattern] = re.compile(r'\b\d{2}-\w+-\d+\b')
    PLAN_URL: t.ClassVar[re.Pattern] = re.compile(
        r'/files/op_info/graph/\d+/.+?(\d{1,2}\.\d{1,2}\.\d{1,2}\.?).+?\.pdf', re.I)
    ACTIVITY_CODES: t.ClassVar[dict[str, TimePlanActivity]] = {
        '': TimePlanActivity.STUDY,
        '*': TimePlanActivity.HOLIDAY,
        'К': TimePlanActivity.REST_PERIOD,
        'Э': TimePlanActivity.EXAM,
        'У': TimePlanActivity.STUDY_PRACTICE,
        'П': TimePlanActivity.INDUSTRY_PRACTICE,
        'Д': TimePlanActivity.GRAD_PROJECT,
        '=': TimePlanActivity.UNUSED,
    }

    def __init__(self, list_url: str):
        self._list_url = list_url

    async def acquire_plans_for(self, spec_codes: t.Collection[str]) -> t.AsyncIterable[GroupPlan]:
        """Скачивает с сайта графики обучения для указанных специальностей."""
        async with aiohttp.ClientSession(raise_for_status=True) as session:
            async with session.get(self._list_url) as list_r:
                page = await list_r.text()
            for match in self.PLAN_URL.finditer(page):
                if match.group(1) in spec_codes:
                    async with session.get(url=urljoin(self._list_url, match.group(0))) as pdf_r:
                        data = io.BytesIO(await pdf_r.content.read())
                    for plan in self.parse_pdf(data):
                        yield plan

    @classmethod
    def parse_pdf(cls, source: t.Union[str, os.PathLike, io.BufferedReader, io.BytesIO]) -> t.Iterable[GroupPlan]:
        """Анализирует PDF-файл с планом-графиком обучения, и извлекает из него планы для отдельных групп."""
        years_re = re.compile(r'(2\d{3})\s*-\s*2\d{3}', re.MULTILINE)
        with pdfplumber.open(source) as pdf:
            text = pdf.pages[0].extract_text()
            match = years_re.search(text)
            if match is None:
                raise ValueError('Failed to find year indicator')
            year = int(match.group(1))
            cells = []
            for page in pdf.pages:
                cells.extend(page.extract_table(table_settings=dict(
                    vertical_strategy='lines',
                    horizontal_strategy='lines',
                )))
        return cls._parse_cells(cells, year)

    @classmethod
    def _analyze_week(cls, raw: list[str]) -> list[TimePlanActivity]:
        """Преобразует столбец таблицы из PDF в последовательность активностей для каждого дня недели.
        Учитывает сокращения в таблице (одно обозначение на всю неделю)."""
        if len(raw) != 6:
            raise ValueError(f'Must be 6 values, received {len(raw)}: {raw!r}')
        value_indices = [i for i, v in enumerate(raw) if v]
        if (
                len(value_indices) == 1 and  # если у нас одно непустое значение
                value_indices[0] not in (0, len(raw) - 1) and  # и оно в середине недели
                cls.ACTIVITY_CODES[raw[value_indices[0]]] != TimePlanActivity.HOLIDAY  # и это не праздник
        ):
            # значит, вся неделя имеет одно и то же значение
            result = [cls.ACTIVITY_CODES[raw[value_indices[0]]]] * len(raw)
        else:
            # иначе кодируем неделю как есть
            result = [cls.ACTIVITY_CODES[item] for item in raw]
        if result[-1] == TimePlanActivity.REST_PERIOD:
            result.append(TimePlanActivity.REST_PERIOD)
        else:
            result.append(TimePlanActivity.UNUSED)
        return result

    @classmethod
    def _parse_cells(cls, cells: TableData, start_year: int) -> t.Iterable[GroupPlan]:
        """
        Разбирает таблицу, содержащую график учёбы группы.
        :param cells: Данные таблицы.
        :param start_year: Год осеннего семестра.
        :return: Описание графика учёбы группы.
        """
        for segment in cls._find_segments_in_table(cells):
            sep_1st = datetime.date(year=start_year, month=9, day=1)
            start_day = sep_1st - datetime.timedelta(days=sep_1st.weekday())
            aug_31st = datetime.date(year=start_year+1, month=8, day=31)
            end_day = aug_31st + datetime.timedelta(days=6 - aug_31st.weekday())
            step = datetime.timedelta(weeks=1)
            week_start = start_day
            col_index = segment.start_column
            daily_activities = []
            while week_start < end_day:
                data = [cells[segment.start_row + i][col_index] or '' for i in range(6)]
                week = cls._analyze_week(data)
                week_end = week_start + datetime.timedelta(days=6)
                if week_start < sep_1st:  # это первая неделя?
                    skip = (sep_1st - week_start).days  # пропускаем дни до 1 сентября
                    daily_activities.extend(week[skip:])
                elif week_end > aug_31st:  # это последняя неделя?
                    skip = (week_end - aug_31st).days  # пропускаем дни после 31 августа
                    daily_activities.extend(week[:-skip])
                else:  # это обычная неделя
                    daily_activities.extend(week)
                col_index += 1
                week_start += step
            assert len(daily_activities) == (aug_31st - sep_1st).days + 1
            for group_code in segment.groups_codes:
                yield GroupPlan(specialty_code=segment.spec_code, specialty_name=segment.spec_name,
                                group_code=group_code, year=start_year, activity=tuple(daily_activities))

    @classmethod
    def _find_segments_in_table(cls, data: TableData, monday: str = 'пн') -> t.Iterable[_DetectedSegment]:
        """Находит в таблице области, описывающие календарный график учёбы групп и специальностей."""
        monday = monday.strip().lower()
        ri = 0
        while ri < len(data):  # перебираем строки таблицы
            row = data[ri]
            start_row, dow_col, spec_code, spec_name, group_codes_str = ri + 1, 0, '', '', ''
            for ci, cell in enumerate(row):  # ищем ячейку, содержащую код специальности
                if cell and cls.SPEC_CODE.match(cell):
                    spec_code = cell  # нашли
                    for i in range(ci+1, len(row)):  # следующая непустая ячейка - название специальности
                        if row[i]:
                            spec_name = row[i]
                            break
                    break  # дальше ячейки можно не искать
            else:  # мы не нашли в строке ячейку с кодом специальности - переходим к следующей
                ri += 1
                continue
            # мы нашли специальность - ищем номера групп
            for i in range(start_row, min(start_row+6, len(data))):  # перебираем следующие 6 строк
                for sub_ci, sub_cell in enumerate(data[i]):  # проверяем ячейки строки
                    if sub_cell and cls.GROUP_CODE.match(sub_cell):
                        group_codes_str = sub_cell  # нашли коды групп - дальше не ищем
                        break  # прерываем перебор ячеек в строке
                else:  # если перебрали все ячейки строки, переходим к следующей строке
                    continue
                # сюда мы попадём только если перебрали не все ячейки строки, т.е. нашли что искали
                break  # прерываем перебор строк
            else:  # перебрали все строки, не нашли коды групп - снова ищем специальность
                ri += 1
                continue
            # ищем столбец, содержащий дни недели. В частности, понедельник.
            row = data[start_row]
            while dow_col < len(row) and (not row[dow_col] or row[dow_col].strip().lower() != monday):
                dow_col += 1
            if dow_col == len(row):  # не нашли этот столбец - снова ищем специальность
                ri += 1
                continue
            # разделяем строку с кодами групп. У них может быть разный разделитель - "," или ";", даже в одном файле
            group_codes = tuple(m.group(0) for m in cls.GROUP_CODE.finditer(group_codes_str))
            # возвращаем информацию о найденном регионе таблицы
            yield _DetectedSegment(start_row=start_row, start_column=dow_col+1,
                                   spec_code=spec_code, spec_name=spec_name,
                                   groups_codes=group_codes)
            ri += 6  # пропускаем этот регион таблицы, ищем следующую специальность далее


if __name__ == '__main__':
    import asyncio

    async def main():
        """Быстрая проверка на работоспособность."""
        url = 'https://kosgos.ru/external/op_info.php'
        parser = TimePlanParser(url)
        async for plan in parser.acquire_plans_for(['09.03.02']):
            print(plan.specialty_code, plan.group_code)
            print(plan.prettify())
            break
    asyncio.run(main())
