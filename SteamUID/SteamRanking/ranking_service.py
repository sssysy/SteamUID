from ..utils.exceptions import SteamError
from ..utils.database.models import SteamBind, SteamPlayRecord
from ..utils.api import get_game_info


async def get_group_ranking_list(group_id: str) -> list[dict]:
    """获取群排名列表"""
    # 第1步：取群绑定列表，构建映射
    binds = await SteamBind.get_binds_by_group(group_id)
    if not binds:
        return []

    steamid_to_user: dict[str, str] = {}
    user_steamids: dict[str, list[str]] = {}
    all_steamids: list[str] = []

    for bind in binds:
        sid = bind.steamid64
        uid = bind.user_id
        steamid_to_user[sid] = uid
        all_steamids.append(sid)
        if uid not in user_steamids:
            user_steamids[uid] = []
        if sid not in user_steamids[uid]:
            user_steamids[uid].append(sid)

    # 第2步：批量查询已结束的游玩记录
    # with_session 重试耗尽后会隐式返回 None（区别于空列表的正常业务结果）
    records = await SteamPlayRecord.get_records_by_steamids(all_steamids)
    if records is None:
        raise SteamError("查询游玩记录失败，请稍后重试")

    # 第3步：计算时长并按 user_id 累加
    user_durations: dict[str, int] = {}
    for record in records:
        uid = steamid_to_user.get(record.steamid64)
        if uid is None:
            continue
        duration = record.end_ts - record.start_ts  # type: ignore
        user_durations[uid] = user_durations.get(uid, 0) + duration

    # 第4步：构建结果列表并按总时长降序排序
    ranking_list = [
        {
            "user_id": uid,
            "total_duration": duration,
            "steamid64s": user_steamids.get(uid, []),
        }
        for uid, duration in user_durations.items()
    ]
    ranking_list.sort(key=lambda x: x["total_duration"], reverse=True)

    return ranking_list


async def get_game_ranking_list(group_id: str) -> list[dict]:
    """获取群内游戏排行列表（按游戏总时长降序，不区分用户）"""
    # 第1步：取群绑定列表，收集所有 steamid64
    binds = await SteamBind.get_binds_by_group(group_id)
    if not binds:
        return []

    all_steamids: list[str] = []
    seen: set[str] = set()
    for bind in binds:
        sid = bind.steamid64
        if sid not in seen:
            seen.add(sid)
            all_steamids.append(sid)

    # 第2步：批量查询已结束的游玩记录
    records = await SteamPlayRecord.get_records_by_steamids(all_steamids)
    if records is None:
        raise SteamError("查询游玩记录失败，请稍后重试")

    # 第3步：按 appid 累加时长，不区分用户
    app_durations: dict[str, int] = {}
    for record in records:
        duration = record.end_ts - record.start_ts  # type: ignore
        app_durations[record.appid] = app_durations.get(record.appid, 0) + duration

    # 第4步：按总时长降序排序
    sorted_apps = sorted(app_durations.items(), key=lambda x: x[1], reverse=True)

    # 第5步：获取游戏名称
    ranking_list: list[dict] = []
    for appid, total_duration in sorted_apps:
        game_name = appid
        try:
            info = await get_game_info(appid)
            if info and info.get("success"):
                name = info.get("data", {}).get("name", "")
                if name:
                    game_name = name
        except Exception:
            pass
        ranking_list.append({
            "appid": appid,
            "game_name": game_name,
            "total_duration": total_duration,
        })

    return ranking_list
