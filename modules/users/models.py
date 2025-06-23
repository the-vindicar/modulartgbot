import typing as t
from enum import StrEnum
import datetime

from api import DBModel
from sqlalchemy import JSON, select, delete
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, AsyncSession


__all__ = ['UserBase', 'SiteUser', 'UserRoles', 'UserRepository']


class UserRoles(StrEnum):
    BLOCKED = 'blocked'
    UNVERIFIED = 'unverified'
    VERIFIED = 'verified'
    SITE_ADMIN = 'siteadmin'


class UserBase(DBModel):
    __abstract__ = True


class SiteUser(UserBase):
    __tablename__ = 'Users'
    id: Mapped[int] = mapped_column(primary_key=True)
    tgid: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    role: Mapped[UserRoles] = mapped_column(nullable=False, server_default=UserRoles.UNVERIFIED)
    lastname: Mapped[str] = mapped_column(nullable=False, server_default='')
    firstname: Mapped[str] = mapped_column(nullable=False, server_default='')
    patronym: Mapped[str] = mapped_column(nullable=False, server_default='')
    registered: Mapped[datetime.datetime] = mapped_column(nullable=False, server_default='NOW()')
    fields: Mapped[JSON] = mapped_column(server_default='{}')

    @property
    def fullname_last(self) -> str:
        return ' '.join(filter(None, (self.firstname, self.patronym, self.lastname)))

    @property
    def shortname_last(self) -> str:
        return '. '.join(filter(None, (self.firstname[:1], self.patronym[:1], self.lastname)))

    @property
    def fullname_first(self) -> str:
        return ' '.join(filter(None, (self.lastname, self.firstname, self.patronym)))

    @property
    def shortname_first(self) -> str:
        return '. '.join(filter(None, (self.lastname, self.firstname[:1], self.patronym[:1])))

    @property
    def partname(self) -> str:
        return ' '.join(filter(None, (self.firstname, self.patronym)))


class UserRepository:
    def __init__(self, engine: AsyncEngine):
        self.__sessionmaker = async_sessionmaker(bind=engine, class_=AsyncSession,
                                                 autoflush=True, expire_on_commit=False)

    async def store(self, user: SiteUser):
        async with self.__sessionmaker() as session:
            session.add(user)

    async def delete_by_tgid(self, tgid: int) -> None:
        async with self.__sessionmaker() as session:
            stmt = delete(SiteUser).where(SiteUser.tgid == tgid)
            await session.execute(stmt)

    async def get_by_tgid(self, tgid: int) -> SiteUser | None:
        async with self.__sessionmaker() as session:
            stmt = select(SiteUser).where(SiteUser.tgid == tgid)  # type: ignore
            return await session.scalar(stmt)  # type: ignore

    async def get_by_id(self, userid: int) -> SiteUser | None:
        async with self.__sessionmaker() as session:
            return await session.get(SiteUser, ident=userid)

    async def get_role_by_tg_id(self, tgid: int) -> UserRoles:
        async with self.__sessionmaker() as session:
            stmt = select(SiteUser.role).select_from(SiteUser).where(SiteUser.tgid == tgid)  # type: ignore
            result = await session.scalar(stmt)  # type: ignore
        return UserRoles(result) if result is not None else UserRoles.UNVERIFIED

    async def get_admin(self) -> SiteUser | None:
        async with self.__sessionmaker() as session:
            stmt = select(SiteUser).where(SiteUser.role == UserRoles.SITE_ADMIN)  # type: ignore
            return await session.scalar(stmt)  # type: ignore

    def get_all_with_role(self, role: UserRoles) -> t.AsyncIterable[SiteUser]:
        async with self.__sessionmaker() as session:
            stmt = (
                select(SiteUser)  # type: ignore
                .where(SiteUser.role == role)
                .order_by(SiteUser.registered.desc())
            )
            return session.stream_scalars(stmt)  # type: ignore
