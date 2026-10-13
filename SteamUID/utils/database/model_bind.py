"""Steam 用户绑定表与全部处理逻辑。"""

from typing import Literal, TypeVar, Optional, Sequence, NamedTuple
from dataclasses import dataclass
from collections.abc import Mapping

from sqlmodel import Field, col, select
from sqlalchemy import UniqueConstraint, text, delete, update, inspect
from sqlalchemy.engine import Connection, CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from gsuid_core.webconsole.mount_app import PageSchema, GsAdminModel, site
from gsuid_core.utils.database.base_models import Bind, with_session

from .model_auth import SteamAuth

T_SteamBind = TypeVar("T_SteamBind", bound="SteamBind")

# 1.0 把推送开关写在这张表里；2.0 已改用框架订阅表，这里只供一次性迁移读取
_LEGACY_TABLE = "steambind"
_LEGACY_REQUIRED_COLUMNS: tuple[str, ...] = (
    "user_id",
    "bot_id",
    "user_type",
    "group_id",
    "steamid64",
    "push_start_game",
    "push_end_game",
    "push_archivement",
)
# 可选列：旧库可能没有，缺列按空值处理，有列但类型异常则整行丢弃
_LEGACY_OPTIONAL_COLUMNS: tuple[str, ...] = ("WS_BOT_ID", "bot_self_id")


@dataclass(frozen=True)
class LegacyPushRow:
    """1.0 遗留 steambind 行，字段全部通过校验后才会构造出来。"""

    user_id: str
    bot_id: str
    bot_self_id: str
    user_type: Literal["group", "direct"]
    group_id: str | None
    steamid64: str
    WS_BOT_ID: str | None
    push_start_game: bool
    push_end_game: bool
    push_archivement: bool


class LegacyPushScan(NamedTuple):
    """一次遗留开关扫描：是否具备 1.0 列、可迁移行、被跳过的异常行数。"""

    has_legacy_columns: bool
    rows: list[LegacyPushRow]
    skipped: int


def _legacy_columns(sync_conn: Connection) -> list[str]:
    """steambind 的实际列名；表不存在时为空。"""
    inspector = inspect(sync_conn)
    if _LEGACY_TABLE not in inspector.get_table_names():
        return []
    names: list[str] = []
    for column in inspector.get_columns(_LEGACY_TABLE):
        name = column["name"]
        if isinstance(name, str):
            names.append(name)
    return names


def _as_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _as_flag(value: object) -> bool | None:
    """SQLite 的 BOOLEAN 落盘为 0/1；非布尔非整型视为异常。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return None


def _optional_text(raw: Mapping[str, object], columns: frozenset[str], key: str) -> tuple[bool, str | None]:
    """可选文本列：未取到列返回 (True, None)，列存在但类型异常返回 (False, None)。"""
    if key not in columns:
        return True, None
    value = raw[key]
    if value is None:
        return True, None
    if isinstance(value, str):
        return True, value
    return False, None


def _to_legacy_row(raw: Mapping[str, object], columns: frozenset[str]) -> LegacyPushRow | None:
    """逐字段校验；任一必需字段异常即整行丢弃。"""
    user_id = _as_text(raw["user_id"])
    bot_id = _as_text(raw["bot_id"])
    steamid64 = _as_text(raw["steamid64"])
    if not user_id or not bot_id or not steamid64:
        return None

    user_type = _as_text(raw["user_type"])
    group_id = _as_text(raw["group_id"])
    if user_type == "group":
        if not group_id:
            return None
    elif user_type == "direct":
        group_id = group_id or None
    else:
        return None

    ws_ok, ws_bot_id = _optional_text(raw, columns, "WS_BOT_ID")
    self_ok, bot_self_id = _optional_text(raw, columns, "bot_self_id")
    if not ws_ok or not self_ok:
        return None

    start = _as_flag(raw["push_start_game"])
    end = _as_flag(raw["push_end_game"])
    achievement = _as_flag(raw["push_archivement"])
    if start is None or end is None or achievement is None:
        return None

    return LegacyPushRow(
        user_id=user_id,
        bot_id=bot_id,
        bot_self_id=bot_self_id or "",
        user_type=user_type,
        group_id=group_id,
        steamid64=steamid64,
        WS_BOT_ID=ws_bot_id,
        push_start_game=start,
        push_end_game=end,
        push_archivement=achievement,
    )


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
    async def get_binds_by_group(
        cls: type[T_SteamBind],
        session: AsyncSession,
        bot_id: str,
        bot_self_id: str,
        group_id: str,
    ) -> list[T_SteamBind]:
        """取该会话内该群的全部绑定。"""
        result = await session.execute(
            select(cls).where(
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
        await session.execute(update(cls).where(*scope, col(cls.is_main_id).is_(True)).values(is_main_id=False))
        await session.execute(update(cls).where(*scope, col(cls.steamid64) == steamid64).values(is_main_id=True))
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
        result = await session.execute(select(cls).where(col(cls.steamid64).in_(list(steamid64s))))
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
        remain = await session.execute(select(col(cls.id)).where(col(cls.steamid64) == steamid64).limit(1))
        if remain.scalars().first() is None:
            await session.execute(delete(SteamAuth).where(col(SteamAuth.steamid64) == steamid64))
        return result.rowcount if isinstance(result, CursorResult) else 0

    @classmethod
    @with_session
    async def scan_legacy_push_rows(
        cls: type[T_SteamBind],
        session: AsyncSession,
    ) -> LegacyPushScan | None:
        """扫描 1.0 遗留推送开关；数据库异常时返回 None 交命令层提示。"""
        conn = await session.connection()
        existing = set(await conn.run_sync(_legacy_columns))
        if not set(_LEGACY_REQUIRED_COLUMNS) <= existing:
            return LegacyPushScan(has_legacy_columns=False, rows=[], skipped=0)

        ordered = (*_LEGACY_REQUIRED_COLUMNS, *_LEGACY_OPTIONAL_COLUMNS)
        columns = frozenset(name for name in ordered if name in existing)
        result = await session.execute(text(f"SELECT * FROM {_LEGACY_TABLE}"))
        rows: list[LegacyPushRow] = []
        skipped = 0
        for raw in result.mappings():
            row = _to_legacy_row(dict(raw), columns)
            if row is None:
                skipped += 1
            else:
                rows.append(row)
        return LegacyPushScan(has_legacy_columns=True, rows=rows, skipped=skipped)


@site.register_admin
class SteamBindAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(label="Steam绑定管理", icon="fa fa-users")
    model = SteamBind
