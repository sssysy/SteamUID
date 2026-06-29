class SteamAPI:
    # 获取玩家摘要信息
    GetPlayerSummaries = "/ISteamUser/GetPlayerSummaries/v2/"

    # 获取玩家成就列表
    GetPlayerAchievements = "/ISteamUserStats/GetPlayerAchievements/v1/"

    #  获取游戏成就 Schema
    GetSchemaForGame = "/ISteamUserStats/GetSchemaForGame/v2/"

    #  获取全球成就解锁率
    GetGlobalAchievementPercentagesForApp = "/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v2/"

    # 获取玩家拥有的游戏
    GetOwnedGames = "/IPlayerService/GetOwnedGames/v1/"

    # 获取游戏当前在线人数
    GetNumberOfCurrentPlayers = "/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"

    