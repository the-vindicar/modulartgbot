"""Provides a class that can be used to interact with a Moodle instance using Web API."""
from typing import Any, Union, Optional, overload, Type
import datetime
import enum
import logging

import aiohttp
from pydantic import BaseModel, TypeAdapter, ValidationError, JsonValue

from .errors import MoodleError, InvalidToken
from .webservice import MoodleFunctions, ModelType, RUserDescription

__all__ = ['Moodle']


class Moodle:
    """Represents a connection to a Moodle instance, including account used to perform actions there.

    Keep in mind that Moodle token can be good for a while, so `token` field value can be saved and restored
    between sessions. If the token is absent or has expired, a login attempt will be made to refresh it.

    Additionally, any timestamp sent to the server will be converted to the timezone specified in `timezone` field.
    While we will attempt to retrieve server's timezone, it's often not possible, so please provide a sensible
    default value for that field before doing anything."""
    def __init__(self, baseurl: str, username: str, password: str, service: str = 'moodle_mobile_app',
                 log: logging.Logger = None):
        """Configure access to a Moodle server.
        :param baseurl: Base address of the Moodle server,  e.g. 'https://example.com/moodle/'.
        :param username: Login for the user account we will be using.
        :param password: Password for the user account we will be using.
        :param service: Service name we will be using. By default we impersonate Moodle Mobile,
            since it's usually enabled.
        :param log: Logger to use. By default, a logger named 'moodle' is used."""
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
        self.__user: Optional[RUserDescription] = None

    @property
    def function(self) -> MoodleFunctions:
        """A proxy object used to call Moodle WebAPI functions."""
        return self.__function

    @property
    def base_url(self) -> str:
        """Base URL of the Moodle instance we are working with."""
        return self.__base_url

    @property
    def me(self) -> Optional[RUserDescription]:
        """Information about our account, as retrieved from the server."""
        return self.__user

    async def close(self):
        """Terminates worksession and closes connection to the server.
        Does NOT log the user out, since we might want to reuse the access token in the next session,
        and Moodle does not provide an API call for logging out anyway.

        Consider using ``async with Moodle(...) as m:`` instead of calling this method explicitly.
        """
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
        """Queries the server, while providing a model to validate the result against."""

    @overload
    async def query(self,
                    urlpath: str, params: dict[str, Any] = None,
                    *, model: None = None) -> JsonValue:
        """Queries the server without providing a model."""

    async def query(self,
                    urlpath: str, params: dict[str, Any] = None,
                    *, model: Type[ModelType] = None) -> Union[ModelType, JsonValue]:
        """Makes a GET request to the specified url and returns unpacked JSON data or a model instance.
        :param urlpath: A requested path, relative to the server base URL.
        :param params: Request parameters. Can include lists/tuples/sets, dicts, datetime instances, StrEnum's.
        :param model: A Pydantic model used to validate server response. If None, then no validation is done.
        :returns: An instance of the specified Pydantic model, or just a decoded JSON."""
        if self.__session is None:
            self.__session = aiohttp.ClientSession()
        urlpath = self.__base_url + urlpath
        paramvalues = {}
        for name, value in params.items():
            paramvalues.update(self.transform_param(name, value))
        self._log.debug('Querying %s with params %s', urlpath, paramvalues)
        for attempt in range(2):  # up to 2 query attempts
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
                        except InvalidToken:  # if we get an InvalidToken error, we re-login to refresh the token
                            await self.login()
                            if attempt == 0:
                                continue
                            else:
                                raise
                    else:
                        break
        if model is not None:
            try:
                ta = TypeAdapter(model)
                result = ta.validate_python(response)
            except ValidationError:
                self._log.warning('Validation error!')
                self._log.warning(repr(response))
                raise
            else:
                return result
        else:
            return response

    async def login(self) -> None:
        """Logs into the server and stores the token. See ``token`` attribute.
        This method will be called automatically whenever an invalid token error is received."""
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
        await self._update_user_info()

    async def _update_user_info(self) -> None:
        """Attempts to acquire user info for the account we are using."""
        res = await self.function.core_user_get_users_by_field(field='username', values=[self.__username])
        if not res:
            self.__user = None
            return
        self.__user = res[0]
        tz = self.__user.timezone
        if tz not in ('99', None):  # 99 means "use server timezone". Which we don't know anyway!
            self.timezone = datetime.timezone(datetime.timedelta(hours=float(tz)))

    async def get_download_response(self, fileurl: str) -> aiohttp.ClientResponse:
        """Takes a file URL, adds our token and creates a :class:`asyncio.StreamReader` to download it.
        :param fileurl: Full file URL, including scheme, hostname, etc.
        :returns: A :class:`asyncio.StreamReader` object that can be used to download the file."""
        if self.__session is None:
            self.__session = aiohttp.ClientSession()
        try:
            r = await self.__session.get(fileurl, params={'token': self.token})
        except aiohttp.ClientError as err:
            raise MoodleError(message=f'Connection failed: {err!s}', url=fileurl)
        else:
            if r.status == 200:
                return r
            else:
                raise MoodleError(url=fileurl, message=f'Failed to receive file: [{r.status}]', data=await r.text())

    def timestamp2datetime(self, ts: Optional[int]) -> Optional[datetime.datetime]:
        """Transforms a timestamp into a :class:`datetime.datetime` instance according to server timezone.
        :param ts: Unix-style timestamp or None.
        :returns: A :class:`datetime.datetime` instance, if a timestamp was given, otherwise None."""
        return datetime.datetime.fromtimestamp(ts, self.timezone).astimezone(datetime.timezone.utc) \
            if isinstance(ts, int) and ts > 0 else None

    def datetime2timestamp(self, dt: Optional[datetime.datetime]) -> Optional[int]:
        """Transforms a :class:`datetime.datetime` instance into a timestamp according to server timezone.
        :param dt: :class:`datetime.datetime` object.
        :returns: Unix-style timestamp, or None if nothing was passed."""
        return int(dt.astimezone(self.timezone).timestamp()) if dt is not None else None

    def transform_param(self, name: str, value: Any) -> dict[str, Any]:
        """Transforms a parameter into a form, applicable to be added to URL.
        :param name: Parameter name. Important for array and dictionary parameters.
        :param value: Parameter value.
        :returns: A set of key-value pairs to be added to URL parameter list."""
        if isinstance(value, (tuple, list, set, frozenset)):
            # simple linear collections use this syntax: param[0]=value0&param[1]=value1&...
            result = {}
            for i, val in enumerate(value):
                result.update(self.transform_param(f'{name}[{i}]', val))  # значения преобразуем рекурсивно
            return result
        elif isinstance(value, dict):
            # dictionaries use this syntax: param[key0]=value0&param[key1]=value1&...
            result = {}
            for key, val in value.items():
                result.update(self.transform_param(f'{name}[{key}]', val))  # значения преобразуем рекурсивно
            return result
        elif isinstance(value, BaseModel):
            # Pydantic models are interpreted as dicts
            return self.transform_param(name, value.model_dump(mode='json', exclude_none=True, warnings='error'))
        elif isinstance(value, datetime.datetime):
            # datetime is transformed into an integer timestamp, according to server timezone
            return {name: self.datetime2timestamp(value)}
        elif isinstance(value, enum.Enum):
            # Enums are replaces with their values
            return {name: value.value}
        elif isinstance(value, bool):
            # boolean values are sent as 0 and 1
            return {name: int(value)}
        elif isinstance(value, (int, float, str)):
            # other primitive types are sent as is
            return {name: value}
        elif value is None:
            # None is ignored and not sent
            return {}
        else:
            # and we don't know how to handle anything else so we throw an exception
            raise TypeError(f'Unsupported type for parameter {name!r}: {type(value)!r}')
