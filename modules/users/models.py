"""Структура и логика хранилища данных для пользователей."""
import typing as t
from enum import StrEnum
import datetime
import random
import re

from api import DBModel
from sqlalchemy import JSON, select, delete, Sequence, DateTime, ForeignKey, func, String, UnaryExpression
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, AsyncSession
from sqlalchemy.dialects.postgresql import insert as upsert


__all__ = ['UserBase', 'SiteUser', 'NameStyle', 'UserRoles', 'UserRepository']


class UserRoles(StrEnum):
    """Возможные роли пользователя."""
    BLOCKED = 'blocked'
    UNVERIFIED = 'unverified'
    VERIFIED = 'verified'
    SITE_ADMIN = 'siteadmin'


class NameStyle(StrEnum):
    """Стили записи реального имени пользователя."""
    LastFP = 'Last F P'
    FPLast = 'F P Last'
    LastFirstPatronym = 'Last First Patronym'
    FirstPatronymLast = 'First Patronym Last'
    FirstPatronym = 'First Patronym'


class UserBase(DBModel):
    __abstract__ = True


class SiteUser(UserBase):
    __tablename__ = 'Users'
    id: Mapped[int] = mapped_column(Sequence('User_ID'), primary_key=True, autoincrement=True,
                                    comment='ID пользователя')
    tgid: Mapped[int | None] = mapped_column(unique=True, nullable=True,
                                             comment='ID пользователя в Telegram')
    moodleid: Mapped[int | None] = mapped_column(unique=True, nullable=True,
                                                 comment='ID пользователя в Moodle')
    role: Mapped[UserRoles] = mapped_column(String(16), nullable=False, server_default=UserRoles.UNVERIFIED,
                                            comment='Роль пользователя')
    lastname: Mapped[str] = mapped_column(nullable=False, server_default='',
                                          comment='Фамилия')
    firstname: Mapped[str] = mapped_column(nullable=False, server_default='',
                                           comment='Имя')
    patronym: Mapped[str] = mapped_column(nullable=False, server_default='',
                                          comment='Отчество')
    registered: Mapped[datetime.datetime] = mapped_column(nullable=False, server_default='NOW()',
                                                          comment='Дата регистрации')
    fields: Mapped[dict[str, t.Any]] = mapped_column(JSON, server_default='{}',
                                                     comment='Дополнительные сведения')

    def get_name(self, style: NameStyle) -> str:
        """Возвращает имя в указанном стиле."""
        if style == NameStyle.FirstPatronymLast:
            return ' '.join(filter(None, (self.firstname, self.patronym, self.lastname)))
        elif style == NameStyle.LastFirstPatronym:
            return ' '.join(filter(None, (self.lastname, self.firstname, self.patronym)))
        elif style == NameStyle.FPLast:
            result = ''
            if self.firstname:
                result += self.firstname[0] + '. '
                if self.patronym:
                    result += self.patronym[0] + '. '
            result += self.lastname
            return result
        elif style == NameStyle.LastFP:
            result = self.lastname
            if self.firstname:
                result += f' {self.firstname[0]}.'
                if self.patronym:
                    result += f' {self.patronym[0]}.'
            return result
        elif style == NameStyle.FirstPatronym:
            result = ' '.join(filter(None, (self.firstname, self.patronym))) or self.lastname
            return result
        else:
            raise ValueError(f'{style!r} is not a correct NameStyle')

    _SPLIT_RE = {
        NameStyle.LastFirstPatronym: r'^\s*(?P<last>\S+)\s+(?P<first>\S+)\s+(?P<patronym>.+)\s*$',
        NameStyle.FirstPatronymLast: r'^\s*(?P<first>\S+)\s+(?P<patronym>.+)\s+(?P<last>\S+)\s*$',
        NameStyle.LastFP: r'^\s*(?P<last>\S+)\s+(?P<first>\S)\.\s*(?:(?P<patronym>\S)\.)?\s*$',
        NameStyle.FPLast: r'^\s*(?P<first>\S)\.\s*(?:(?P<patronym>\S)\.)?\s*(?P<last>\S+)\s*$',
        NameStyle.FirstPatronym: r'^\s*(?P<first>\S+)\s+(?P<patronym>.+?)\s*$',
    }

    @classmethod
    def split_name(cls, name: str, style: NameStyle) -> t.Optional[tuple[str, str, str]]:
        """Разбивает строку с именем пользователя на три части: имя, отчество, фамилия.
        Вместо имени и отчества могут быть инициалы.
        :param name: Строка с именем в указанном стиле.
        :param style: Ожидаемый стиль имени.
        :returns: Кортеж из трёх строк: имя, отчество, фамилия. None, если строка не соответствует шаблону."""
        pattern = cls._SPLIT_RE[style]
        match = re.match(pattern, name)
        if not match:
            return None
        parts = match.groupdict()
        return parts.get('first', ''), parts.get('patronym', ''), parts.get('last', '')


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

    async def create_tables(self) -> None:
        """Создаёт таблицы, относящиеся к пользователям системы."""
        engine: AsyncEngine = self.__sessionmaker.kw['bind']
        async with engine.connect() as conn:
            await conn.run_sync(UserBase.metadata.create_all)
            await conn.commit()

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

    async def get_by_name(self, name: str, style: NameStyle) -> list[SiteUser]:
        """Ищет пользователей по имени, заданном в указанном стиле.
        :param name: Образец имени, например, "Иван Иванович Иванов" или "Петров П.П.".
        :param style: Стиль имени, например, NameStyle.FirstPatronymLast или NameStyle.LastFP.
        :returns: Список подходящих под условия пользователей."""
        stmt = select(SiteUser)
        parts = SiteUser.split_name(name, style)
        if not parts:
            return []
        first, patronym, last = parts[0].lower(), parts[1].lower(), parts[2].lower()
        if style in (NameStyle.LastFirstPatronym, NameStyle.FirstPatronymLast):
            stmt = stmt.where(
                func.lower(SiteUser.lastname) == last,
                func.lower(SiteUser.firstname) == first,
                func.lower(SiteUser.patronym) == patronym,
            )
        elif style in (NameStyle.LastFP, NameStyle.FPLast):
            stmt = stmt.where(
                func.lower(SiteUser.lastname) == last,
                func.lower(SiteUser.firstname).like(f'{first}%'),
                func.lower(SiteUser.patronym).like(f'{patronym}%'),
            )
        elif style == NameStyle.FirstPatronym:
            stmt = stmt.where(
                func.lower(SiteUser.firstname) == first,
                func.lower(SiteUser.patronym) == patronym,
            )
        else:
            raise ValueError(f'{style!r} is not a correct NameStyle')
        async with self.__sessionmaker() as session:
            result = await session.scalars(stmt)
            return list(result.all())

    async def get_role_by_tg_id(self, tgid: int) -> UserRoles:
        """Возвращает роль пользователя по его Telegram ID.
        :param tgid: Telegram ID пользователя.
        :returns: Обозначение роли."""
        async with self.__sessionmaker() as session:
            stmt = select(SiteUser.role).select_from(SiteUser).where(SiteUser.tgid == tgid)
            result = await session.scalar(stmt)
        return UserRoles(result) if result is not None else UserRoles.UNVERIFIED

    async def get_role_by_id(self, userid: int) -> UserRoles:
        """Возвращает роль пользователя по его ID.
        :param userid: ID пользователя.
        :returns: Обозначение роли."""
        async with self.__sessionmaker() as session:
            stmt = select(SiteUser.role).select_from(SiteUser).where(SiteUser.id == userid)
            result = await session.scalar(stmt)
        return UserRoles(result) if result is not None else UserRoles.UNVERIFIED

    async def get_admin(self) -> SiteUser | None:
        """Возвращает первого пользователя-администратора.
        :returns: Администратор, или None, если нет пользователя с ролью администратора."""
        async with self.__sessionmaker() as session:
            stmt = select(SiteUser).where(SiteUser.role == UserRoles.SITE_ADMIN)
            return await session.scalar(stmt)

    async def get_all_by_roles(self, *roles: UserRoles,
                               inverted: bool = False,
                               order_by: t.Collection[UnaryExpression] = (SiteUser.id.asc(),)
                               ) -> t.Sequence[SiteUser]:
        """Возвращает всех пользователей с указанными ролями (или всех без указанных ролей).
        :param roles: Пользователь должен иметь одну из этих ролей.
        :param inverted: Если истина, пользователь НЕ должен иметь одну из указанных ролей.
        :param order_by: Правила сортировки получаемого списка.
        :returns: Поток пользователей с этой ролью."""
        async with self.__sessionmaker() as session:
            condition = SiteUser.role.notin_(roles) if inverted else SiteUser.role.in_(roles)
            stmt = (
                select(SiteUser)
                .where(condition)
                .order_by(*order_by)
            )
            result = await session.scalars(stmt)
            return result.all()

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

    async def try_consume_onetime_code(self, code: str, intent: str = None
                                       ) -> tuple[t.Optional[str], t.Optional[SiteUser]]:
        """Проверяет наличие соответствующего одноразового кода. Если код существует и не устарел,
        возвращает назначение кода и пользователя, с которым он ассоциирован. При этом код будет удалён из базы.
        :param code: Текст кода. Он уникален, что позволяет идентифицировать пользователя и назначение.
        :param intent: Назначение кода. Если указано и не None, то даже существующий в базе код не будет принят и
            удалён, если его назначение не совпадает с указанным. Если None, то будет принят код с любым назначением.
            Назначение кода будет возвращено вместе с пользователем.
        :returns: Пара "назначение-пользователь" или пара None-None, если код неверен или устарел."""
        await self.expire_old_onetime_codes()
        async with self.__sessionmaker() as session:
            stmt = (
                select(OneTimeCode.intent, SiteUser)
                .select_from(OneTimeCode)
                .join(SiteUser, SiteUser.id == OneTimeCode.user_id)
                .where(OneTimeCode.code == code)
            )
            if intent is not None:
                stmt = stmt.where(OneTimeCode.intent == intent)
            result = await session.execute(stmt)
            row = result.fetchone()
            if row is None:
                return None, None
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
