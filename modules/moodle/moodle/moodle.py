# -*- coding: utf-8 -*-
import datetime
from typing import Any, Union, Optional, overload, Type
import asyncio
import logging

import aiohttp
from pydantic import TypeAdapter

from .errors import MoodleError, InvalidToken
from .webservice import MoodleFunctions, ModelType

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

    @overload
    async def query(self,
                    urlpath: str, params: dict[str, Any] = None,
                    *, model: Type[ModelType]) -> ModelType:
        ...

    @overload
    async def query(self,
                    urlpath: str, params: dict[str, Any] = None,
                    *, model: None = None) -> Union[list, dict[str, Any]]:
        ...

    async def query(self,
                    urlpath: str, params: dict[str, Any] = None,
                    *, model: Type[ModelType] = None) -> Union[ModelType, list, dict[str, Any]]:
        """Выполняет GET запрос к указанному пути на сервере, передавая указанные параметры, и принимает JSON ответ.
        :param urlpath: Путь, запрашиваемый на сервере. Задаётся относительно базового URL сервера.
        :param params: Передаваемые параметры.
        :param model: Модель Pydantic, которой должен соответствовать ответ сервера.
        :returns: Декодированный JSON, отправленный сервером."""
        if self.__session is None:
            self.__session = aiohttp.ClientSession()
        urlpath = self.__base_url + urlpath
        paramvalues = {}
        for name, value in params.items():
            paramvalues.update(self.transform_param(name, value))
        self._log.debug('Querying %s with params %s', urlpath, paramvalues)
        for attempt in range(2):  # делаем до 2 попыток
            async with self.__session.get(urlpath, params=paramvalues) as r:
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
                    if model is not None:
                        ta = TypeAdapter(model)
                        return ta.validate_python(response)
                    else:
                        return response

    async def login(self) -> None:
        """Использует переданные в конструкторе логин и пароль, чтобы получить токен.
        Токен сохраняется в атрибуте `token`. Время жизни токена определяется сервером."""
        if self.__session is None:
            self.__session = aiohttp.ClientSession()
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
        res = await self.function('core_user_get_users_by_field', dict(field='username', values=[self.__username]))
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

    def timestamp2datetime(self, ts: Optional[int]) -> Optional[datetime.datetime]:
        """Преобразует метку времени сервера в объект :class:`datetime.datetime`
        с учётом часового пояса.
        :param ts: Метка времени.
        :returns: Объект :class:`datetime.datetime`, если передана метка времени. В противном случае None."""
        return datetime.datetime.fromtimestamp(ts, self.timezone).astimezone(datetime.timezone.utc) \
            if isinstance(ts, int) and ts > 0 else None

    def datetime2timestamp(self, dt: Optional[datetime.datetime]) -> Optional[int]:
        """Преобразует объект :class:`datetime.datetime` в метку времени сервера с учётом часового пояса.
        :param dt: Дата-время.
        :returns: Метка времени, если передан объект datetime. В противном случае None."""
        return int(dt.astimezone(self.timezone).timestamp()) if dt is not None else None

    def transform_param(self, name: str, value: Any) -> dict[str, Any]:
        """Выполняет преобразование параметров вызываемой функции в форму, пригодную для передачи в URL.
        :param name: Имя параметра. Служит основой для параметров-массивов и параметров-словарей.
        :param value: Значение параметра. Его тип определяет характер преобразования.
        :returns: Набор имён и значений примитивных параметров, которые следует подставить в URL."""
        if isinstance(value, (tuple, list, set, frozenset)):
            # линейные коллекции используют синтаксис param[0]=value0&param[1]=value1&...
            result = {}
            for i, val in enumerate(value):
                result.update(self.transform_param(f'{name}[{i}]', val))  # значения преобразуем рекурсивно
            return result
        elif isinstance(value, dict):
            # словари используют синтаксис param[key0]=value0&param[key1]=value1&...
            result = {}
            for key, val in value.items():
                result.update(self.transform_param(f'{name}[{key}]', val))  # значения преобразуем рекурсивно
            return result
        elif isinstance(value, datetime.datetime):
            # дата и время преобразуется в часовой пояс сервера, а потом в int
            return {name: self.datetime2timestamp(value)}
        elif isinstance(value, (int, float, str)):
            # примитивные типы данные передаются как есть
            return {name: value}
        else:
            # мы не знаем, как поступать с остальным
            raise TypeError(f'Unsupported type for parameter {name!r}: {type(value)!r}')
