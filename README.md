# SteamUID

<p align="center">
  <a href="ICON.png">
    <img src="ICON.png" width="256" height="256" alt="SteamUID">
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

## 丨命令列表

<details><summary>账号绑定</summary>

| 命令 | 说明 |
|------|:------:|
| `steam绑定` | 绑定 Steam 账号（OpenID 扫码或手动传参） |
| `steam解绑` | 解绑当前会话选中的 Steam 账号 |
| `steam查看` | 查看会话内已绑定的 Steam 账号 |
| `steam切换 [好友码\|序号]` | 在已绑定账号间切换，无参数切到下一位 |
| `steam刷新用户` | 重拉当前账号资料并重发卡片 |

</details>

<details><summary>个人资料</summary>

| 命令 | 说明 |
|------|:------:|
| `steam状态 [@他人\|steamid\|好友码]` | 查询账号的在线状态与当前游戏 |
| `steam信息` | 渲染账号资料与统计信息卡片 |
| `steam群友状态` | 本群已绑定群友的实时在线与游戏状态 |
| `steam年度回顾 2024` | 获取该账号指定年份的官方回顾分享图 |

</details>

<details><summary>库存与成就</summary>

| 命令 | 说明 |
|------|:------:|
| `steam游戏墙` | 把账号游戏库渲染成封面墙 |
| `steam家庭库` | 把 Steam 家庭共享库渲染成封面墙 |
| `steam玩什么` | 从游戏库随机挑三款游戏 |
| `steam最近游玩` | 最近两周玩过的游戏，按近两周时长排序 |
| `steam游戏成就 游戏名` | 渲染指定游戏的成就进度卡片 |

</details>

<details><summary>排行统计</summary>

| 命令 | 说明 |
|------|:------:|
| `steam排行` | 自己在本群的游戏时长排行 |
| `steam群玩家排行` | 按群内用户累计游玩时长排行 |
| `steam群游戏排行` | 按群内所有游戏累计时长排行 |
| `steam群游戏玩家排行 游戏名` | 指定游戏在本群内玩家的时长排行 |

</details>

<details><summary>商店订阅</summary>

| 命令 | 说明 |
|------|:------:|
| `steam订阅降价 游戏名` | 订阅指定游戏的降价提醒 |
| `steam取消订阅降价 游戏名` | 取消该游戏的降价提醒 |
| `steam订阅降价查看` | 查看当前会话订阅的降价与当前售价 |
| `steam订阅公告 游戏名` | 订阅该游戏的新公告推送 |
| `steam取消订阅公告 游戏名` | 取消该游戏的公告推送 |
| `steam订阅公告列表` | 查看当前会话订阅的游戏公告列表 |

> 公告 / 降价订阅按会话生效：群内订阅对该群生效，私聊订阅只对本人生效

</details>

<details><summary>推送通知</summary>

| 命令 | 说明 |
|------|:------:|
| `steam订阅推送` | 一次性开启全部推送类型 |
| `steam取消订阅推送` | 一次性关闭全部推送类型 |
| `steam订阅开始游戏推送` | 账号开始游戏时推送 |
| `steam订阅结束游戏推送` | 账号结束游戏时推送 |
| `steam订阅获得成就推送` | 解锁新成就时推送 |
| `steam订阅用户上线推送` | 账号上线时推送 |
| `steam订阅用户离线推送` | 账号离线时推送 |

> 推送订阅按会话生效：同一个 Steam 账号可在多个群各自绑定并订阅，各群开关与推送互不影响；
> 同一群内该账号只允许一个人绑定，群内推送开关也只有该账号的绑定者本人可以切换

</details>

<details><summary>登录功能</summary>


| 命令 | 说明 |
|------|:------:|
| `steam登录` | 扫码登录 Steam 账号 |
| `steam激活` | 私聊内激活一枚或多枚 CDKey |
| `steam探索队列` | 立即对名下账号执行探索队列任务 |
| `steam开启自动探索队列` | 开启每日自动探索队列 |
| `steam关闭自动探索队列` | 关闭每日自动探索队列 |

</details>

<details><summary>缓存管理</summary>

| 命令 | 说明 |
|------|:------:|
| `steam清除接口缓存` | 清空数据库接口缓存 |
| `steam清除图片缓存` | 清空 img_cache 图片缓存 |
| `steam清除文件缓存` | 清空 cache 文件缓存 |
| `steam清除全部缓存` | 清空接口 / 图片 / 文件全部缓存 |

</details>

<details><summary>数据迁移</summary>

| 命令 | 说明 |
|------|:------:|
| `steam迁移订阅状态` | 把 1.0 遗留库内的推送开关与降价 / 公告订阅迁移到框架订阅（仅管理员） |

</details>

<details><summary>其他</summary>

| 命令 | 说明 |
|------|:------:|
| `steam更新acf` | 把上传的 appmanifest 伪造为最新版本 |
| `steam帮助` | 获取帮助图 |

</details>

## 丨其他

- 本项目仅供学习使用，请勿用于商业用途
- [GPL-3.0 License](LICENSE)

## 致谢

- [Wuyi 无疑](https://github.com/KimigaiiWuyi)
- [gsuid_core](https://github.com/Genshin-bots/gsuid_core)
- [Steam Web API](https://developer.valvesoftware.com/wiki/Steam_Web_API)
- [steam_wall](https://github.com/zhMoody/steam_wall)
- [yunzai-steam-plugin](https://github.com/XasYer/steam-plugin)
- [steam-next](https://github.com/fabieu/steam-next)
- [卡拉彼丘表情包](https://wiki.biligame.com/klbq/%E8%A1%A8%E6%83%85%E5%8C%85)
