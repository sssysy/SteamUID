class SteamAPI:
    # 获取玩家摘要信息
    api_GetPlayerSummaries = "/ISteamUser/GetPlayerSummaries/v2/"

    # 获取玩家成就列表
    api_GetPlayerAchievements = "/ISteamUserStats/GetPlayerAchievements/v1/"

    #  获取游戏成就 Schema
    api_GetSchemaForGame = "/ISteamUserStats/GetSchemaForGame/v2/"

    #  获取全球成就解锁率
    api_GetGlobalAchievementPercentagesForApp = "/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v2/"

    # 获取玩家拥有的游戏
    api_GetOwnedGames = "/IPlayerService/GetOwnedGames/v1/"

    # 获取游戏当前在线人数
    api_GetNumberOfCurrentPlayers = "/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"

    # 获取游戏详情
    store_GetGameDetails = "/api/appdetails"
