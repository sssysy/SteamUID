from typing import Any, Dict, Type, TypeVar

from sqlmodel import Field, select
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from gsuid_core.webconsole.mount_app import PageSchema, GsAdminModel, site
from gsuid_core.utils.database.startup import exec_list
from gsuid_core.utils.database.base_models import BaseIDModel, with_session

# 老库兼容：补齐新增列与索引（启动时自动执行）
exec_list.extend(
    [
        # SteamIDInfo 新增列
        "ALTER TABLE steamidinfo ADD COLUMN steamid64 VARCHAR",
        "ALTER TABLE steamidinfo ADD COLUMN steamuserinfo VARCHAR",
    ]
)

T_SteamIDInfo = TypeVar("T_SteamIDInfo", bound="SteamIDInfo")


class SteamIDInfo(BaseIDModel, table=True):
    __table_args__: Dict[str, Any] = {"extend_existing": True}

    steamid64: str = Field(default=None, index=True, title="SteamID64")
    steamuserinfo: str = Field(default=None, title="Steam用户信息JSON")

    @classmethod
    @with_session
    async def upsert_steamuserinfo(
        cls: Type[T_SteamIDInfo],
        session: AsyncSession,
        steamid64: str,
        steamuserinfo: str,
    ) -> int:
        stmt = select(cls).where(cls.steamid64 == steamid64)
        result = await session.execute(stmt)
        existing = result.scalars().first()

        if existing is not None:
            existing.steamuserinfo = steamuserinfo
            session.add(existing)
        else:
            session.add(
                cls(
                    steamid64=steamid64,
                    steamuserinfo=steamuserinfo,
                )
            )
        return 0

    @classmethod
    @with_session
    async def get_steamuserinfo(
        cls: Type[T_SteamIDInfo],
        session: AsyncSession,
        steamid64: str,
    ) -> str | None:
        stmt = select(cls.steamuserinfo).where(cls.steamid64 == steamid64)
        result = await session.execute(stmt)
        return result.scalars().first()

    @classmethod
    @with_session
    async def delete_steamuserinfo(
        cls: Type[T_SteamIDInfo],
        session: AsyncSession,
        steamid64: str,
    ) -> int:
        """
        0: 成功
        -1: 未找到匹配记录
        """
        stmt = delete(cls).where(cls.steamid64 == steamid64) # type: ignore
        result = await session.execute(stmt)
        if result.rowcount and result.rowcount > 0: # type: ignore
            return 0
        return -1

    @classmethod
    @with_session
    async def get_all_steamid64(
        cls: Type[T_SteamIDInfo],
        session: AsyncSession,
    ) -> list[str]:
        stmt = select(cls.steamid64)
        result = await session.execute(stmt)
        return list(result.scalars().all())


@site.register_admin
class SteamIDInfoAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(
        label="steamid轮询记录",
        icon="fa fa-database",
    )  # type: ignore

    model = SteamIDInfo
