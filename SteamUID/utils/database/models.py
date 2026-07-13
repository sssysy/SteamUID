from typing import Any, ClassVar, Dict, Optional, Set, Type, TypeVar

from sqlmodel import Field, select
from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncSession

from gsuid_core.utils.database.base_models import BaseIDModel, with_session

from . import migrations

T_SteamBind = TypeVar("T_SteamBind", bound="SteamBind")
T_SteamIDInfo = TypeVar("T_SteamIDInfo", bound="SteamIDInfo")
T_SteamArchivementInfo = TypeVar("T_SteamArchivementInfo", bound="SteamArchivementInfo")
T_SteamPriceInfo = TypeVar("T_SteamPriceInfo", bound="SteamPriceInfo")
T_SteamPlayRecord = TypeVar("T_SteamPlayRecord", bound="SteamPlayRecord")

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

class SteamPriceInfo(BaseIDModel, table=True):
    """Steam降价订阅表：记录需要轮询价格的 appid 及其最新价格数据"""
    __table_args__: Dict[str, Any] = {"extend_existing": True}

    appid: str = Field(default=None, index=True, unique=True, title="游戏AppID")
    price_data: str = Field(default=None, title="价格数据JSON")

    @classmethod
    @with_session
    async def subscribe(
        cls: Type[T_SteamPriceInfo],
        session: AsyncSession,
        appid: str,
        price_data: str = "{}",
    ) -> int:
        """订阅降价：若已存在则更新价格数据，否则新增。返回 0 表示成功。"""
        stmt = select(cls).where(cls.appid == appid)
        result = await session.execute(stmt)
        existing = result.scalars().first()
        if existing is not None:
            existing.price_data = price_data
            session.add(existing)
        else:
            session.add(cls(appid=appid, price_data=price_data))  # type: ignore
        return 0

    @classmethod
    @with_session
    async def unsubscribe(
        cls: Type[T_SteamPriceInfo],
        session: AsyncSession,
        appid: str,
    ) -> int:
        """取消降价订阅。0: 成功, -1: 未找到"""
        stmt = delete(cls).where(cls.appid == appid)  # type: ignore
        result = await session.execute(stmt)
        if result.rowcount and result.rowcount > 0:  # type: ignore
            return 0
        return -1

    @classmethod
    @with_session
    async def is_subscribed(
        cls: Type[T_SteamPriceInfo],
        session: AsyncSession,
        appid: str,
    ) -> bool:
        """检查某 appid 是否已被订阅"""
        stmt = select(cls.id).where(cls.appid == appid)
        result = await session.execute(stmt)
        return result.scalars().first() is not None

    @classmethod
    @with_session
    async def get_price_data(
        cls: Type[T_SteamPriceInfo],
        session: AsyncSession,
        appid: str,
    ) -> str | None:
        """获取指定 appid 的价格数据 JSON"""
        stmt = select(cls.price_data).where(cls.appid == appid)
        result = await session.execute(stmt)
        return result.scalars().first()

    @classmethod
    @with_session
    async def update_price_data(
        cls: Type[T_SteamPriceInfo],
        session: AsyncSession,
        appid: str,
        price_data: str,
    ) -> int:
        """更新指定 appid 的价格数据。0: 成功, -1: 未找到"""
        stmt = select(cls).where(cls.appid == appid)
        result = await session.execute(stmt)
        existing = result.scalars().first()
        if existing is None:
            return -1
        existing.price_data = price_data
        session.add(existing)
        return 0

    @classmethod
    @with_session
    async def get_all_appids(
        cls: Type[T_SteamPriceInfo],
        session: AsyncSession,
    ) -> list[str]:
        """获取所有已订阅的 appid 列表（供定时任务轮询使用）"""
        stmt = select(cls.appid)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    @with_session
    async def get_all_price_subs(
        cls: Type[T_SteamPriceInfo],
        session: AsyncSession,
    ) -> list["SteamPriceInfo"]:
        """获取所有订阅记录（含价格数据）"""
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
    async def get_binds_by_group(
        cls: Type[T_SteamBind],
        session: AsyncSession,
        group_id: str,
    ) -> list["SteamBind"]:
        """按群查所有绑定（用于排行榜：群 → steamid列表 → user_id映射）"""
        stmt = select(cls).where(cls.group_id == group_id)
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


class SteamPlayRecord(BaseIDModel, table=True):
    """Steam游戏游玩记录表（用于游戏排行榜及衍生功能）"""
    __table_args__: Dict[str, Any] = {"extend_existing": True}

    steamid64: str = Field(default=None, index=True, title="SteamID64")
    appid: str = Field(default=None, index=True, title="游戏AppID")
    start_ts: int = Field(default=None, title="开始游戏时间(Unix时间戳)")
    end_ts: Optional[int] = Field(default=None, title="结束游戏时间(Unix时间戳,NULL=进行中)")

    @classmethod
    @with_session
    async def upsert_record(
        cls: Type[T_SteamPlayRecord],
        session: AsyncSession,
        steamid64: str,
        appid: str,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
    ) -> int:
        """
        写入游玩记录（upsert）。
        - 不传 end_ts（开始游戏）：新增一条记录，start_ts 必填。
        - 传了 end_ts（结束游戏）：按 steamid64 + appid + end_ts IS NULL
          定位进行中的记录并写入 end_ts，start_ts 此时忽略。
        一个玩家同一时间在同一个 appid 只会有一条 end_ts 为 NULL 的记录，
        因此该定位方式不会产生歧义。
        返回 0 表示成功，-1 表示结束游戏时未找到进行中的记录。
        """
        if end_ts is None:
            session.add(
                cls(
                    steamid64=steamid64,  # type: ignore
                    appid=appid,  # type: ignore
                    start_ts=start_ts,  # type: ignore
                    end_ts=None,  # type: ignore
                )
            )
            return 0

        # 结束游戏：查找进行中的记录
        stmt = (
            select(cls)
            .where(
                cls.steamid64 == steamid64,
                cls.appid == appid,
                cls.end_ts.is_(None),  # type: ignore
            )
            .order_by(cls.id.desc())  # type: ignore
        )
        result = await session.execute(stmt)
        existing = result.scalars().first()
        if existing is None:
            return -1
        existing.end_ts = end_ts
        session.add(existing)
        return 0

    @classmethod
    @with_session
    async def delete_record(
        cls: Type[T_SteamPlayRecord],
        session: AsyncSession,
        record_id: int,
    ) -> int:
        """
        按主键删除一条游玩记录。
        0: 成功
        -1: 未找到匹配记录
        """
        stmt = delete(cls).where(cls.id == record_id)  # type: ignore
        result = await session.execute(stmt)
        if result.rowcount and result.rowcount > 0:  # type: ignore
            return 0
        return -1

    @classmethod
    @with_session
    async def get_records(
        cls: Type[T_SteamPlayRecord],
        session: AsyncSession,
        steamid64: Optional[str] = None,
        appid: Optional[str] = None,
        end_before: Optional[int] = None,
        end_after: Optional[int] = None,
    ) -> list["SteamPlayRecord"]:
        """
        按条件查询游玩记录列表。所有参数可选，传入的条件以 AND 组合。
        steamid64 / appid 精确匹配；end_before / end_after 对 end_ts 做范围过滤（含边界）。
        end_ts 为 NULL 的记录不会出现在按时间范围过滤的结果中。
        """
        stmt = select(cls)
        if steamid64 is not None:
            stmt = stmt.where(cls.steamid64 == steamid64)
        if appid is not None:
            stmt = stmt.where(cls.appid == appid)
        if end_before is not None:
            stmt = stmt.where(cls.end_ts <= end_before)  # type: ignore
        if end_after is not None:
            stmt = stmt.where(cls.end_ts >= end_after)  # type: ignore
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    @with_session
    async def get_records_by_steamids(
        cls: Type[T_SteamPlayRecord],
        session: AsyncSession,
        steamid64s: list[str],
    ) -> list["SteamPlayRecord"]:
        """按 steamid64 列表批量查询已结束的游玩记录（end_ts 为 NULL 的进行中记录不返回）"""
        if not steamid64s:
            return []
        stmt = select(cls).where(
            cls.steamid64.in_(steamid64s),  # type: ignore
            cls.end_ts.is_not(None),  # type: ignore
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


from . import admin # 注册到管理员
