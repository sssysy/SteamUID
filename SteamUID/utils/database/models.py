from typing import Any, ClassVar, Dict, Optional, Set, Type, TypeVar

from sqlmodel import Field, select
from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncSession

from gsuid_core.utils.database.base_models import BaseIDModel, with_session

from . import migrations

T_SteamBind = TypeVar("T_SteamBind", bound="SteamBind")
T_SteamIDInfo = TypeVar("T_SteamIDInfo", bound="SteamIDInfo")
T_SteamArchivementInfo = TypeVar("T_SteamArchivementInfo", bound="SteamArchivementInfo")

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
                    steamid64=steamid64, # type: ignore
                    steamuserinfo=steamuserinfo, # type: ignore
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

class SteamArchivementInfo(BaseIDModel, table=True):
    __table_args__: Dict[str, Any] = {"extend_existing": True}

    steamid64: str = Field(default=None, index=True, unique=True, title="SteamID64")
    appid: str = Field(default=None, index=True, title="游戏中AppID")
    archivement_data: str = Field(default=None, title="成就数据JSON")

    @classmethod
    @with_session
    async def upsert_archivement_data(
        cls: Type[T_SteamArchivementInfo],
        session: AsyncSession,
        steamid64: str,
        appid: str,
        archivement_data: str,
    ) -> int:
        stmt = (
            insert(cls)
            .prefix_with("OR REPLACE")
            .values(
                steamid64=steamid64,
                appid=appid,
                archivement_data=archivement_data,
            )
        )
        await session.execute(stmt)
        return 0

    @classmethod
    @with_session
    async def get_archivement_data(
        cls: Type[T_SteamArchivementInfo],
        session: AsyncSession,
        steamid64: str,
    ) -> str | None:
        stmt = select(cls.archivement_data).where(cls.steamid64 == steamid64)
        result = await session.execute(stmt)
        return result.scalars().first()

    @classmethod
    @with_session
    async def delete_archivement_data(
        cls: Type[T_SteamArchivementInfo],
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
        cls: Type[T_SteamArchivementInfo],
        session: AsyncSession,
    ) -> list[str]:
        stmt = select(cls.steamid64)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    @with_session
    async def get_all_archivement_info(
        cls: Type[T_SteamArchivementInfo],
        session: AsyncSession,
    ) -> list["SteamArchivementInfo"]:
        stmt = select(cls)
        result = await session.execute(stmt)
        return list(result.scalars().all())

class SteamBind(BaseIDModel, table=True):
    """从subscribe表独立出来"""
    __table_args__: Dict[str, Any] = {"extend_existing": True}

    steamid64: str = Field(default=None, index=True, title="SteamID64")
    bot_id: str = Field(default=None, title="平台")
    user_id: str = Field(default=None, index=True, title="用户ID")
    WS_BOT_ID: Optional[str] = Field(default=None, title="WS机器人ID")
    group_id: Optional[str] = Field(default=None, title="群ID")
    bot_self_id: Optional[str] = Field(default=None, title="机器人自身ID")
    user_type: str = Field(default=None, title="发送类型")
    push_start_game: bool = Field(default=True, title="推送开始游戏")
    push_end_game: bool = Field(default=True, title="推送结束游戏")
    push_archivement: bool = Field(default=True, title="推送成就")
    is_main_id: bool = Field(default=False, title="是否主ID")

    async def send(self, reply=None, **kwargs):
        """薄委托，路由逻辑见 push_sender.send_to_bind"""
        from ..sender import send_to_bind
        return await send_to_bind(self, reply, **kwargs)

    @classmethod
    @with_session
    async def upsert_bind(
        cls: Type[T_SteamBind],
        session: AsyncSession,
        steamid64: str,
        bot_id: str,
        user_id: str,
        user_type: str,
        WS_BOT_ID: Optional[str] = None,
        group_id: Optional[str] = None,
        bot_self_id: Optional[str] = None,
        is_main_id: bool = False,
        push_start_game: bool = True,
        push_end_game: bool = True,
        push_archivement: bool = True,
    ) -> int:
        """写入绑定关系（同一 user + steamid 已存在则更新）"""
        # 设置主ID前，先将该用户在同群绑定的 is_main_id 清零
        if is_main_id:
            user_stmt = select(cls).where(
                cls.bot_id == bot_id,
                cls.user_id == user_id,
                cls.user_type == user_type,
                cls.group_id == group_id,
            )
            user_result = await session.execute(user_stmt)
            for row in user_result.scalars().all():
                row.is_main_id = False
                session.add(row)

        stmt = select(cls).where(
            cls.steamid64 == steamid64,
            cls.bot_id == bot_id,
            cls.user_id == user_id,
            cls.user_type == user_type,
            cls.group_id == group_id
        )
        result = await session.execute(stmt)
        existing = result.scalars().first()

        if existing is not None:
            # 更新绑定不修改推送状态
            existing.WS_BOT_ID = WS_BOT_ID
            existing.bot_self_id = bot_self_id
            existing.is_main_id = is_main_id
            session.add(existing)
        else:
            session.add(
                cls(
                    steamid64=steamid64,
                    bot_id=bot_id,
                    user_id=user_id,
                    user_type=user_type,
                    WS_BOT_ID=WS_BOT_ID,
                    group_id=group_id,
                    bot_self_id=bot_self_id,
                    push_start_game=push_start_game,
                    push_end_game=push_end_game,
                    push_archivement=push_archivement,
                    is_main_id=is_main_id,
                )
            )
        return 0

    @classmethod
    @with_session
    async def get_bind_by_steamid(
        cls: Type[T_SteamBind],
        session: AsyncSession,
        steamid64: str,
    ) -> list["SteamBind"]:
        """按 steamid 反查所有绑定者（用于"一个steamid只能绑一个用户"校验 + 推送反查）"""
        stmt = select(cls).where(cls.steamid64 == steamid64)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    @with_session
    async def get_binds_by_user(
        cls: Type[T_SteamBind],
        session: AsyncSession,
        bot_id: str,
        user_id: str,
        user_type: str,
        group_id: Optional[str] = None,
    ) -> list["SteamBind"]:
        """按用户查其所有绑定（用于查看命令、解绑查本人订阅）"""
        where_list = [
            cls.bot_id == bot_id,
            cls.user_id == user_id,
            cls.user_type == user_type,
        ]
        if group_id is not None:
            where_list.append(cls.group_id == group_id)
        stmt = select(cls).where(*where_list)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    @with_session
    async def delete_bind(
        cls: Type[T_SteamBind],
        session: AsyncSession,
        steamid64: str,
        bot_id: str,
        user_id: str,
        user_type: str,
        group_id: Optional[str] = None,
    ) -> int:
        """
        0: 成功
        -1: 未找到匹配记录
        """
        # 先查询被删记录，判断是否为主ID
        check_stmt = select(cls).where(
            cls.steamid64 == steamid64,
            cls.bot_id == bot_id,
            cls.user_id == user_id,
            cls.user_type == user_type,
            cls.group_id == group_id,
        )
        check_result = await session.execute(check_stmt)
        target = check_result.scalars().first()
        was_main = target is not None and target.is_main_id

        stmt = delete(cls).where(  # type: ignore
            cls.steamid64 == steamid64, # type: ignore
            cls.bot_id == bot_id, # type: ignore
            cls.user_id == user_id, # type: ignore
            cls.user_type == user_type, # type: ignore
            cls.group_id == group_id # type: ignore
        )
        result = await session.execute(stmt)
        if result.rowcount and result.rowcount > 0:  # type: ignore
            # 删除的是主ID时，自动提升本群最近绑定的ID为主ID
            if was_main:
                next_stmt = select(cls).where(
                    cls.bot_id == bot_id,
                    cls.user_id == user_id,
                    cls.user_type == user_type,
                    cls.group_id == group_id,
                ).order_by(cls.id.desc())  # type: ignore
                next_result = await session.execute(next_stmt)
                next_bind = next_result.scalars().first()
                if next_bind is not None:
                    next_bind.is_main_id = True
                    session.add(next_bind)
            return 0
        return -1

    PUSH_COLUMNS: ClassVar[Set[str]] = {"push_start_game", "push_end_game", "push_archivement"}

    @classmethod
    @with_session
    async def get_all_archivement_push_binds(
        cls: Type[T_SteamBind],
        session: AsyncSession,
    ) -> list["SteamBind"]:
        """获取所有开启了成就推送的绑定（按 steamid64 去重）"""
        stmt = select(cls).where(cls.push_archivement == True)  # noqa: E712
        result = await session.execute(stmt)
        binds = result.scalars().all()
        seen = set()
        unique: list["SteamBind"] = []
        for b in binds:
            if b.steamid64 not in seen:
                seen.add(b.steamid64)
                unique.append(b)
        return unique

    @classmethod
    @with_session
    async def set_push_status(
        cls: Type[T_SteamBind],
        session: AsyncSession,
        steamid64: str,
        bot_id: str,
        user_id: str,
        user_type: str,
        push_column: str,
        enabled: bool,
        group_id: Optional[str] = None,
    ) -> int:
        """
        设置某个推送开关。
        0: 成功
        -1: 未找到绑定
        -2: 非法列名
        """
        if push_column not in cls.PUSH_COLUMNS:
            return -2
        stmt = select(cls).where(
            cls.steamid64 == steamid64,
            cls.bot_id == bot_id,
            cls.user_id == user_id,
            cls.user_type == user_type,
            cls.group_id == group_id,
        )
        result = await session.execute(stmt)
        existing = result.scalars().first()
        if existing is None:
            return -1
        setattr(existing, push_column, enabled)
        session.add(existing)
        return 0

    @classmethod
    @with_session
    async def get_push_status(
        cls: Type[T_SteamBind],
        session: AsyncSession,
        steamid64: str,
        bot_id: str,
        user_id: str,
        user_type: str,
        push_column: str,
    ) -> Optional[bool]:
        """
        查询某个绑定记录的某个推送状态。
        None未找到。
        """
        if push_column not in cls.PUSH_COLUMNS:
            return None
        stmt = select(getattr(cls, push_column)).where(
            cls.steamid64 == steamid64,
            cls.bot_id == bot_id,
            cls.user_id == user_id,
            cls.user_type == user_type,
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    @classmethod
    @with_session
    async def set_main_id(
        cls: Type[T_SteamBind],
        session: AsyncSession,
        steamid64: str,
        bot_id: str,
        user_id: str,
        user_type: str,
        group_id: Optional[str] = None,
    ) -> int:
        """
        设置主ID：先清零该用户在【同群】绑定的 is_main_id，再将指定绑定设为 True。
        0: 成功
        -1: 未找到指定绑定
        """
        # 先清零该用户在同群的所有 is_main_id
        user_stmt = select(cls).where(
            cls.bot_id == bot_id,
            cls.user_id == user_id,
            cls.user_type == user_type,
            cls.group_id == group_id,
        )
        user_result = await session.execute(user_stmt)
        for row in user_result.scalars().all():
            row.is_main_id = False
            session.add(row)

        # 将指定绑定设为主ID
        stmt = select(cls).where(
            cls.steamid64 == steamid64,
            cls.bot_id == bot_id,
            cls.user_id == user_id,
            cls.user_type == user_type,
            cls.group_id == group_id,
        )
        result = await session.execute(stmt)
        existing = result.scalars().first()
        if existing is None:
            return -1
        existing.is_main_id = True
        session.add(existing)
        return 0

    @classmethod
    @with_session
    async def get_main_id(
        cls: Type[T_SteamBind],
        session: AsyncSession,
        bot_id: str,
        user_id: str,
        user_type: str,
        group_id: Optional[str] = None,
    ) -> Optional[str]:
        """获取该用户在指定群的主ID(steamid64)，不存在则返回 None。"""
        stmt = select(cls.steamid64).where(
            cls.bot_id == bot_id,
            cls.user_id == user_id,
            cls.user_type == user_type,
            cls.is_main_id == True,  # noqa: E712
            cls.group_id == group_id,
        )
        result = await session.execute(stmt)
        return result.scalars().first()


from . import admin  # noqa: F401, E402
