<p align="center">
  <img width="500px" src="assets/textures/coinbig.png"/>
</p>

# danser-go

[English](README.md)

[![GitHub release](https://img.shields.io/github/release/wieku/danser-go.svg)](https://github.com/Wieku/danser-go/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/wieku/danser-go/total?label=Downloads)](https://github.com/Wieku/danser-go/releases)
[![CodeFactor](https://www.codefactor.io/repository/github/wieku/danser-go/badge)](https://www.codefactor.io/repository/github/wieku/danser-go)
[![Discord server](https://img.shields.io/discord/713705871758065685.svg?label=&logo=discord&logoColor=ffffff&color=7389D8&labelColor=6A7EC2)](https://discord.gg/UTPvbe8)

danser-go 是用于 osu!standard 谱面的图形／命令行可视化工具，也能将 osu! 模式的 stable 和 lazer 回放录制为 MP4 视频。

Danser 仍在开发中，部分功能可能出现问题。遇到问题时，请提交包含尽可能详细信息的 issue。

**注意**：由于 macOS 的 OpenGL 支持有限，danser-go 无法在该平台运行；请使用双系统中的 Windows 或 Linux。

## 示例

- [Omoi - Chiisana Koi no Uta (Synth Rock Cover) [Kroytz's EX EX] - TAG2 Mirror Collage](https://youtu.be/Vo0Pbpu113Y)
- [Sex Whales & Fraxo - Dead To Me (feat. Lox Chatterbox) [extrad1881 (ar 10)] Mirror Collage](https://youtu.be/KCHqrVGdXrk)
- [Nightcore - Flower Dance [Amachoco ARX.7] Mandala Mirror Collage](https://youtu.be/HBC89S-UwFc)
- [Flower Dance (osu! cursordance)](https://youtu.be/lcnnz3fN3bs)
- [osu! top 50 replays knockout | xi - FREEDOM DiVE [ENDLESS DiMENSiONS]](https://youtu.be/kzr_Sr0Shuc)
- [osu! top 50 knockout | YURRY CANNON - Suicide Parade [Sakase]](https://youtu.be/GS_yoq5MJMU)
- [osu! top 50 replays knockout | Kobaryo - Bookmaker [Corrupt The World]](https://youtu.be/SJqkP1IDUq0)

## 运行 Danser

可以从上游 [releases](https://github.com/Wieku/danser-go/releases) 下载 Windows／Linux 64 位二进制文件。

解压到目标目录后，使用启动器 `danser`，或从终端启动。Windows cmd：

```bash
danser-cli <arguments>
```

Linux／Unix／Git Bash／PowerShell：

```bash
./danser-cli <arguments>
```

不带参数运行 `danser-cli` 时，会有一个小惊喜 ;)

## 命令行参数

- `-artist="NOMA"` 或 `-a="NOMA"`：曲师。
- `-title="Brain Power"` 或 `-t="Brain Power"`：曲名。
- `-difficulty="Overdrive"` 或 `-d="Overdrive"`：难度名。
- `-creator="Skystar"` 或 `-c="Skystar"`：谱师。
- `-md5=hash`：覆盖其他选图参数，查找 MD5（文件摘要）匹配的 `.osu`。
- `-id=433005`：覆盖其他选图参数，按 BeatmapID 查找 `.osu`，不是 BeatmapSetID。
- `-cursors=2`：镜像拼贴中的光标数量。
- `-tag=2`：TAG 模式的光标数量。
- `-speed=1.5`：音乐速度，1.5 相当于 osu! 的 Double Time。`-play` 搭配变速 Mods（游戏调整项）时忽略此参数。
- `-pitch=1.5`：音乐音高，1.5 对应 Nightcore 的音高；模拟 Nightcore 时同时设定速度为 1.5。
- `-settings=name`：使用 `settings/name.json`，而非 `settings/default.json`。
- `-debug`：显示额外信息，覆盖 `Graphics.DrawFPS` 设置。
- `-play`：以 osu!standard 模式游玩谱面。
- `-skip`：像 osu! 一样跳过谱面开头。
- `-start=20.5`：从指定秒数开始。
- `-end=30.5`：在指定秒数结束。
- `-knockout`：多回放淘汰模式。
- `-knockout2='["replay1.osr","replay2.osr"]'`：从 JSON 数组读取回放，而非 danser 的回放目录；忽略 `Knockout.MaxPlayers` 和 `Knockout.ExcludeMods`。
- `-record`：录制视频，需要可访问的 [FFmpeg](https://github.com/Wieku/danser-go/wiki/FFmpeg)。
- `-out=abcd`：隐含启用录制并指定文件名，扩展名由设置决定；使用 `-ss` 时指定截图名。
- `-replay="path_to_replay.osr"` 或 `-r="path_to_replay.osr"`：播放回放，覆盖选图参数。路径中的 `\` 请替换为 `\\` 或 `/`。
- `-mods=HDHR`：使用指定 Mods；指定时覆盖回放 Mods。`-mods=AT` 会启用带回放界面的光标舞蹈。
- `-mods2='[{"acronym":"DT","settings":{"speed_change":1.2}},{"acronym":"HD"}]'`：使用支持自定义参数的 lazer Mods 结构；指定时覆盖回放 Mods，加入 AT 同样启用带回放界面的光标舞蹈。
- `-skin`：覆盖 `Skin.CurrentSkin`。
- `-cs`、`-ar`、`-od`、`-hp`：覆盖圆圈大小、出现速度、判定难度及掉血设置，允许超出 osu! 常规范围；`-mods2` 指定 DA（Difficulty Adjust，难度调整）时忽略。
- `-nodbcheck`：跳过对新增、修改或删除谱面的数据库更新。
- `-noupdatecheck`：跳过 GitHub 上的 danser 新版本检查。
- `-ss=20.5`：在指定秒数生成 PNG 截图。
- `-quickstart`：启用 `-skip`，并将 `LeadInTime` 和 `LeadInHold` 设为 0。
- `-offset=20`：本地音频偏移，单位毫秒；与 `Audio.Offset` 不同，会作用于录制。符号方向已不再与 stable 相反。
- `-preciseprogress`：每推进 1% 输出一次录制进度。
- `-sPatch='{"Cursor":{"CursorSize":50}}'`：用 JSON 覆盖当前配置，重载配置时仍保留；第三方工具可据此调整少量设置，无需修改配置文件。

以下示例应产生相同结果。第一条假设只有一张谱面的难度名为 `Overdrive`：

```bash
<executable> -d="Overdrive" -tag=2
<executable> -t="Brain Power" -d="Overdrive" -tag=2
<executable> -t "Brain Power" -d Overdrive -tag 2
<executable> -t="ain pow" -difficulty="rdrive" -tag=2
<executable> -md5=59f3708114c73b2334ad18f31ef49046 -tag=2
<executable> -id=933228 -tag=2
```

设置和淘汰模式的详细用法见 [wiki](https://github.com/Wieku/danser-go/wiki)。

## 构建项目

克隆仓库，或下载 ZIP 并解压到目标目录。

### 依赖

- [64 位 Go，至少 1.24](https://go.dev/dl/)。
- Linux／Unix 使用 gcc／g++；Windows 使用 [WinLibs](http://winlibs.com/) MSVCRT+POSIX，TDM-GCC 不可用，mingw-w64 已过时。
- OpenGL 库，通常随驱动提供；Linux 服务器构建可安装 `libgl1-mesa-dev`。
- Linux 需要 xorg-dev、libgtk-3 和 libgtk-3-dev。
- 仅可选的[官方 osu!lazer 规则程序](tools/lazer-rules-host/README.zh-CN.md)需要 `third_party/osu/global.json` 指定的 .NET SDK。

### 构建与运行

进入仓库，首次运行或修改源码后执行：

```bash
go build
```

该命令会自动下载并构建所需依赖。然后运行：

```bash
./danser-go <arguments>
```

与发布包的 `danser-cli` 不同，源码构建不带参数时会打开启动器，但不能通过将回放拖到可执行文件上来预加载。如果需要该行为，使用 dist 脚本构建。

要让本地 lazer 回放或实时游玩使用官方 osu! 源码，请构建并启用[官方规则程序](tools/lazer-rules-host/README.zh-CN.md)。

需要独立且默认启用官方规则的 Linux 桌面应用时，使用 [danser-lazer 安装说明](tools/linux/README.zh-CN.md)。评分接入细节见[实现说明](tools/lazer-rules-host/IMPLEMENTATION.zh-CN.md)。

## 致谢与许可证

软件由 Sebastian Krajewski（[@Wieku](https://github.com/Wieku)）及[贡献者](https://github.com/Wieku/danser-go/graphs/contributors)创建。

除非另有说明，源码按 GNU General Public License v3.0 分发。

第三方资源的完整致谢及许可证见[致谢](CREDITS.zh-CN.md)。
