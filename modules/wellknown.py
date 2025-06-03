"""
Предоставляет список известных пользователей системы.
"""
import typing as t
import dataclasses
import logging

from api import CoreAPI


@dataclasses.dataclass(frozen=True, slots=True)
class WellKnownUserInfo:
    name: str = ''
    tgid: t.Optional[int] = None


class WellKnownUsers(t.Mapping[str, WellKnownUserInfo]):
    def __init__(self, src: t.Mapping[str, t.Mapping[str, t.Any]]):
        super().__init__()
        self.__data: dict[str, WellKnownUserInfo] = {}
        for name, data in src.items():
            self.__data[name] = WellKnownUserInfo(name=name, **data)

    def __len__(self) -> int:
        return len(self.__data)

    def __bool__(self) -> bool:
        return bool(self.__data)

    def __iter__(self):
        return iter(self.__data)

    def __getitem__(self, item: str) -> WellKnownUserInfo:
        return self.__data[item]


requires = []
provides = [WellKnownUsers]
__all__ = ['WellKnownUserInfo', 'WellKnownUsers']


@dataclasses.dataclass
class WellKnownConfig:
    teachers: dict[str, dict[str, t.Any]]


async def lifetime(api: CoreAPI):
    log = logging.getLogger('modules.wellknown')
    log.debug('Loading wellknown users...')
    cfg = await api.config.load('wellknown', WellKnownConfig)
    users = WellKnownUsers(cfg.teachers)
    log.info('Discovered %d wellknown users.', len(users))

    async def provider():
        return users

    api.register_api_provider(provider, WellKnownUsers)
    yield
