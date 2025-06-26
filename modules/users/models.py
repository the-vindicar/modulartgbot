"""Структура и логика хранилища данных для пользователей."""
import typing as t
from enum import StrEnum
import datetime
import random

from api import DBModel
from sqlalchemy import JSON, select, delete, Sequence, DateTime, ForeignKey
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, AsyncSession
from sqlalchemy.dialects.postgresql import insert as upsert


__all__ = ['UserBase', 'SiteUser', 'UserRoles', 'UserRepository']


class UserRoles(StrEnum):
    """Возможные роли пользователя."""
    BLOCKED = 'blocked'
    UNVERIFIED = 'unverified'
    VERIFIED = 'verified'
    SITE_ADMIN = 'siteadmin'


class UserBase(DBModel):
    __abstract__ = True


class SiteUser(UserBase):
    __tablename__ = 'Users'
    id: Mapped[int] = mapped_column(Sequence('User_ID'), primary_key=True, autoincrement=True)
    tgid: Mapped[int | None] = mapped_column(unique=True, nullable=True)
    role: Mapped[UserRoles] = mapped_column(nullable=False, server_default=UserRoles.UNVERIFIED)
    lastname: Mapped[str] = mapped_column(nullable=False, server_default='')
    firstname: Mapped[str] = mapped_column(nullable=False, server_default='')
    patronym: Mapped[str] = mapped_column(nullable=False, server_default='')
    registered: Mapped[datetime.datetime] = mapped_column(nullable=False, server_default='NOW()')
    fields: Mapped[JSON] = mapped_column(server_default='{}')

    @property
    def fullname_last(self) -> str:
        """Имя Отчество Фамилия"""
        return ' '.join(filter(None, (self.firstname, self.patronym, self.lastname)))

    @property
    def shortname_last(self) -> str:
        """И. О. Фамилия"""
        return '. '.join(filter(None, (self.firstname[:1], self.patronym[:1], self.lastname)))

    @property
    def fullname_first(self) -> str:
        """Фамилия Имя Отчество"""
        return ' '.join(filter(None, (self.lastname, self.firstname, self.patronym)))

    @property
    def shortname_first(self) -> str:
        """Фамилия И.О."""
        return '. '.join(filter(None, (self.lastname, self.firstname[:1], self.patronym[:1])))

    @property
    def partname(self) -> str:
        """Имя Отчество"""
        return ' '.join(filter(None, (self.firstname, self.patronym)))


class OneTimeCode(UserBase):
    __tablename__ = 'OneTimeCodes'
    intent: Mapped[str] = mapped_column(primary_key=True,
                                        comment='Назначение одноразового кода')
    user_id: Mapped[int] = mapped_column(ForeignKey(SiteUser.id, ondelete='cascade'), primary_key=True,
                                         comment='К какому пользователю привязан этот код')
    code: Mapped[str] = mapped_column(unique=True, nullable=False,
                                      comment='Одноразовый код')
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                              comment='Когда истекает срок действия кода')


class UserRepository:
    """Предоставляет доступ к базе пользователей."""
    def __init__(self, engine: AsyncEngine):
        self.__sessionmaker = async_sessionmaker(bind=engine, class_=AsyncSession,
                                                 autoflush=True, expire_on_commit=False)

    async def store(self, user: SiteUser) -> None:
        """Сохраняет сведения о пользователе (новом или существующем).
        :param user: Пользователь, сведения о котором нужно сохранять."""
        async with self.__sessionmaker() as session:
            stmt = upsert(SiteUser)
            stmt = stmt.on_conflict_do_update(
                index_elements=[SiteUser.id],
                set_={
                    SiteUser.firstname: stmt.excluded.firstname,
                    SiteUser.patronym: stmt.excluded.patronym,
                    SiteUser.lastname: stmt.excluded.lastname,
                    SiteUser.tgid: stmt.excluded.tgid,
                    SiteUser.role: stmt.excluded.role,
                }
            )
            await session.execute(stmt, dict(
                id=user.id, tgid=user.tgid, role=user.role,
                firstname=user.firstname, patronym=user.patronym, lastname=user.lastname
            ))
            await session.commit()

    async def delete_by_tgid(self, tgid: int) -> None:
        """Удаляет пользователя с указанным Telegram ID.
        :param tgid: Telegram ID удаляемого пользователя."""
        async with self.__sessionmaker() as session:
            stmt = delete(SiteUser).where(SiteUser.tgid == tgid)
            await session.execute(stmt)
            await session.commit()

    async def get_by_tgid(self, tgid: int) -> SiteUser | None:
        """Возвращает пользователя с указанным Telegram ID.
        :param tgid: Telegram ID пользователя.
        :returns: Пользователь, или None, если такого Telegram ID нет."""
        async with self.__sessionmaker() as session:
            stmt = select(SiteUser).where(SiteUser.tgid == tgid)
            return await session.scalar(stmt)

    async def get_by_id(self, userid: int) -> SiteUser | None:
        """Возвращает пользователя с указанным ID.
        :param userid: ID пользователя.
        :returns: Пользователь, или None, если такого ID нет."""
        async with self.__sessionmaker() as session:
            return await session.get(SiteUser, ident=userid)

    async def get_role_by_tg_id(self, tgid: int) -> UserRoles:
        """Возвращает роль пользователя по его Telegram ID.
        :param tgid: Telegram ID пользователя.
        :returns: Обозначение роли."""
        async with self.__sessionmaker() as session:
            stmt = select(SiteUser.role).select_from(SiteUser).where(SiteUser.tgid == tgid)
            result = await session.scalar(stmt)
        return UserRoles(result) if result is not None else UserRoles.UNVERIFIED

    async def get_admin(self) -> SiteUser | None:
        """Возвращает первого пользователя-администратора.
        :returns: Администратор, или None, если нет пользователя с ролью администратора."""
        async with self.__sessionmaker() as session:
            stmt = select(SiteUser).where(SiteUser.role == UserRoles.SITE_ADMIN)
            return await session.scalar(stmt)

    async def get_all_with_role(self, role: UserRoles) -> t.AsyncIterable[SiteUser]:
        """Возвращает все пользователей с указанной ролью.
        :param role: Требуемая роль.
        :returns: Поток пользователей с этой ролью."""
        async with self.__sessionmaker() as session:
            stmt = (
                select(SiteUser)
                .where(SiteUser.role == role)
                .order_by(SiteUser.registered.desc())
            )
            return await session.stream_scalars(stmt)

    async def create_onetime_code(self, intent: str, target: SiteUser, lifetime: datetime.timedelta
                                  ) -> tuple[str, datetime.datetime]:
        """Генерирует одноразовый код для указанного пользователя.
        :param intent: Назначение кода. Можно считать это пространством имён.
        :param target: Для кого создаётся код.
        :param lifetime: Время пригодности кода.
        :returns: Значение созданного кода. Уникально идентифицирует пользователя и намерение."""
        await self.expire_old_onetime_codes()
        CODE_CHARS = '0123456789'
        stmt = upsert(OneTimeCode)
        stmt = stmt.on_conflict_do_update(
            index_elements=[OneTimeCode.intent, OneTimeCode.user_id],
            set_={
                OneTimeCode.code: stmt.excluded.code,
                OneTimeCode.expires: stmt.excluded.expires
            }
        )
        async with self.__sessionmaker() as session:
            for attempt in range(10):
                codeparts = [CODE_CHARS[random.randrange(len(CODE_CHARS))] for _ in range(8)]
                code = (''.join(codeparts[:len(codeparts) // 2])) + '-' + (''.join(codeparts[len(codeparts) // 2:]))
                expires = datetime.datetime.now(datetime.timezone.utc) + lifetime
                try:
                    await session.execute(stmt, {
                        'intent': intent, 'user_id': target.id, 'code': code, 'expires': expires
                    })
                except IntegrityError:
                    continue  # код оказался не уникален - пробуем ещё раз.
                else:
                    await session.commit()
                    return code, expires
        raise RuntimeError('Somehow, we failed to create a unique random code...')

    async def try_consume_onetime_code(self, code: str) -> t.Optional[tuple[str, SiteUser]]:
        """Проверяет наличие соответствующего одноразового кода. Если код существует и не устарел,
        возвращает назначение кода и пользователя, с которым он ассоциирован. При этом код будет удалён из базы.
        :param code: Текст кода. Он уникален, что позволяет идентифицировать пользователя и назначение.
        :returns: Пара "назначение-пользователь" или None, если код неверен или устарел."""
        await self.expire_old_onetime_codes()
        async with self.__sessionmaker() as session:
            stmt = (
                select(OneTimeCode.intent, SiteUser)
                .select_from(OneTimeCode)
                .join(SiteUser, SiteUser.id == OneTimeCode.user_id)
                .where(OneTimeCode.code == code)
            )
            result = await session.execute(stmt)
            row = result.fetchone()
            if row is None:
                return None
            intent, user = row
            await session.execute(delete(OneTimeCode).where(OneTimeCode.code == code))
            await session.commit()
        return intent, user

    async def expire_old_onetime_codes(self) -> None:
        """Удаляет все одноразовые коды, у которых истек срок действия."""
        now = datetime.datetime.now(datetime.timezone.utc)
        async with self.__sessionmaker() as session:
            await session.execute(delete(OneTimeCode).where(OneTimeCode.expires <= now))
            await session.commit()
