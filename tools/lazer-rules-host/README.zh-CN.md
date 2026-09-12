# 官方 osu!lazer 规则程序

[English](README.md) · [实现说明](IMPLEMENTATION.zh-CN.md) · [Linux 应用安装](../linux/README.zh-CN.md)

此程序通过官方 osu!lazer 规则集处理 osu!standard 回放和实时输入。Danser 保留原有渲染与光标处理，由规则程序提供权威判定事件、分数、连击、血量、评级及 PP（Performance Points，表现分）。

osu! 源码由 `third_party/osu` Git 子模块固定，每次响应都带有该源码版本。响应不兼容或规则程序失败时，danser 会报错，不会静默切换评分引擎。

## 支持范围

官方规则支持通过 `-replay`、`-knockout`、`-knockout2` 加载的本地 lazer 回放，以及完整谱面的 lazer `-play`。多回放最多同时使用两个规则进程，以限制内存占用。回放覆盖参数及实时 `-mods`／`-mods2` 会转换成 osu! 的缩写与设置格式，再由官方规则集验证。

实时游玩将输入帧发送给一个持续运行的规则进程，并等待每帧确认后发布官方判定。只有选择官方实时引擎时才拒绝 `-start` 和 `-end`，因为截取后的 danser 谱面不构成官方完整谱面成绩。内置引擎保留原有局部游玩行为。

## 构建

使用 `third_party/osu/global.json` 指定的 .NET SDK。规则程序的目标框架在 `Danser.LazerRulesHost.csproj` 中定义，与引用的 osu! 项目保持一致。

```bash
git submodule update --init --recursive third_party/osu
dotnet publish tools/lazer-rules-host/Danser.LazerRulesHost.csproj \
  --configuration Release \
  --output lazer-rules-host
go build
```

将所选设置文件中的 `Gameplay.LazerRulesEngine` 设为 `official`。也可以只对单次运行启用：

```bash
./danser-go -replay=/path/to/replay.osr \
  -sPatch='{"Gameplay":{"LazerRulesEngine":"official"}}'

./danser-go -play -mods=LZHD \
  -sPatch='{"Gameplay":{"LazerRulesEngine":"official"}}' \
  -md5=<beatmap-md5>
```

源码构建仍默认使用内置引擎，因此既有构建与非回放模式无需 .NET 规则程序即可运行。

## 独立验证

规则程序向标准输出写入一份 JSON 文档：

```bash
./lazer-rules-host/danser-lazer-rules rejudge \
  --beatmap /path/to/map.osu \
  --replay /path/to/replay.osr \
  --mods-json '[{"acronym":"HD"}]'
```

省略 `--mods-json` 时使用回放原有的 Mods（游戏调整项）。`recorded` 始终表示回放保存的成绩；`rejudged`、逐判定成绩快照，以及实际、全连、全完美 PP 均由固定版本的 osu! 源码计算。`live` 命令通过标准输入输出使用 JSON Lines（每行一条 JSON）的请求与确认协议；该协议由 danser 管理，用户通常无需直接调用。

与客户端对照时，请使用[手动验收清单](ACCEPTANCE.zh-CN.md)。

## 更新 osu!lazer

审查并固定一个明确的上游提交，重新构建规则程序，然后执行 Go 与规则程序检查：

```bash
git -C third_party/osu fetch origin
git -C third_party/osu checkout <reviewed-osu-revision>
dotnet build tools/lazer-rules-host/Danser.LazerRulesHost.csproj
go test ./app/rulesets/osu/...
```

协议结构位于 `Protocol.cs` 与 `app/rulesets/osu/lazer/protocol.go`。不兼容变更需同时更新 `Protocol.cs` 中的 `Protocol.Version` 和 `app/rulesets/osu/lazer/client.go` 中的 `ProtocolVersion`。
