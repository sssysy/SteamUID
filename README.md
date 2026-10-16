# SteamUID

<p align="center">
  <a href="ICON.png">
    <img src="ICON.png" width="227" height="227" alt="SteamUID">
  </a>
</p>
<h1 align="center">SteamUID 2.0.0</h1>
<h4 align="center">基于 gsuid_core 的 全功能 Steam 插件</h4>

<p align="center">
  <a href="https://www.python.org/" target="_blank"><img src="https://img.shields.io/badge/Python-3.12+-blue" alt="Python 3.12+"></a>
  <a href="https://github.com/Genshin-bots/gsuid_core" target="_blank"><img src="https://img.shields.io/badge/gsuid_core-0.10.7+-orange" alt="gsuid_core 0.10.7+"></a>
</p>

<div align="center">
  <a href="https://docs.sayu-bot.com/" target="_blank">安装文档</a> &nbsp; · &nbsp;
  <a href="https://github.com/Genshin-bots/gsuid_core" target="_blank">gsuid_core</a>
</div>

## 丨安装提醒

> **注意：该插件为 [早柚核心(gsuid_core)](https://github.com/Genshin-bots/gsuid_core) 的扩展，具体安装方式可参考上方安装文档**
>
> 插件需要配置有效的 Steam Web API Key 才可正常使用
>
> 若从本插件 0.1.0 版本升级至 2.x 版本请手动执行一次 `steam迁移订阅状态` 迁移数据库
> 新安装用户请忽略此提示
>
> 此插件需要可连接至 Steam 社区的网络环境，如无法直连可配置反代Base URL并填入插件配置中
>
> 🚧 项目快速迭代中，有漏洞可提issue或pr 🚧

> [!CAUTION]
> 登录命令可能会导致收到红信(异地红)，请谨慎登录！
> 大部分功能使用 `steam绑定` 绑定账号后即可使用~

## 丨命令列表
> 对于可传参数的命令没有额外说明默认支持传递: `@他人 / 个人资料url / steamid / 好友码`

<details><summary>绑定登录</summary>

| 命令 | 说明 |
|------|:------:|
| `steam绑定 12345678` | 绑定 Steam 账号 |
| `steam解绑 12345678` | 解绑当前会话选中的 Steam 账号 |
| `steam登录` | 扫码登录 Steam 账号 |
| `steam查看` | 查看会话内已绑定的 Steam 账号 |
| `steam切换 12345678` | 在已绑定账号间切换，不传默认切换下一个 |
| `steam刷新用户` | 刷新当前账号的缓存 |

</details>

<details><summary>账号信息</summary>

| 命令 | 说明 |
|------|:------:|
| `steam状态 12345678` | 查询账号的在线状态与当前游戏 |
| `steam信息 12345678` | 渲染账号资料与统计信息卡片 |
| `steam年度回顾 2025` | 获取该账号指定年份的官方回顾分享图 |
| `steam游戏墙` | 把账号游戏库渲染成封面墙 |
| `steam玩什么` | 从游戏库随机挑三款游戏 |
| `steam最近游玩` | 最近两周玩过的游戏 |
| `steam游戏成就 黑神话` | 渲染指定游戏的成就进度卡片 |
| `steam查封禁` | 查询账号的社区 / VAC / 经济封禁情况 |
| `steam转换 12345678` | 通过好友码或其他格式的个人资料转换为steamid64、个人资料url信息 |

</details>

<details><summary>排行统计</summary>

| 命令 | 说明 |
|------|:------:|
| `steam排行` | **自己**在本群的游戏时长排行 |
| `steam群玩家排行` | 按群内**用户**累计游玩时长排行 |
| `steam群游戏排行` | 按群内所有**游戏**累计时长排行 |
| `steam群游戏玩家排行 apex` | 指定**游戏**在本群内**玩家的时长**排行 |
| `steam群友状态` | 本群已绑定群友的实时在线与游戏状态 |
| `steam当前玩家 dota2` | 查询指定游戏当前的在线玩家数 |
| `steam本周热门排行` | 本周 / 当前最热游戏 |
| `steam本周热销排行` | 本周 / 上周销量榜 |

</details>

<details><summary>订阅相关</summary>

| 命令 | 说明 |
|------|:------:|
| `steam订阅状态` | 查看全局开启的推送开关与公告 / 降价订阅数量 |
| `steam订阅推送` | 一次性开启全部推送类型 |
| `steam取消订阅推送` | 一次性关闭全部推送类型 |
| `steam订阅开始游戏推送` | 账号开始游戏时推送 |
| `steam订阅结束游戏推送` | 账号结束游戏时推送 |
| `steam订阅获得成就推送` | 解锁新成就时推送 |
| `steam订阅用户上线推送` | 账号上线时推送 |
| `steam订阅用户离线推送` | 账号离线时推送 |
| `steam订阅降价 游戏名` | 订阅指定游戏的降价提醒 |
| `steam取消订阅降价 游戏名` | 取消该游戏的降价提醒 |
| `steam订阅降价查看` | 查看当前会话订阅的降价与当前售价 |
| `steam订阅公告 游戏名` | 订阅该游戏的新公告推送 |
| `steam取消订阅公告 游戏名` | 取消该游戏的公告推送 |
| `steam订阅公告列表` | 查看当前会话订阅的游戏公告列表 |

</details>

<details><summary>登录解锁</summary>

> [!CAUTION]
> 登录命令可能会导致收到红信(异地红)，请谨慎登录！

| 命令 | 说明 |
|------|:------:|
| `steam激活` | 私聊内激活一枚或多枚 CDKey |
| `steam家庭库` | 把 Steam 家庭共享库渲染成封面墙|
| `steam探索队列` | 立即对名下账号执行探索队列任务 |
| `steam开启自动探索队列` | 开启每日自动探索队列 |
| `steam关闭自动探索队列` | 关闭每日自动探索队列 |
| `steam愿望单列表` | 查看目标账号的愿望单与当前售价 |
| `steam增加愿望单 游戏名` | 把游戏加入自己账号的愿望单 |
| `steam删除愿望单 游戏名` | 把游戏移出自己账号的愿望单 |

</details>

<details><summary>其他</summary>

| 命令 | 说明 |
|------|:------:|
| `steam帮助` | 获取帮助图 |
| `steam更新acf` | 把上传的 appmanifest 伪造为最新版本 (本地游戏绕过 steam 更新) |
| `steam清除接口缓存` | 清空接口缓存 |
| `steam清除图片缓存` | 清空图片缓存 |
| `steam清除文件缓存` | 清空文件缓存 |
| `steam清除全部缓存` | 清空全部缓存 |
| `steam迁移订阅状态` | 从0.1.0版本迁移上来可以用这个命令迁移订阅，其他情况不需要用 |

</details>

## 丨其他

- 本项目仅供学习使用，请勿用于商业用途
- [GPL-3.0 License](LICENSE)

## 丨QA
#### 1. 插件安装完毕后大部分功能无法使用？
> 请先检查后台是否配置了有效且正确的Steam API Key，[点此获取](https://steamcommunity.com/dev/apikey)

#### 2. 更新acf命令怎么用？
> 1. 打开需要忽略更新的游戏的安装路径(`游戏库` - `右键游戏` - `管理` - `浏览本地文件`)
> 2. 回退两级目录(到 `steamapps` 文件夹中)
> 3. 找到游戏appid对应的 `appmanifest_{appid}.acf` 文件
>   (appid可通过`游戏库` - `右键游戏` - `属性` - `更新` - `APP ID` 获取)
> 4. 将文件上传，并引用文件发送 `steam更新acf` 指令
>   **需要core适配器支持文件引用功能**
> 5. 插件返回新的acf文件后替换本地同名文件即可

## 致谢

- [Wuyi 无疑](https://github.com/KimigaiiWuyi)
- [gsuid_core](https://github.com/Genshin-bots/gsuid_core)
- [Steam Web API](https://developer.valvesoftware.com/wiki/Steam_Web_API)
- [steam_wall](https://github.com/zhMoody/steam_wall)
- [yunzai-steam-plugin](https://github.com/XasYer/steam-plugin)
- [steam-next](https://github.com/fabieu/steam-next)
- [卡拉彼丘表情包](https://wiki.biligame.com/klbq/%E8%A1%A8%E6%83%85%E5%8C%85)
