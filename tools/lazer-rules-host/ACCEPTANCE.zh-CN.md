# osu!lazer 手动验收

[English](ACCEPTANCE.md)

在 danser 仓库根目录运行命令，使用新构建的 `danser-acceptance` 和相邻的 `lazer-rules-host` 目录。

## 准备可比较的成绩

- [ ] 记录官方客户端版本及发布通道。运行 `git -C third_party/osu rev-parse HEAD` 获取规则程序的源码版本。精确源码对齐需要用该版本构建客户端；若中间改动不影响被测规则，也可以使用相应发布版。
- [ ] 在官方客户端游玩一张 osu!standard 谱面，导出 `.osr` 回放；danser 使用完全相同的 `.osu`。比较同一份回放，而不是两次独立手打。
- [ ] 保留回放中的 Mods（游戏调整项）及全部参数。官方客户端使用标准化分数显示，不使用经典分数。记录判定数量、准确率、最大连击、分数、评级和本地计算的 PP（Performance Points，表现分）。

## 单回放

```bash
./danser-acceptance -noupdatecheck -replay=/path/to/score.osr \
  -sPatch='{"Gameplay":{"LazerRulesEngine":"official"},"Graphics":{"VSync":false,"FPSCap":120}}'

./lazer-rules-host/danser-lazer-rules rejudge \
  --beatmap /path/to/map.osu --replay /path/to/score.osr > /tmp/danser-score.json
jq '{engine, recorded, rejudged}' /tmp/danser-score.json
```

- [ ] 日志包含 `Using official osu!lazer rules from`，并显示预期源码版本。
- [ ] 最终分数、最大连击、评级和各判定数量与官方客户端完全一致。准确率与 PP 在显示精度内一致；排查舍入时使用 JSON 原始值。
- [ ] 将 danser 与 `rejudged` 比较；`recorded` 是回放保存的历史结果，不会重算。网站 PP 可能采用不同计算版本。全连和全完美 PP 是假设成绩估算，不是实际成绩 PP。
- [ ] 对可疑物件查看 JSON 的 `judgements`，核对物件序号、组成部分、结果、时刻、连击及成绩快照。滑条头、打点、折返和尾部分别检查；部分嵌套判定数量不会显示在 danser 的 HUD（游戏内信息显示层）中。

使用以下样例重复检查，一份回放可以覆盖多行：

| 样例 | 检查内容 |
| --- | --- |
| 无 Mod，圆圈，混合 300／100／50／Miss | 时刻、数量、准确率、分数、连击 |
| 滑条，漏接头／打点／折返／尾部 | 嵌套判定、断连、准确率 |
| 转盘 | 完成判定和奖励分 |
| 全连与全完美 | 最大连击、评级、最终 PP |
| Hidden／Hard Rock | 可见性或几何变化及计分 |
| Double Time／Half Time 自定义速度 | 精确参数及时间倍率 |
| Difficulty Adjust | 难度参数一致 |
| Classic | 滑条准确率及 PP 计算 |
| No Fail 与失败成绩 | 失败状态、分数推进、最终 PP |
| Relax | 自动点击与判定结果 |

## 其他入口

```bash
./danser-acceptance -noupdatecheck -md5=<beatmap-md5> \
  -knockout2='["/path/to/first.osr","/path/to/second.osr"]' \
  -sPatch='{"Gameplay":{"LazerRulesEngine":"official"},"Graphics":{"VSync":false,"FPSCap":120}}'

./danser-acceptance -noupdatecheck -play -quickstart -mods=LZ \
  -md5=<beatmap-md5> \
  -sPatch='{"Gameplay":{"LazerRulesEngine":"official"},"Graphics":{"VSync":false,"FPSCap":120}}'
```

- [ ] `-knockout2`：使用同一谱面的两份 lazer 回放；每位玩家的结果均与其单回放运行一致。
- [ ] `-knockout`：将副本放入 `replays/`，使用 `-knockout -md5=<beatmap-md5>` 及相同设置补丁运行。该入口会将回放移动到按谱面分类的子目录。
- [ ] `-play`：完成整张谱面，再测试失败与退出。检查输入响应、判定显示、分数、连击、血量及 PP，且无规则程序或时间回拨错误。`LZ` 选择 lazer 模式，可按需添加其他 Mods。
- [ ] 官方 `-play` 拒绝 `-start`／`-end`；将 `Gameplay.LazerRulesEngine` 设为 `danser` 后仍可局部游玩。
- [ ] 退出后，`pgrep -af 'danser-lazer-rules|danser-acceptance'` 不再显示残留的游玩或规则进程。

手动游玩检查输入和显示链路，不能证明两次独立操作的时序完全一致；严格时序验证需要向两种实现提供完全相同的输入帧。

发现差异时，保留 `.osu`、`.osr`、客户端版本、完整启动命令、`danser.log`、规则程序 JSON，以及首个差异物件／时刻或最终字段。
