# 在 Linux 安装 danser-lazer

[English](README.md)

安装程序会为当前用户安装独立的 Linux x86-64 应用。应用菜单入口和命令均名为 `danser-lazer`；不带参数启动时打开原有 danser 启动器。首次安装的设置默认启用官方 lazer 规则，并将渲染限制为 120 FPS（每秒帧数）。更新安装时保留已有设置。

先安装 [Go 和原生构建依赖](../../README.zh-CN.md#构建项目)、`third_party/osu/global.json` 指定的 SDK（软件开发工具包）、`desktop-file-utils` 和 `jq`。请在图形桌面会话中执行安装：首次安装会调用 danser 原有的设置初始化，检测主显示器分辨率，再应用官方引擎预设。在仓库根目录运行：

```bash
sh tools/linux/install.sh
```

如果 SDK 不在 `PATH` 中，用 `DOTNET` 指定其可执行文件。如果 `/tmp` 空间不足，将 `GOTMPDIR` 指向已有且空间足够的磁盘目录。安装程序会构建 Go 应用，并发布自带 .NET 运行时的规则程序。

```bash
DOTNET=/path/to/dotnet GOTMPDIR=/path/to/build-temp sh tools/linux/install.sh
```

应用安装到 `${XDG_DATA_HOME:-$HOME/.local/share}/danser-lazer`，命令链接放在 `$HOME/.local/bin`，桌面入口放在 XDG 应用目录。设置、数据库和生成内容均属于该应用目录。现有 danser-go 安装保持独立；安装程序不会复制其设置、凭据或数据库。

从应用菜单打开 **danser-lazer**，或运行：

```bash
danser-lazer
danser-lazer /path/to/replay.osr
danser-lazer -play -mods=LZ -md5=<beatmap-md5>
```

如果需要，将 `$HOME/.local/bin` 加入 `PATH`，也可以直接使用该目录中的命令。在启动器里选择 Songs 谱面目录和 Skins 皮肤目录。若 lazer 导出内容分为 `beatmap/` 和 `audio/`，需将 `.osu` 与其引用的音频放到 danser Songs 下的同一子目录；保持 `.osu` 文件字节不变，以便正确匹配回放。

启动器使用已安装配置中的引擎选择。实时游玩使用官方评分时还需选择 lazer 模式（`LZ`）；stable 回放和非 lazer 模式仍使用原有评分路径。引擎支持范围见[规则程序说明](../lazer-rules-host/README.zh-CN.md)，与官方客户端的对照步骤见[验收清单](../lazer-rules-host/ACCEPTANCE.zh-CN.md)。

更新源码后重新运行安装程序，即可重新构建并更新应用。卸载时移除 `danser-lazer.desktop`、`$HOME/.local/bin/danser-lazer` 链接及安装的 `danser-lazer` 目录。该目录也包含设置和生成的视频，需要时先保留这些内容。
