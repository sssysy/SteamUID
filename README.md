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

## 丨使用限制

> [!CAUTION]
> 本项目内的所有模板文件，以及任何用于 UI 渲染的相关资源，**未经原作者书面授权，不得以任何形式拷贝、二次修改或重新发布**。该限制涵盖但不局限于以下场景：
>
> - 上传至公开仓库或个人网站托管
> - 转载、二次散布或在社群中分享原始 / 修改版文件
> - 打包或内嵌进其他插件、应用、项目使用
>
> 如需取得授权，请联系 [Wuyi 无疑](https://github.com/KimigaiiWuyi)。

## 丨命令列表

### steam帮助
<img src="https://dlink.host/1drv/aHR0cHM6Ly8xZHJ2Lm1zL2kvYy8xYmIyNTkxODI4ZDcyZTIzL0lRQmlCSUowU2ZIT1Q2clc2UzQ3UDNNWkFjMlFfanNSSWVpTHc0WmphQ1pqQ1JvP2U9S0dmZjYz.jpg" width="480" alt="Steam帮助菜单"></a>

### 文字版

#### 基础命令
| 命令 | 说明 |
|------|:------:|
| `steam帮助` | 查看帮助菜单 |
| `steam绑定` | 绑定steam |
| `steam解绑` | 解绑steam |
| `steam查看` | 查看已绑定的steamid64列表 |

#### 推送相关
| 命令 | 说明 |
|------|:------:|
| `steam开启推送` | 开启全部steam状态推送功能 |
| `steam关闭推送` | 关闭全部steam状态推送功能 |
| `steam开启开始游戏推送` | 开启开始游戏状态推送功能 |
| `steam关闭开始游戏推送` | 关闭开始游戏状态推送功能 |
| `steam开启结束游戏推送` | 开启结束游戏状态推送功能 |
| `steam关闭结束游戏推送` | 关闭结束游戏状态推送功能 |
| `steam开启成就推送` | 开启成就推送功能 |
| `steam关闭成就推送` | 关闭成就推送功能 |

#### 游戏库相关
| 命令 | 说明 |
|------|:------:|
| `steam游戏墙`         |      查看自己游戏墙       |
| `steam游戏成就123456` | 查看appid123456的成就详情 |



## 效果图

### steam游戏成就
<img src="https://dlink.host/1drv/aHR0cHM6Ly8xZHJ2Lm1zL2kvYy8xYmIyNTkxODI4ZDcyZTIzL0lRRHR5UVVwYVVENFJhX2UxakdHblNIeUFRVVoxcDVZMGpxRkpBWmYtRGhQRENjP2U9RTdMMlJk.png" width="160"/>

### steam成就推送
<img src="https://dlink.host/1drv/aHR0cHM6Ly8xZHJ2Lm1zL2kvYy8xYmIyNTkxODI4ZDcyZTIzL0lRQWVnNm85WjBHc1NyZWhvWHJJaVFLdUFiZEJqb3ZlQ1JHMXlNdUNLenk3TlY0P2U9cXlpTWdS.png" width="160"/>

### steam开始游戏 / 结束游戏推送
<img src="https://dlink.host/1drv/aHR0cHM6Ly8xZHJ2Lm1zL2kvYy8xYmIyNTkxODI4ZDcyZTIzL0lRQ2lrOERKZ1VIZFE1bkl1S2dOTzRDeUFjQlB1SmRyYlM0SlhjcGdLSTU0bGFvP2U9bm1ja0gy.png" width="160"/>

### steam游戏墙
<img src="https://dlink.host/1drv/aHR0cHM6Ly8xZHJ2Lm1zL2kvYy8xYmIyNTkxODI4ZDcyZTIzL0lRQnhKUDRNUFhhX1NKdUROakNNYzJ1T0FTeVRKNGlqam5wMG95YzZRUFF2QXo4P2U9aHNRV2dw.jpg" width="160"/>


## 计划功能

- [x] 支持设置所有状态推送推送默认值
- [ ] 玩家上下线状态推送
- [ ] 带游玩时长的游戏库存图片
- [ ] 游戏降价 / 打折信息订阅推送
- [ ] 支持绑定交易报价链接
- [ ] steam玩什么 (随机抽游戏)
- [ ] 游戏名 / 成就名本地化名字获取
- [ ] 总结推送功能 (定时总结周期内游戏情况而不每次状态变化都推送)
- [ ] 群游玩时长排行榜




## 丨其他

- 本项目仅供学习使用，请勿用于商业用途
- [GPL-3.0 License](LICENSE)


## 致谢

- [Wuyi 无疑](https://github.com/KimigaiiWuyi)
- [gsuid_core](https://github.com/Genshin-bots/gsuid_core)
- [Steam Web API](https://developer.valvesoftware.com/wiki/Steam_Web_API)
- steam游戏墙参考自 [steam_wall](https://github.com/zhMoody/steam_wall)
