"""Steam 数据库缓存表与全部处理逻辑。"""

from typing import TypeVar, Optional

from sqlmodel import Field, col, select
from sqlalchemy import UniqueConstraint, delete
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from gsuid_core.webconsole.mount_app import PageSchema, GsAdminModel, site
from gsuid_core.utils.database.base_models import BaseIDModel, with_session

T_SteamCache = TypeVar("T_SteamCache", bound="SteamCache")


class SteamCache(BaseIDModel, table=True):
    """按缓存类型分类的键值缓存，updated_at 供过期清理。"""

    __table_args__ = (
        UniqueConstraint("cache_type", "cache_key", name="uq_steamcache_type_key"),
        {"extend_existing": True},
    )

    cache_type: str = Field(default="", index=True, title="缓存类型")
    cache_key: str = Field(default="", index=True, title="缓存键")
    cache_value: str = Field(default="", title="缓存值")
    updated_at: int = Field(default=0, index=True, title="更新时间戳")

    @classmethod
    @with_session
    async def upsert(
        cls: type[T_SteamCache],
        session: AsyncSession,
        cache_type: str,
        cache_key: str,
        cache_value: str,
        updated_at: int,
    ) -> None:
        result = await session.execute(
            select(cls).where(
                col(cls.cache_type) == cache_type, col(cls.cache_key) == cache_key
            )
        )
        row = result.scalars().first()
        if row is None:
            session.add(
                cls(
                    cache_type=cache_type,
                    cache_key=cache_key,
                    cache_value=cache_value,
                    updated_at=updated_at,
                )
            )
            return

        row.cache_value = cache_value
        row.updated_at = updated_at
        session.add(row)

    @classmethod
    @with_session
    async def get_row(
        cls: type[T_SteamCache],
        session: AsyncSession,
        cache_type: str,
        cache_key: str,
    ) -> Optional[T_SteamCache]:
        result = await session.execute(
            select(cls).where(
                col(cls.cache_type) == cache_type, col(cls.cache_key) == cache_key
            )
        )
        return result.scalars().first()

    @classmethod
    @with_session
    async def get_value(
        cls: type[T_SteamCache],
        session: AsyncSession,
        cache_type: str,
        cache_key: str,
    ) -> Optional[str]:
        result = await session.execute(
            select(col(cls.cache_value)).where(
                col(cls.cache_type) == cache_type, col(cls.cache_key) == cache_key
            )
        )
        return result.scalars().first()

    @classmethod
    @with_session
    async def delete_row(
        cls: type[T_SteamCache],
        session: AsyncSession,
        cache_type: str,
        cache_key: str,
    ) -> int:
        result = await session.execute(
            delete(cls).where(
                col(cls.cache_type) == cache_type, col(cls.cache_key) == cache_key
            )
        )
        return result.rowcount if isinstance(result, CursorResult) else 0

    @classmethod
    @with_session
    async def delete_type(
        cls: type[T_SteamCache],
        session: AsyncSession,
        cache_type: str,
    ) -> int:
        result = await session.execute(
            delete(cls).where(col(cls.cache_type) == cache_type)
        )
        return result.rowcount if isinstance(result, CursorResult) else 0

    @classmethod
    @with_session
    async def delete_expired(
        cls: type[T_SteamCache],
        session: AsyncSession,
        before_ts: int,
        cache_type: Optional[str] = None,
    ) -> int:
        """删除 updated_at 早于 before_ts 的缓存；cache_type 为空表示不限类型。"""
        stmt = delete(cls).where(col(cls.updated_at) < before_ts)
        if cache_type is not None:
            stmt = stmt.where(col(cls.cache_type) == cache_type)
        result = await session.execute(stmt)
        return result.rowcount if isinstance(result, CursorResult) else 0

    @classmethod
    @with_session
    async def clear_all(
        cls: type[T_SteamCache],
        session: AsyncSession,
    ) -> int:
        result = await session.execute(delete(cls))
        return result.rowcount if isinstance(result, CursorResult) else 0


@site.register_admin
class SteamCacheAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(label="Steam缓存管理", icon="fa fa-database")
    model = SteamCache
