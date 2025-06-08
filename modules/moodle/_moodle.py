# -*- coding: utf-8 -*-
import datetime
from typing import Any, Union, Iterable, Collection, AsyncIterable, Optional
import asyncio
import logging

import aiohttp

from ._classes import *
from ._errors import MoodleError, InvalidToken
from ._funcs import MoodleFunctions


__all__ = ['Moodle']


class Moodle:
    def __init__(self, baseurl: str, username: str, password: str, service: str = 'moodle_mobile_app',
                 log: logging.Logger = None):
        """Задаёт доступ к серверу Moodle.
        :param baseurl: Базовый адрес сервера Moodle. Например, 'https://example.com/moodle/'.
        :param username: Имя пользователя, от имени которого мы будем работать.
        :param password: Пароль пользователя.
        :param service: Имя сервиса, от имени которого мы обращаемся. По умолчанию мы притворяемся Moodle Mobile.
        :param log: Объект журнала. По умолчанию используется журнал под названием 'moodle'."""
        self._log = log if log else logging.getLogger('moodle')
        self.__base_url: str = str(baseurl)
        if not self.__base_url.endswith('/'):
            self.__base_url = self.__base_url + '/'
        self.__username: str = username
        self.__password: str = password
        self.__service: str = service
        self.token: str = ''
        self.timezone: datetime.timezone = datetime.timezone.utc
        self.__session = None
        self.__function = MoodleFunctions(self)

    @property
    def function(self) -> MoodleFunctions:
        """Позволяет вызывать функции Moodle WebAPI."""
        return self.__function

    @property
    def base_url(self) -> str:
        return self.__base_url

    async def close(self):
        """Завершает работу с сервером, удаляя пользовательскую сессию.
        Logout НЕ производится, так как Moodle не предоставляет API для этого.
        Кроме того, возможно, мы захотим переиспользовать наш токен."""
        if self.__session is not None:
            await self.__session.close()
            self.__session = None

    async def __aenter__(self) -> 'Moodle':
        if self.__session is None:
            self.__session = aiohttp.ClientSession()
            await self.__session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.__session is not None:
            await self.__session.__aexit__(exc_type, exc_val, exc_tb)
            self.__session = None

    async def query(self, urlpath: str, params: dict[str, Any] = None) -> Union[list, dict[str, Any]]:
        """Выполняет GET запрос к указанному пути на сервере, передавая указанные параметры, и принимает JSON ответ.
        :param urlpath: Путь, запрашиваемый на сервере. Задаётся относительно базового URL сервера.
        :param params: Передаваемые параметры.
        :returns: Декодированный JSON, отправленный сервером."""
        if self.__session is None:
            self.__session = aiohttp.ClientSession()
        urlpath = self.__base_url + urlpath
        self._log.debug('Querying %s with params %s', urlpath, params)
        for attempt in range(2):  # делаем до 2 попыток
            async with self.__session.get(urlpath, params=params) as r:
                if r.status >= 400:
                    raise MoodleError(url=str(r.url), message=f'Server responded with error code {r.status}')
                try:
                    response = await r.json()
                except aiohttp.ClientError as err:
                    raise MoodleError(url=str(r.url), message=await r.text()) from err
                else:
                    if isinstance(response, dict) and 'exception' in response:
                        try:
                            MoodleError.make_and_raise(str(r.url), response)
                        except InvalidToken:  # если первая попытка провалилась из-за токена, перелогиниваемся.
                            await self.login()
                            if attempt == 0:
                                continue
                            else:
                                raise
                    return response

    async def login(self) -> None:
        """Использует переданные в конструкторе логин и пароль, чтобы получить токен.
        Токен сохраняется в атрибуте `token`. Время жизни токена определяется сервером."""
        url = self.__base_url + 'login/token.php'
        params = dict(username=self.__username, password=self.__password, service=self.__service)
        async with self.__session.get(url, params=params) as r:
            if r.status >= 400:
                raise MoodleError(url=str(r.url), message=f'Server responded with error code {r.status}')
            try:
                response = await r.json()
            except aiohttp.ClientError as err:
                raise MoodleError(url=str(r.url), message=await r.text()) from err
            else:
                if isinstance(response, dict) and 'exception' in response:
                    MoodleError.make_and_raise(str(r.url), response)
                elif not isinstance(response, dict) or 'token' not in response:
                    raise MoodleError(url=str(r.url), message='Key "token" not found in the response')
        self.token = response['token']
        await self._update_timezone()

    async def _update_timezone(self) -> None:
        """Пытается запросить информацию о часовом поясе, настроенном для той учётной записи, которую мы используем."""
        res = await self.function.core_user_get_users_by_field(field='username', values=[self.__username])
        if res and 'timezone' in res[0]:
            tz = res[0]['timezone']
            if tz != '99':  # 99 означает, что мы используем часовой пояс сервера
                self.timezone = datetime.timezone(datetime.timedelta(hours=float(tz)))

    async def get_download_fileobj(self, fileurl: str) -> asyncio.StreamReader:
        """Имея ссылку на файл, формирует поток для его скачивания.
        :param fileurl: Полная ссылка на файл, включающая в себя адрес и путь сервера.
        :returns: Поток для скачивания содержимого файла."""
        if self.__session is None:
            self.__session = aiohttp.ClientSession()
        try:
            r = await self.__session.get(fileurl, params={'token': self.token})
        except aiohttp.ClientError as err:
            raise MoodleError(message=f'Connection failed: {err!s}', url=fileurl)
        else:
            if r.status == 200:
                return r.content
            else:
                raise MoodleError(url=fileurl, message=f'Failed to receive file: [{r.status}]', data=await r.text())

    def timestamp2datetime(self, item: dict[str, Any], key: str) -> Optional[datetime.datetime]:
        """Преобразует метку времени сервера (если она есть) в объект :class:`datetime.datetime`
        с учётом часового пояса.
        :param item: Словарь, в котором может содержаться метка времени.
        :param key: Ключ в словаре, по которому может содержаться метка времени.
        :returns: Объект :class:`datetime.datetime`, если в словаре по этому ключу присуствует целое число.
        В противном случае None."""
        value: Optional[int] = item.get(key, None)
        return datetime.datetime.fromtimestamp(value, self.timezone).astimezone(datetime.timezone.utc) \
            if isinstance(value, int) else None

    async def stream_enrolled_courses(self,
                                      in_progress_only: bool = True,
                                      teacher_role_ids: Collection[role_id] = tuple(),
                                      batch_size: int = 10,
                                      ) -> AsyncIterable[Course]:
        """Возвращает поток объектов-курсов, на которые мы подписаны, соответствующих условиям.
        :param in_progress_only: Если True, возвращать нужно только курсы, которые уже начались, но ещё не закончились.
        :param teacher_role_ids: Коллекция идентификаторов ролей, которые считаются преподавателями.
            Пользователи с этими ролями попадут в коллекцию `teachers` объекта курса.
        :param batch_size: Сколько курсов запрашивать за один запрос.
        :returns: Асинхронный поток экземпляров класса :class:`Course`."""
        offset, limit = 0, batch_size
        while True:
            raw_course_data = await self.function.core_course_get_enrolled_courses_by_timeline_classification(
                classification='inprogress' if in_progress_only else 'all',
                offset=offset, limit=limit)
            raw_courses = raw_course_data.get('courses', [])
            if not raw_courses:
                break
            offset = raw_course_data['nextoffset']
            for item in raw_courses:
                starts = self.timestamp2datetime(item, 'startdate')
                ends = self.timestamp2datetime(item, 'enddate')
                cid = item['id']
                teachers, students = [], []
                async for p in self.stream_users(cid):
                    if any(r in teacher_role_ids for r in p.roles):
                        teachers.append(p)
                    else:
                        students.append(p)
                c = Course(id=cid, shortname=item['shortname'], fullname=item['fullname'],
                           starts=starts, ends=ends, students=tuple(students), teachers=tuple(teachers))
                yield c

    async def stream_users(self,
                           courseid: course_id,
                           batch_size: int = 50
                           ) -> AsyncIterable[Participant]:
        """Возвращает поток объектов-участников данного курса.
        :param courseid: Идентификатор курса, для которого мы загружаем участников.
        :param batch_size: Сколько участников запрашивать за один запрос.
        :returns: Асинхронный поток экземпляров класса :class:`Participant`."""
        options = [
            {'name': 'userfields', 'value': 'id, fullname, email, roles, groups'}
        ]
        offset, limit = 0, batch_size
        while True:
            limits = [
                {'name': 'limitfrom', 'value': offset},
                {'name': 'limitnumber', 'value': limit},
            ]
            raw_users = await self.function.core_enrol_get_enrolled_users(
                courseid=courseid, options=options + limits
            )
            if not raw_users:
                break
            offset += len(raw_users)
            for raw_user in raw_users:
                p = Participant(
                    user=User(id=raw_user['id'], name=raw_user['fullname'], email=raw_user['email']),
                    roles=tuple([Role(id=r['roleid'], name=r['name']) for r in raw_user.get('roles', [])]),
                    groups=tuple([Group(id=g['id'], name=g['name']) for g in raw_user.get('groups', [])]),
                )
                yield p

    async def stream_assignments(self, course_ids: Iterable[course_id]) -> AsyncIterable[Assignment]:
        """Возвращает поток объектов-заданий (assignment), имеющихся в данных курсах.
        :param course_ids: Идентификаторы курсов, из которых мы загружаем задания.
        :returns: Асинхронный поток экземпляров класса :class:`Assignment`."""
        response = await self.function.mod_assign_get_assignments(
            courseids=list(course_ids), includenotenrolledcourses=1
        )
        for course in response['courses']:
            raw_assigns = course['assignments']
            if not raw_assigns:
                continue
            for raw_assign in raw_assigns:
                a = Assignment(
                    id=raw_assign['id'],
                    name=raw_assign['name'],
                    course_id=raw_assign['course'],
                    opening=self.timestamp2datetime(raw_assign, 'allowsubmissionsfromdate'),
                    closing=self.timestamp2datetime(raw_assign, 'duedate'),
                    cutoff=self.timestamp2datetime(raw_assign, 'cutoffdate')
                )
                yield a

    async def stream_submissions(self, assignmentid: assignment_id,
                                 submitted_after: Optional[datetime.datetime] = None,
                                 submitted_before: Optional[datetime.datetime] = None
                                 ) -> AsyncIterable[Submission]:
        """Возвращает поток объектов-ответов на указанное задание.
        :param assignmentid: Идентификатор задания, для которого мы загружаем ответы.
        :param submitted_after: Дата и время, позднее которого (включительно) ответ был загружен.
        :param submitted_before: Дата и время, ранее которого (включительно) ответ был загружен.
        :returns: Асинхронный поток экземпляров класса :class:`Submission`."""
        responce = await self.function.mod_assign_get_submissions(
            assignmentids=[assignmentid],
            since=int(submitted_after.astimezone(self.timezone).timestamp()) if submitted_after is not None else 0,
            before=int(submitted_before.astimezone(self.timezone).timestamp()) if submitted_before is not None else 0,
        )
        for raw_assign in responce['assignments']:
            assign_id = raw_assign['assignmentid']
            raw_subs = raw_assign.get('submissions', [])
            if not raw_subs:
                continue
            for raw_sub in raw_subs:
                sub_id = raw_sub['id']
                uid = raw_sub['userid']
                files = []
                for plugin in raw_sub.get('plugins', []):
                    if plugin['type'] == 'file':
                        for area in plugin['fileareas']:
                            if area['area'] == 'submission_files':
                                for raw_file in area['files']:
                                    file = SubmittedFile(
                                        submission_id=sub_id,
                                        filename=raw_file['filename'],
                                        mimetype=raw_file['mimetype'],
                                        filesize=raw_file['filesize'],
                                        url=raw_file['fileurl'],
                                        uploaded=self.timestamp2datetime(raw_file, 'timemodified')
                                    )
                                    files.append(file)
                s = Submission(
                    id=sub_id,
                    assignment_id=assign_id,
                    user_id=uid,
                    updated=self.timestamp2datetime(raw_sub, 'timemodified'),
                    files=tuple(files)
                )
                yield s
