# -*- coding: utf-8 -*-
from typing import Any, Union, List, Dict
import asyncio
import logging

import aiohttp

from ._errors import MoodleError, InvalidToken
from ._funcs import MoodleFunctions


__all__ = ['Moodle']


class Moodle:
    def __init__(self, baseurl: str, username: str, password: str, service: str = 'moodle_mobile_app',
                 log: logging.Logger = None):
        self._log = log if log else logging.getLogger('moodle')
        self.__base_url: str = str(baseurl)
        if not self.__base_url.endswith('/'):
            self.__base_url = self.__base_url + '/'
        self.__username: str = username
        self.__password: str = password
        self.__service: str = service
        self.token: str = ''
        self.__session = None
        self.__function = MoodleFunctions(self)

    @property
    def function(self) -> MoodleFunctions:
        return self.__function

    @property
    def base_url(self) -> str:
        return self.__base_url

    async def close(self):
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

    async def query(self, url: str, params: Dict[str, Any] = None, *, key: Union[None, str] = None
                    ) -> Union[List, Dict[str, Any]]:
        if self.__session is None:
            self.__session = aiohttp.ClientSession()
        self._log.debug('Querying %s with params %s', url, params)
        for attempt in range(2):
            async with self.__session.get(url, params=params) as r:
                if r.status >= 400:
                    raise MoodleError(f'Server responded with error code {r.status}')
                try:
                    response = await r.json()
                except aiohttp.ClientError as err:
                    raise MoodleError(await r.text()) from err
                else:
                    if isinstance(response, dict) and 'exception' in response:
                        try:
                            MoodleError.make_and_raise(response)
                        except InvalidToken:
                            await self.login()
                            if attempt == 0:
                                continue
                            else:
                                raise
                    elif isinstance(key, str):
                        if not isinstance(response, dict) or key not in response:
                            raise MoodleError(f'Key "{key}" not found in the response')
                        else:
                            return response
                    return response

    async def login(self) -> None:
        url = self.__base_url + 'login/token.php'
        params = dict(username=self.__username, password=self.__password, service=self.__service)
        async with self.__session.get(url, params=params) as r:
            if r.status >= 400:
                raise MoodleError(f'Server responded with error code {r.status}')
            try:
                response = await r.json()
            except aiohttp.ClientError as err:
                raise MoodleError(await r.text()) from err
            else:
                if isinstance(response, dict) and 'exception' in response:
                    MoodleError.make_and_raise(response)
                elif not isinstance(response, dict) or 'token' not in response:
                    raise MoodleError(f'Key "token" not found in the response')
        self.token = response['token']

    async def get_download_fileobj(self, fileurl: str) -> asyncio.StreamReader:
        if self.__session is None:
            self.__session = aiohttp.ClientSession()
        try:
            r = await self.__session.get(fileurl, params={'token': self.token})
        except aiohttp.ClientError as err:
            raise MoodleError(f'Connection failed: {err!s}')
        else:
            if r.status == 200:
                return r.content
            else:
                raise MoodleError(f'Failed to receive file: [{r.status}]', data=await r.text())
