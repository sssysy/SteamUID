"""Steam 游玩历史表与全部处理逻辑。"""

from typing import TypeVar, Optional, Sequence

from sqlmodel import Field, col, select
from sqlalchemy import delete, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from gsuid_core.webconsole.mount_app import PageSchema, GsAdminModel, site
from gsuid_core.utils.database.base_models import BaseIDModel, with_session

T_SteamPlayRecord = TypeVar("T_SteamPlayRecord", bound="SteamPlayRecord")


class SteamPlayRecord(BaseIDModel, table=True):
    """一次游玩会话；end_ts 为空表示仍在进行中。"""

    steamid64: str = Field(default="", index=True, title="SteamID64")
    appid: str = Field(default="", index=True, title="游戏AppID")
    start_ts: int = Field(default=0, title="开始游戏时间戳")
    end_ts: Optional[int] = Field(default=None, index=True, title="结束游戏时间戳")

    @classmethod
    @with_session
    async def start_record(
        cls: type[T_SteamPlayRecord],
        session: AsyncSession,
        steamid64: str,
        appid: str,
        start_ts: int,
    ) -> None:
        session.add(cls(steamid64=steamid64, appid=appid, start_ts=start_ts))

    @classmethod
    @with_session
    async def end_record(
        cls: type[T_SteamPlayRecord],
        session: AsyncSession,
        steamid64: str,
        appid: str,
        end_ts: int,
    ) -> int:
        """收尾该账号该游戏全部进行中的记录，返回收尾条数。"""
        result = await session.execute(
            update(cls)
            .where(
                col(cls.steamid64) == steamid64,
                col(cls.appid) == appid,
                col(cls.end_ts).is_(None),
            )
            .values(end_ts=end_ts)
        )
        return result.rowcount if isinstance(result, CursorResult) else 0

    @classmethod
    @with_session
    async def get_open_record(
        cls: type[T_SteamPlayRecord],
        session: AsyncSession,
        steamid64: str,
        appid: str,
    ) -> Optional[T_SteamPlayRecord]:
        result = await session.execute(
            select(cls).where(
                col(cls.steamid64) == steamid64,
                col(cls.appid) == appid,
                col(cls.end_ts).is_(None),
            )
        )
        return result.scalars().first()

    @classmethod
    @with_session
    async def get_records(
        cls: type[T_SteamPlayRecord],
        session: AsyncSession,
        steamid64: Optional[str] = None,
        appid: Optional[str] = None,
        end_after: Optional[int] = None,
        end_before: Optional[int] = None,
    ) -> list[T_SteamPlayRecord]:
        """按账号、游戏、结束时间区间过滤；未结束的记录不会命中时间区间条件。"""
        stmt = select(cls)
        if steamid64 is not None:
            stmt = stmt.where(col(cls.steamid64) == steamid64)
        if appid is not None:
            stmt = stmt.where(col(cls.appid) == appid)
        if end_after is not None:
            stmt = stmt.where(col(cls.end_ts) >= end_after)
        if end_before is not None:
            stmt = stmt.where(col(cls.end_ts) <= end_before)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    @with_session
    async def get_records_by_steamids(
        cls: type[T_SteamPlayRecord],
        session: AsyncSession,
        steamid64s: Sequence[str],
    ) -> list[T_SteamPlayRecord]:
        if not steamid64s:
            return []
        result = await session.execute(
            select(cls).where(
                col(cls.steamid64).in_(list(steamid64s)),
                col(cls.end_ts).is_not(None),
            )
        )
        return list(result.scalars().all())

    @classmethod
    @with_session
    async def delete_by_steamid(
        cls: type[T_SteamPlayRecord],
        session: AsyncSession,
        steamid64: str,
    ) -> int:
        result = await session.execute(
            delete(cls).where(col(cls.steamid64) == steamid64)
        )
        return result.rowcount if isinstance(result, CursorResult) else 0


@site.register_admin
class SteamPlayRecordAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(label="Steam游玩记录", icon="fa fa-gamepad")
    model = SteamPlayRecord
