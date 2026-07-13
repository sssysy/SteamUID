# steamUID

<p align="center">
  <a href="https://github.com/Genshin-bots/gsuid_core"><img src="https://dlink.host/1drv/aHR0cHM6Ly8xZHJ2Lm1zL2kvYy8xYmIyNTkxODI4ZDcyZTIzL0lRQk10SGVBTlRQalRiVFM0TUdKRGV6UkFacXppQ0JVd0VZZzFXRmVYdnJ6UXFjP2U9TzZQejBi.gif" width="256" height="256" alt="SteamUID"></a>
</p>
<h1 align="center">SteamUID 0.1.0</h1>
<h4 align="center">基于 gsuid_core 的 steam 状态推送插件</h4>
<div align="center">
  <a href="https://docs.sayu-bot.com/" target="_blank">安装文档</a> &nbsp; · &nbsp;
  <a href="https://github.com/Genshin-bots/gsuid_core" target="_blank">gsuid_core</a>
</div>

## 丨安装提醒

> **注意：该插件为 [早柚核心(gsuid_core)](https://github.com/Genshin-bots/gsuid_core) 的扩展，具体安装方式可参考上方安装文档**
>
> **运行环境要求 Python `3.12+`**
>
> ~~如果已经是最新版本的 `gsuid_core`，可以直接对 bot 发送 `core安装插件SteamUID`，然后重启 Core 以应用安装~~
>
> 插件检测 steam 状态需要将 steam 资料设置为公开
>
> 🚧 项目快速迭代中，有漏洞可提issue或pr 🚧

## 丨使用前注意

> [!CAUTION]
> 使用前请务必阅读以下事项，否则会导致此插件无法正常工作
> - 使用本插件前请先确保框架机器可以正常访问 **steam 官方服务器**，若无法访问请务必配置反向代理([参考](https://github.com/XasYer/steam-plugin#%E4%BD%BF%E7%94%A8cloudflare%E6%90%AD%E5%BB%BA%E5%8F%8D%E4%BB%A3-%E8%BF%9E%E6%8E%A5%E4%B8%8D%E4%B8%8Asteam%E6%83%85%E5%86%B5%E4%B8%8B%E7%9A%84%E5%A4%87%E9%80%89))并在设置中配置**SteamAPI反代URL** 和 **Steam商店反代URL**。
> - 首次启用本插件务必在设置中填写**Steam API Key**，否则插件无法工作！。

## 丨命令列表

### steam帮助(图片更新可能不及时)
<img src="https://dlink.host/1drv/aHR0cHM6Ly8xZHJ2Lm1zL2kvYy8xYmIyNTkxODI4ZDcyZTIzL0lRQ2FlcEk0R3k1TFRMR2tzLWZmUUJHNkFXRFJCRXZobV9JbHh2MWZ5Rlplb2RrP2U9ejJzWGx5.jpg" width="480" alt="Steam帮助菜单">
### 命令说明

#### 绑定账号
| 命令 | 说明 |
|------|:------:|
| `steam绑定` | 使用 OpenID 方式绑定 steam |
| `steam绑定12345678` | 使用好友码 / steamid 绑定 steam|
| `steam解绑` | 使用 OpenID 方式解绑 steam |
| `steam解绑12345678` | 使用好友码 / steamid 解绑 steam|
| `steam查看` | 查看自己当前群绑定 steam |
| `steam查看全部` | 查看自己所有绑定 steam |

#### 游戏状态
| 命令 | 说明 |
|------|:------:|
| `steam开启推送` | 开启自己的所有推送功能 |
| `steam关闭推送` | 关闭自己的所有推送功能 |
| `steam开启开始游戏推送` | 开启自己的开始游戏推送功能 |
| `steam关闭开始游戏推送` | 关闭自己的开始游戏推送功能 |
| `steam开启结束游戏推送` | 开启自己的结束游戏推送功能 |
| `steam关闭结束游戏推送` | 关闭自己的结束游戏推送功能 |
| `steam推送状态` | 查看自己的推送开关状态 |

#### 库存相关
| 命令 | 说明 |
|------|:------:|
| `steam游戏墙123456`  | 查询指定steam的游戏墙    |
| `steam游戏成就123456` | 查看appid123456的成就详情 |
| `steam开启成就推送` | 开启自己的成就推送功能 |
| `steam关闭成就推送` | 关闭自己的成就推送功能 |
| `steam玩什么` | 从自己的游戏库随机挑3个游戏 |

#### 商店相关
| 命令 | 说明 |
|------|:------:|
| `steam订阅降价123456` | 订阅商店游戏降价信息 |
| `steam取消订阅降价123456` | 取消订阅商店游戏降价信息 |
| `steam订阅降价查看` | 查看订阅的商店游戏降价信息 |

#### 社交相关
| 命令 | 说明 |
|------|:------:|
| `@xx steam加好友123456` | 获取被 @ 用户的好友码 |
| `steam群排行` | 查看群游玩时长排行榜 |

#### 其他服务
| 命令 | 说明 |
|------|:------:|
| `steam帮助` | 呼出本插件帮助菜单 |
| `steam清除全部缓存` | 清除全部缓存 |

## 效果图

### steam游戏成就
<img src="https://dlink.host/1drv/aHR0cHM6Ly8xZHJ2Lm1zL2kvYy8xYmIyNTkxODI4ZDcyZTIzL0lRRHR5UVVwYVVENFJhX2UxakdHblNIeUFRVVoxcDVZMGpxRkpBWmYtRGhQRENjP2U9RTdMMlJk.png" width="160"/>

### steam成就推送
<img src="https://dlink.host/1drv/aHR0cHM6Ly8xZHJ2Lm1zL2kvYy8xYmIyNTkxODI4ZDcyZTIzL0lRRDVmeDFrYTF2RlI2aXo2RklpNFlSQkFkUHFGQ1FwaloteW8wZllfbkpVQXhFP2U9Ynd5bXBh.png" width="160"/>

### steam开始游戏 / 结束游戏推送
<img src="https://dlink.host/1drv/aHR0cHM6Ly8xZHJ2Lm1zL2kvYy8xYmIyNTkxODI4ZDcyZTIzL0lRQUEtZEVQOXV3blRwMjJaN2R0MVFXNEFaZUMtVTVsOWdQZjFRSmZGSUd5UlIwP2U9elRLQmdu.png" width="160"/>

### steam游戏墙
<img src="https://dlink.host/1drv/aHR0cHM6Ly8xZHJ2Lm1zL2kvYy8xYmIyNTkxODI4ZDcyZTIzL0lRQnhKUDRNUFhhX1NKdUROakNNYzJ1T0FTeVRKNGlqam5wMG95YzZRUFF2QXo4P2U9aHNRV2dw.jpg" width="160"/>

## steam玩什么
<img src="https://dlink.host/1drv/aHR0cHM6Ly8xZHJ2Lm1zL2kvYy8xYmIyNTkxODI4ZDcyZTIzL0lRQjcxemRIckRxTlI0ZGYwVmhpQm5YUkFkR0lzZjAzVktic2x2ZTQ3VUNSYnNRP2U9WXhMVUhP.jpg" width="160">



## 计划功能

- [x] 支持设置所有状态推送推送默认值
- [ ] 玩家上下线状态推送
- [ ] 带游玩时长的游戏库存图片
- [x] 游戏降价 / 打折信息订阅推送
- [x] steam玩什么 (随机抽游戏)
- [x] 游戏名 / 成就名本地化名字获取
- [ ] 总结推送功能 (定时总结周期内游戏情况而不每次状态变化都推送)
- [x] 群游玩时长排行榜
- [x] 隐藏 steamid / 好友码




## 丨其他

- 本项目仅供学习使用，请勿用于商业用途
- [GPL-3.0 License](LICENSE)
- 部分功能没有写绘图，以后再说

## 致谢

- 此插件依赖框架作者 [Wuyi 无疑](https://github.com/KimigaiiWuyi)
- 此插件依赖自框架 [gsuid_core](https://github.com/Genshin-bots/gsuid_core)
- 所有请求格式来自 [Steam Web API](https://developer.valvesoftware.com/wiki/Steam_Web_API)
- steam游戏墙参考自 [steam_wall](https://github.com/zhMoody/steam_wall)
- steam反代教程来自 [Yunzai-steam-plugin](https://github.com/XasYer/steam-plugin)
