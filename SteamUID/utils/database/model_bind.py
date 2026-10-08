"""Steam 用户绑定表与全部处理逻辑。"""

from typing import TypeVar, Optional, Sequence

from sqlmodel import Field, col, select
from sqlalchemy import UniqueConstraint, delete, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from gsuid_core.webconsole.mount_app import PageSchema, GsAdminModel, site
from gsuid_core.utils.database.base_models import Bind, with_session

from .model_auth import SteamAuth

T_SteamBind = TypeVar("T_SteamBind", bound="SteamBind")


class SteamBind(Bind, table=True):
    """群内 user 与 steamid64 的绑定，唯一键为会话四元组加 steamid64。"""

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "bot_id",
            "bot_self_id",
            "group_id",
            "steamid64",
            name="uq_steambind_session_steamid",
        ),
        {"extend_existing": True},
    )

    WS_BOT_ID: Optional[str] = Field(default=None, title="WS机器人ID")
    bot_self_id: str = Field(default="", title="机器人自身ID")
    steamid64: str = Field(default="", index=True, title="SteamID64")
    is_main_id: bool = Field(default=False, title="是否主ID")

    @classmethod
    @with_session
    async def upsert_bind(
        cls: type[T_SteamBind],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
        bot_self_id: str,
        group_id: str,
        steamid64: str,
        WS_BOT_ID: Optional[str] = None,
        is_main_id: bool = False,
    ) -> None:
        """写入或刷新绑定；置主ID时先清掉同会话其余主ID。"""
        if is_main_id:
            await session.execute(
                update(cls)
                .where(
                    col(cls.user_id) == user_id,
                    col(cls.bot_id) == bot_id,
                    col(cls.bot_self_id) == bot_self_id,
                    col(cls.group_id) == group_id,
                    col(cls.is_main_id).is_(True),
                )
                .values(is_main_id=False)
            )

        result = await session.execute(
            select(cls).where(
                col(cls.user_id) == user_id,
                col(cls.bot_id) == bot_id,
                col(cls.bot_self_id) == bot_self_id,
                col(cls.group_id) == group_id,
                col(cls.steamid64) == steamid64,
            )
        )
        row = result.scalars().first()
        if row is None:
            session.add(
                cls(
                    user_id=user_id,
                    bot_id=bot_id,
                    bot_self_id=bot_self_id,
                    group_id=group_id,
                    steamid64=steamid64,
                    WS_BOT_ID=WS_BOT_ID,
                    is_main_id=is_main_id,
                )
            )
            return

        row.WS_BOT_ID = WS_BOT_ID
        row.is_main_id = is_main_id
        session.add(row)

    @classmethod
    @with_session
    async def get_binds_by_session(
        cls: type[T_SteamBind],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
        bot_self_id: str,
        group_id: str,
    ) -> list[T_SteamBind]:
        result = await session.execute(
            select(cls).where(
                col(cls.user_id) == user_id,
                col(cls.bot_id) == bot_id,
                col(cls.bot_self_id) == bot_self_id,
                col(cls.group_id) == group_id,
            )
        )
        return list(result.scalars().all())

    @classmethod
    @with_session
    async def get_main_bind(
        cls: type[T_SteamBind],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
        bot_self_id: str,
        group_id: str,
    ) -> Optional[T_SteamBind]:
        result = await session.execute(
            select(cls).where(
                col(cls.user_id) == user_id,
                col(cls.bot_id) == bot_id,
                col(cls.bot_self_id) == bot_self_id,
                col(cls.group_id) == group_id,
                col(cls.is_main_id).is_(True),
            )
        )
        return result.scalars().first()

    @classmethod
    @with_session
    async def set_main_id(
        cls: type[T_SteamBind],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
        bot_self_id: str,
        group_id: str,
        steamid64: str,
    ) -> bool:
        """切换主ID；目标不在该会话的绑定里时返回 False 且不改动。"""
        target = await session.execute(
            select(cls).where(
                col(cls.user_id) == user_id,
                col(cls.bot_id) == bot_id,
                col(cls.bot_self_id) == bot_self_id,
                col(cls.group_id) == group_id,
                col(cls.steamid64) == steamid64,
            )
        )
        if target.scalars().first() is None:
            return False

        scope = (
            col(cls.user_id) == user_id,
            col(cls.bot_id) == bot_id,
            col(cls.bot_self_id) == bot_self_id,
            col(cls.group_id) == group_id,
        )
        await session.execute(
            update(cls).where(*scope, col(cls.is_main_id).is_(True)).values(is_main_id=False)
        )
        await session.execute(
            update(cls).where(*scope, col(cls.steamid64) == steamid64).values(is_main_id=True)
        )
        return True

    @classmethod
    @with_session
    async def get_all_steamids(
        cls: type[T_SteamBind],
        session: AsyncSession,
    ) -> list[str]:
        result = await session.execute(select(col(cls.steamid64)).distinct())
        return list(result.scalars().all())

    @classmethod
    @with_session
    async def get_binds_by_steamids(
        cls: type[T_SteamBind],
        session: AsyncSession,
        steamid64s: Sequence[str],
    ) -> list[T_SteamBind]:
        if not steamid64s:
            return []
        result = await session.execute(
            select(cls).where(col(cls.steamid64).in_(list(steamid64s)))
        )
        return list(result.scalars().all())

    @classmethod
    @with_session
    async def delete_bind(
        cls: type[T_SteamBind],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
        bot_self_id: str,
        group_id: str,
        steamid64: str,
    ) -> int:
        """解绑；该 steamid 再无绑定引用时连带删除登录凭证。"""
        result = await session.execute(
            delete(cls).where(
                col(cls.user_id) == user_id,
                col(cls.bot_id) == bot_id,
                col(cls.bot_self_id) == bot_self_id,
                col(cls.group_id) == group_id,
                col(cls.steamid64) == steamid64,
            )
        )
        remain = await session.execute(
            select(col(cls.id)).where(col(cls.steamid64) == steamid64).limit(1)
        )
        if remain.scalars().first() is None:
            await session.execute(
                delete(SteamAuth).where(col(SteamAuth.steamid64) == steamid64)
            )
        return result.rowcount if isinstance(result, CursorResult) else 0


@site.register_admin
class SteamBindAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(label="Steam绑定管理", icon="fa fa-users")
    model = SteamBind
