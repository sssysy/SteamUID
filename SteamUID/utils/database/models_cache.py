from typing import Any, Dict, Type, TypeVar
from datetime import datetime, timezone

from sqlmodel import Field, select
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from gsuid_core.utils.database.base_models import BaseIDModel, with_session

T_SteamApiCache = TypeVar("T_SteamApiCache", bound="SteamApiCache")
T_SteamArchivementCache = TypeVar("T_SteamArchivementCache", bound="SteamArchivementCache")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SteamApiCache(BaseIDModel, table=True):
    """Steam接口JSON缓存表（内部表，不注册到控制台）"""
    __table_args__: Dict[str, Any] = {"extend_existing": True}

    appid: str = Field(default=None, index=True, unique=True, title="游戏AppID")
    cache_json: str = Field(default=None, title="接口缓存JSON")
    updated_at: datetime = Field(default_factory=_now, title="更新时间")

    @classmethod
    @with_session
    async def upsert_cache(
        cls: Type[T_SteamApiCache],
        session: AsyncSession,
        appid: str,
        cache_json: str,
    ) -> int:
        """写入/更新缓存。返回 0 表示成功。"""
        stmt = select(cls).where(cls.appid == appid)
        result = await session.execute(stmt)
        existing = result.scalars().first()
        if existing is not None:
            existing.cache_json = cache_json
            existing.updated_at = _now()
            session.add(existing)
        else:
            session.add(cls(appid=appid, cache_json=cache_json, updated_at=_now()))  # type: ignore
        return 0

    @classmethod
    @with_session
    async def get_cache(
        cls: Type[T_SteamApiCache],
        session: AsyncSession,
        appid: str,
    ) -> str | None:
        """获取指定 appid 的缓存 JSON"""
        stmt = select(cls.cache_json).where(cls.appid == appid)
        result = await session.execute(stmt)
        return result.scalars().first()

    @classmethod
    @with_session
    async def delete_cache(
        cls: Type[T_SteamApiCache],
        session: AsyncSession,
        appid: str,
    ) -> int:
        """
        删除指定 appid 的缓存。
        0: 成功
        -1: 未找到匹配记录
        """
        stmt = delete(cls).where(cls.appid == appid)  # type: ignore
        result = await session.execute(stmt)
        if result.rowcount and result.rowcount > 0:  # type: ignore
            return 0
        return -1

    @classmethod
    @with_session
    async def delete_stale(
        cls: Type[T_SteamApiCache],
        session: AsyncSession,
        before: datetime,
    ) -> int:
        """删除 updated_at 早于 before 的所有缓存行，返回删除行数。"""
        stmt = delete(cls).where(cls.updated_at < before)  # type: ignore
        result = await session.execute(stmt)
        return result.rowcount or 0  # type: ignore

    @classmethod
    @with_session
    async def delete_all(
        cls: Type[T_SteamApiCache],
        session: AsyncSession,
    ) -> int:
        """删除全部缓存，返回删除行数。"""
        stmt = delete(cls)  # type: ignore
        result = await session.execute(stmt)
        return result.rowcount or 0  # type: ignore


class SteamArchivementCache(BaseIDModel, table=True):
    """Steam成就Schema缓存表（内部表，不注册到控制台）。
    缓存 GetSchemaForGame 返回的成就定义列表（icon/icongray/displayName/description），
    供 get_archivement_schema 和 get_archivement_img 共享使用。
    """
    __table_args__: Dict[str, Any] = {"extend_existing": True}

    appid: str = Field(default=None, index=True, unique=True, title="游戏AppID")
    cache_json: str = Field(default=None, title="成就Schema缓存JSON")
    updated_at: datetime = Field(default_factory=_now, title="更新时间")

    @classmethod
    @with_session
    async def upsert_cache(
        cls: Type[T_SteamArchivementCache],
        session: AsyncSession,
        appid: str,
        cache_json: str,
    ) -> int:
        """写入/更新成就Schema缓存。返回 0 表示成功。"""
        stmt = select(cls).where(cls.appid == appid)
        result = await session.execute(stmt)
        existing = result.scalars().first()
        if existing is not None:
            existing.cache_json = cache_json
            existing.updated_at = _now()
            session.add(existing)
        else:
            session.add(cls(appid=appid, cache_json=cache_json, updated_at=_now()))  # type: ignore
        return 0

    @classmethod
    @with_session
    async def get_cache(
        cls: Type[T_SteamArchivementCache],
        session: AsyncSession,
        appid: str,
    ) -> str | None:
        """获取指定 appid 的成就Schema缓存 JSON"""
        stmt = select(cls.cache_json).where(cls.appid == appid)
        result = await session.execute(stmt)
        return result.scalars().first()

    @classmethod
    @with_session
    async def delete_cache(
        cls: Type[T_SteamArchivementCache],
        session: AsyncSession,
        appid: str,
    ) -> int:
        """
        删除指定 appid 的成就Schema缓存。
        0: 成功
        -1: 未找到匹配记录
        """
        stmt = delete(cls).where(cls.appid == appid)  # type: ignore
        result = await session.execute(stmt)
        if result.rowcount and result.rowcount > 0:  # type: ignore
            return 0
        return -1

    @classmethod
    @with_session
    async def delete_stale(
        cls: Type[T_SteamArchivementCache],
        session: AsyncSession,
        before: datetime,
    ) -> int:
        """删除 updated_at 早于 before 的所有缓存行，返回删除行数。"""
        stmt = delete(cls).where(cls.updated_at < before)  # type: ignore
        result = await session.execute(stmt)
        return result.rowcount or 0  # type: ignore

    @classmethod
    @with_session
    async def delete_all(
        cls: Type[T_SteamArchivementCache],
        session: AsyncSession,
    ) -> int:
        """删除全部缓存，返回删除行数。"""
        stmt = delete(cls)  # type: ignore
        result = await session.execute(stmt)
        return result.rowcount or 0  # type: ignore
