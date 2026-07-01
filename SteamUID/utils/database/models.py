from typing import Any, Dict, List, Optional, Type, TypeVar, Union

from sqlmodel import Field, select
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from gsuid_core.bot import Bot
from gsuid_core.gss import gss
from gsuid_core.logger import logger
from gsuid_core.models import Event, Message
from gsuid_core.message_models import ButtonType
from gsuid_core.webconsole.mount_app import PageSchema, GsAdminModel, site
from gsuid_core.utils.database.startup import exec_list
from gsuid_core.utils.database.base_models import BaseIDModel, with_session

# 补齐新增列与索引
exec_list.extend(
    [
        # SteamIDInfo 新增列
        "ALTER TABLE steamidinfo ADD COLUMN steamid64 VARCHAR",
        "ALTER TABLE steamidinfo ADD COLUMN steamuserinfo VARCHAR",
        # SteamBind 新增列（表已存在但列不全时补齐，列已存在会被 try/except 忽略）
        'ALTER TABLE steambind ADD COLUMN steamid64 VARCHAR',
        'ALTER TABLE steambind ADD COLUMN bot_id VARCHAR',
        'ALTER TABLE steambind ADD COLUMN user_id VARCHAR',
        'ALTER TABLE steambind ADD COLUMN "WS_BOT_ID" VARCHAR',
        'ALTER TABLE steambind ADD COLUMN group_id VARCHAR',
        'ALTER TABLE steambind ADD COLUMN bot_self_id VARCHAR',
        'ALTER TABLE steambind ADD COLUMN user_type VARCHAR',
        # 推送开关列
        'ALTER TABLE steambind ADD COLUMN push_start_game BOOLEAN DEFAULT 1',
        'ALTER TABLE steambind ADD COLUMN push_end_game BOOLEAN DEFAULT 1',
    ]
)

T_SteamBind = TypeVar("T_SteamBind", bound="SteamBind")
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

    async def send(
        self,
        reply: Optional[
            Union[
                Message,
                List[Message],
                List[str],
                str,
                bytes,
            ]
        ] = None,
        option_list: Optional[ButtonType] = None,
        unsuported_platform: bool = False,
        sep: str = "\n",
        command_tips: str = "请输入以下命令之一:",
        command_start_text: str = "",
        force_direct: bool = False,
    ):
        """复制 Subscribe.send 路由逻辑：优先 WS_BOT_ID，失效时按 bot_id 兜底"""
        user_type = "direct" if force_direct else self.user_type
        ev = Event(
            bot_id=self.bot_id,
            user_id=self.user_id,
            bot_self_id=self.bot_self_id,
            user_type=user_type,  # type: ignore
            group_id=self.group_id,
            real_bot_id=self.bot_id,
            msg_id="",
        )
        params = {
            "reply": reply,
            "option_list": option_list,
            "unsuported_platform": unsuported_platform,
            "sep": sep,
            "command_tips": command_tips,
            "command_start_text": command_start_text,
        }

        if self.WS_BOT_ID:
            if self.WS_BOT_ID in gss.active_bot:
                BOT = gss.active_bot[self.WS_BOT_ID]
                bot = Bot(BOT, ev)
                await bot.send_option(**params)
            else:
                # WS_BOT_ID 失效，按 bot_id 兜底查找活跃 Bot（不回写数据库，简化处理）
                found = False
                for ws_bot_id, _bot in gss.active_bot.items():
                    if _bot.bot_id == self.bot_id:
                        logger.info(
                            f"[SteamBind] WS_BOT_ID {self.WS_BOT_ID} 已失效，临时切换到 {ws_bot_id}"
                        )
                        bot = Bot(_bot, ev)
                        await bot.send_option(**params)
                        found = True
                        break
                if not found:
                    logger.error(
                        f"[SteamBind] 机器人{self.WS_BOT_ID}不存在, 该消息无法发送!"
                    )
                    return -1
        else:
            for bot_id in gss.active_bot:
                BOT = gss.active_bot[bot_id]
                bot = Bot(BOT, ev)
                await bot.send_option(**params)

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
    ) -> int:
        """写入绑定关系（同一 user + steamid 已存在则更新）"""
        stmt = select(cls).where(
            cls.steamid64 == steamid64,
            cls.bot_id == bot_id,
            cls.user_id == user_id,
            cls.user_type == user_type,
        )
        result = await session.execute(stmt)
        existing = result.scalars().first()

        if existing is not None:# 更新绑定不需要修改推送状态
            existing.WS_BOT_ID = WS_BOT_ID
            existing.group_id = group_id
            existing.bot_self_id = bot_self_id
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
                    push_start_game=True,
                    push_end_game=True,
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
    ) -> list["SteamBind"]:
        """按用户查其所有绑定（用于查看命令、解绑查本人订阅）"""
        stmt = select(cls).where(
            cls.bot_id == bot_id,
            cls.user_id == user_id,
            cls.user_type == user_type,
        )
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
    ) -> int:
        """
        0: 成功
        -1: 未找到匹配记录
        """
        stmt = delete(cls).where(  # type: ignore
            cls.steamid64 == steamid64, # type: ignore
            cls.bot_id == bot_id, # type: ignore
            cls.user_id == user_id, # type: ignore
            cls.user_type == user_type, # type: ignore
        )
        result = await session.execute(stmt)
        if result.rowcount and result.rowcount > 0:  # type: ignore
            return 0
        return -1

    PUSH_COLUMNS = {"push_start_game", "push_end_game"}

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


@site.register_admin
class SteamIDInfoAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(
        label="steamid轮询记录",
        icon="fa fa-database",
    )  # type: ignore

    model = SteamIDInfo

@site.register_admin
class SteamBindAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(
        label="steam绑定管理",
        icon="fa fa-database",
    )  # type: ignore

    model = SteamBind
