"""steam迁移订阅状态：把 1.0 库内的推送开关与任务名迁移到框架订阅。"""

from collections.abc import Sequence

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.subscribe import gs_subscribe
from gsuid_core.utils.database.models import Subscribe

from ..utils.helper.bind import is_subscribed
from ..utils.helper.notify import subscribe_task_name
from ..utils.helper.announce import SUBSCRIBE_TASK as ANNOUNCE_TASK
from ..utils.helper.price_drop import SUBSCRIBE_TASK as PRICE_TASK
from ..utils.database.model_bind import SteamBind, LegacyPushRow

_TAG = "[Steam·订阅迁移]"

# 遗留列 -> 2.0 通知类型；值必须取自 NOTIFY_KINDS
_LEGACY_KIND_BY_COLUMN: dict[str, str] = {
    "push_start_game": "开始游戏",
    "push_end_game": "结束游戏",
    "push_archivement": "获得成就",
}

# 1.0 的降价 / 公告订阅任务名，迁移时整表改写成 2.0 任务名
_LEGACY_PRICE_TASK = "steam商店降价订阅"
_LEGACY_ANNOUNCE_TASK = "订阅steam游戏公告"


def _subscribe_rows(rows: object) -> list[Subscribe]:
    """框架订阅查询无类型标注，这里立刻收窄为 Subscribe。"""
    if not isinstance(rows, Sequence):
        return []
    return [row for row in rows if isinstance(row, Subscribe)]


def _switch_flags(row: LegacyPushRow) -> dict[str, bool]:
    return {
        "push_start_game": row.push_start_game,
        "push_end_game": row.push_end_game,
        "push_archivement": row.push_archivement,
    }


async def _migrate_push_switches(rows: Sequence[LegacyPushRow]) -> int:
    """按遗留开关补订阅，已存在的不重复建立；返回新建条数。"""
    created = 0
    for row in rows:
        flags = _switch_flags(row)
        ev = Event(
            bot_id=row.bot_id,
            bot_self_id=row.bot_self_id,
            user_type=row.user_type,
            group_id=row.group_id,
            user_id=row.user_id,
            WS_BOT_ID=row.WS_BOT_ID,
        )
        for column, kind in _LEGACY_KIND_BY_COLUMN.items():
            if not flags[column]:
                continue
            if await is_subscribed(ev, row.steamid64, kind):
                continue
            await gs_subscribe.add_subscribe("single", subscribe_task_name(kind), ev, uid=row.steamid64)
            created += 1
    return created


async def _rename_task(old_name: str, new_name: str) -> int:
    """旧任务名的订阅整表改写成新任务名；返回影响行数。"""
    rows = _subscribe_rows(await Subscribe.select_rows(task_name=old_name))
    if not rows:
        return 0
    await Subscribe.update_data_by_data({"task_name": old_name}, {"task_name": new_name})
    return len(rows)


async def migrate_subscribe_state(bot: Bot) -> None:
    """全量迁移：补推送订阅，并把降价 / 公告任务名改写成 2.0 名称。"""
    scan = await SteamBind.scan_legacy_push_rows()
    if scan is None:
        raise ValueError("读取旧版订阅数据失败，请稍后重试")

    price_renamed = await _rename_task(_LEGACY_PRICE_TASK, PRICE_TASK)
    announce_renamed = await _rename_task(_LEGACY_ANNOUNCE_TASK, ANNOUNCE_TASK)
    if not scan.has_legacy_columns and not price_renamed and not announce_renamed:
        await bot.send("无旧版本数据，无需迁移")
        return

    created = await _migrate_push_switches(scan.rows) if scan.has_legacy_columns else 0
    logger.info(
        f"{_TAG} 迁移完成: 新建推送订阅 {created} 条 / 跳过 {scan.skipped} 行, "
        f"改写降价 {price_renamed} 条, 改写公告 {announce_renamed} 条"
    )

    lines = ["迁移完成："]
    if scan.has_legacy_columns:
        lines.append(f"新建推送订阅 {created} 条")
        if scan.skipped:
            lines.append(f"跳过异常数据 {scan.skipped} 行")
    lines.append(f"改写降价订阅 {price_renamed} 条")
    lines.append(f"改写公告订阅 {announce_renamed} 条")
    await bot.send("\n".join(lines))
