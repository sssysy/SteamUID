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

    # 获取游戏详情 / 价格
    store_GetGameDetails = "/api/appdetails"

    # 获取服务器状态
    api_GetServerInfo = "/ISteamWebAPIUtil/GetServerInfo/v1"
    # 游戏封面图api
    @staticmethod
    def GetGameCoverImageURL(appid: str, variant: str = "header") -> str:
        """
        variant支持：
        header	        商店页头部横幅
        library_600x900	库竖版封面
        library_hero	库英雄图
        capsule_616x353	社交分享卡图
        capsule_467x181	中等胶囊图
        capsule_231x87	小胶囊图
        capsule_184x69	搜索缩略图
        """
        url = f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/{variant}.jpg"
        return url
