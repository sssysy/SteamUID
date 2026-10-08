"""Steam 登录凭证表与全部处理逻辑。"""

from typing import TypeVar, Optional

from sqlmodel import Field, col, select
from sqlalchemy import UniqueConstraint, delete
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from gsuid_core.webconsole.mount_app import PageSchema, GsAdminModel, site
from gsuid_core.utils.database.base_models import BaseIDModel, with_session

T_SteamAuth = TypeVar("T_SteamAuth", bound="SteamAuth")


class SteamAuth(BaseIDModel, table=True):
    """Steam WebAuth 授权凭据，一个 steamid64 一行。"""

    __table_args__ = (
        UniqueConstraint("steamid64", name="uq_steamauth_steamid64"),
        {"extend_existing": True},
    )

    steamid64: str = Field(default="", index=True, title="SteamID64")
    account_name: str = Field(default="", title="Steam用户名")
    access_token: str = Field(default="", title="Access Token")
    refresh_token: str = Field(default="", title="Refresh Token")
    session_id: str = Field(default="", title="Session ID")
    cookies_json: str = Field(default="", title="Cookie字典JSON")
    updated_at: int = Field(default=0, title="凭据更新时间戳")

    @classmethod
    @with_session
    async def upsert_account(
        cls: type[T_SteamAuth],
        session: AsyncSession,
        steamid64: str,
        account_name: str = "",
        access_token: str = "",
        refresh_token: str = "",
        session_id: str = "",
        cookies_json: str = "",
        updated_at: int = 0,
    ) -> None:
        """整行覆盖写入凭据；登录回传的字段一次性落库。"""
        result = await session.execute(
            select(cls).where(col(cls.steamid64) == steamid64)
        )
        row = result.scalars().first()
        if row is None:
            session.add(
                cls(
                    steamid64=steamid64,
                    account_name=account_name,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    session_id=session_id,
                    cookies_json=cookies_json,
                    updated_at=updated_at,
                )
            )
            return

        row.account_name = account_name
        row.access_token = access_token
        row.refresh_token = refresh_token
        row.session_id = session_id
        row.cookies_json = cookies_json
        row.updated_at = updated_at
        session.add(row)

    @classmethod
    @with_session
    async def get_account(
        cls: type[T_SteamAuth],
        session: AsyncSession,
        steamid64: str,
    ) -> Optional[T_SteamAuth]:
        result = await session.execute(
            select(cls).where(col(cls.steamid64) == steamid64)
        )
        return result.scalars().first()

    @classmethod
    @with_session
    async def get_all_accounts(
        cls: type[T_SteamAuth],
        session: AsyncSession,
    ) -> list[T_SteamAuth]:
        result = await session.execute(select(cls))
        return list(result.scalars().all())

    @classmethod
    @with_session
    async def delete_account(
        cls: type[T_SteamAuth],
        session: AsyncSession,
        steamid64: str,
    ) -> int:
        result = await session.execute(
            delete(cls).where(col(cls.steamid64) == steamid64)
        )
        return result.rowcount if isinstance(result, CursorResult) else 0


@site.register_admin
class SteamAuthAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(label="Steam登录凭证", icon="fa fa-key")
    model = SteamAuth
