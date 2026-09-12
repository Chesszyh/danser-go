# 官方 lazer 评分接入实现

[English](IMPLEMENTATION.md)

## 职责与源码版本

Danser 负责渲染和游玩调度，配套 C# 进程执行固定版本的官方 osu!standard 规则。源码构建仍默认使用原有 Go 评分引擎；独立 Linux 安装则在自己的初始配置中选择官方引擎。入口和支持范围见[规则程序说明](README.zh-CN.md)。

`third_party/osu` 是 Git 子模块，因此每个 danser 提交都能确定所依赖的 osu! 源码版本。[Danser.LazerRulesHost.csproj](Danser.LazerRulesHost.csproj) 的 `AddOsuSourceRevision` 构建目标将该版本写入规则程序程序集，响应通过 `engine.osuSourceRevision` 返回。规则程序直接引用 `osu.Game` 和 `osu.Game.Rulesets.Osu`，不在 Go 中维护评分或表现分公式的翻译副本。

## 离线回放链路

1. [ReplayController.loadOfficialReplays](../../app/dance/rcontroller.go) 收集 lazer 回放路径、实际生效的 Mods（游戏调整项）和选中的原始 `.osu` 文件。Stable 回放控制器继续使用 Go 规则。
2. [lazer.Rejudge](../../app/rulesets/osu/lazer/client.go) 查找 `lazer-rules-host/danser-lazer-rules`，通过有并发数量限制的工作队列运行它。每个规则进程接收一组谱面／回放及可选的 Mods 覆盖参数；结果保持输入顺序。
3. [ReplayAnalysisGame](ReplayAnalysisGame.cs) 加载 `FlatWorkingBeatmap`，用 [SilentWorkingBeatmap](SilentWorkingBeatmap.cs) 提供静音音轨，再通过官方 `LegacyScoreDecoder` 的子类解析 `.osr`。所提供谱面必须与回放保存的谱面哈希匹配，规则集必须是 osu!standard。
4. 官方 `ReplayPlayer` 创建可游玩谱面和游戏状态。规则程序在跳转处理回放前订阅 `ScoreProcessor.NewJudgement`，捕获包含滑条组成部分在内的每个判定。跳转目标超过回放末尾及最后一个物件，确保完成结算。
5. 返回历史成绩 `recorded`、重新计算的 `rejudged` 和按时间排列的 `judgements`。Danser 将结果绑定到对应光标，随自身显示时钟推进逐条应用。

回放原始成绩在覆盖 Mods 前保存，仅用于检查，不替代重新计算的成绩。

## 实时输入链路

[PlayerController](../../app/dance/pcontroller.go) 仅在同时选择官方引擎和 lazer 模式时准备完整谱面会话。[Player](../../app/states/player.go) 在 quickstart 预热结束后启动会话；该路径拒绝 `-start` 或 `-end` 局部游玩。

控制器约以 60 Hz 采样光标位置，按键状态变化则立即发送。BASS 音频时钟的小幅回拨只在外发时间戳上被钳制，以保持回放输入时间单调；danser 自身时钟不被修改。

[LiveSession](../../app/rulesets/osu/lazer/live.go) 启动一个持续运行的规则进程，并等待 `ready`。随后发送 `frame` 请求，包含帧编号、时刻、位置和左键／右键／烟雾状态。[LiveAnalysisGame](LiveAnalysisGame.cs) 将其转换为官方 `OsuReplayFrame`，追加到尚未结束的回放，让官方播放器消费。规则程序确认已处理的帧并返回待发布的判定事件；控制器收到确认后才应用结果。

结束时，`finish` 将回放输入标记为完整。规则程序通过 `complete` 返回剩余判定和最终成绩；关闭会话会释放子进程。`error` 消息、非法帧顺序或不兼容响应会使官方会话失败。

## 判定、成绩与表现分

离线与实时路径共享 [ScoreAnalysis](ScoreAnalysis.cs)。它将官方物件及其嵌套组成部分映射回 danser 的顶层物件序号。每条事件携带组成部分、实际与最大判定、判定时刻及时间偏差、判定前后连击、是否影响成绩、可选的命中光标位置，以及成绩快照。

每次快照由 `ScoreProcessor.PopulateScore` 填充官方成绩字段。难度使用官方难度计算器，PP（Performance Points，表现分）使用官方表现分计算器。中途快照使用不晚于被判物件结束时刻的分段难度；最终快照使用完整谱面难度。

| 输出 | 来源 |
| --- | --- |
| 标准化分数、准确率、连击、评级、判定统计 | 官方成绩处理器 |
| 血量和失败状态 | 捕获时的官方游戏状态 |
| 实际 PP | 将已填充成绩交给官方表现分计算器 |
| 全连 PP | 规则程序构造假设成绩：将 Miss 和漏打点替换为命中，恢复可达连击，重算准确率，再调用官方计算器 |
| 全完美 PP | 规则程序构造假设成绩：使用累计最大判定统计、可达连击和满准确率，再调用官方计算器 |

假设 PP 的构造方式定义在 `ScoreAnalysis.calculatePerformance`，不是客户端提供的独立预测接口。它们使用当时累计的最大判定统计，因此中途数值描述已处理部分，并不假设剩余整张谱面都完美完成。与实际客户端成绩比较时，应使用实际 PP。

[official_lazer.go](../../app/rulesets/osu/official_lazer.go) 校验物件序号和判定映射、应用快照，并发出 danser 命中通知。Great／Ok／Meh／Miss 映射为已有的 300／100／50／Miss 计数；嵌套结果驱动滑条显示和断连信息。HUD（游戏内信息显示层）没有对应字段的嵌套统计仍保留在规则程序 JSON 中。这些光标跳过常规 Go 评分路径，避免再次计分；PP 显示层读取传入的实际值和假设值。

## Mods 与协议

回放和实时适配器将 danser 的有效 Mods 参数转换为官方缩写／设置对象，并移除 danser 专用的 lazer 选择标记。[ModParser](ModParser.cs) 通过 `InstantiateValidModsForRuleset` 和 `CheckValidForGameplay` 实例化并校验覆盖参数。Mods 合法并不证明 danser 渲染完全相同：几何呈现、光标渲染和音频仍由 danser 负责。

通信结构位于 [Protocol.cs](Protocol.cs) 和 [protocol.go](../../app/rulesets/osu/lazer/protocol.go)。版本常量分别为 C# 的 `Protocol.Version` 和 [client.go](../../app/rulesets/osu/lazer/client.go) 的 `ProtocolVersion`；不兼容结构变更需同时更新。Go 会检查协议、规则集标识及源码版本是否存在，但不会自动将该版本与本地子模块比较。发现“协议兼容但规则程序过旧”仍需核对响应中的版本。

## 更新与验证边界

将子模块更新到已审查的上游提交，检查 SDK／目标框架要求及评分接口变化，重新构建规则程序和应用。解释预期值变化前，审查成绩处理器、物件、Mods、难度和表现分相关改动；子模块版本与所需适配修改一并提交。具体安装命令分别维护在[规则程序说明](README.zh-CN.md)和 [Linux 安装说明](../linux/README.zh-CN.md)。

执行 Go 协议／适配测试、规则程序构建、已知回放对照和[手动验收清单](ACCEPTANCE.zh-CN.md)。对比时固定相同的谱面字节、回放帧、Mods 参数和评分版本；核对客户端的标准化分数及本地计算版本，不以历史网站结果替代。

使用官方规则确定了计算来源，但不等于已经证明每个输入、Mods、渲染或帧时序路径。血量随判定／最终快照捕获，并非每个渲染帧连续传输；不同手打尝试的输入时刻也不同。仓库中的 Go 测试验证通信协议，尚未包含覆盖全面的、提交到仓库的实时与离线游玩样例矩阵。精确验证实时一致性需要向两条路径输入完全相同的数据流。
