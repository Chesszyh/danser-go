# Official lazer scoring integration

[简体中文](IMPLEMENTATION.zh-CN.md)

## Responsibility and source identity

Danser renders and schedules gameplay; the companion C# process executes the pinned official osu!standard rules. The original Go scoring engine remains the source-build default. The separate Linux installation seeds its own settings with the official engine selected. Engine scope and invocation are defined in the [host guide](README.md).

`third_party/osu` is a Git submodule, so a danser commit identifies the exact osu! source dependency. The build target `AddOsuSourceRevision` in [Danser.LazerRulesHost.csproj](Danser.LazerRulesHost.csproj) embeds that revision into the host assembly. Responses expose it as `engine.osuSourceRevision`. The host references `osu.Game` and `osu.Game.Rulesets.Osu` directly; danser does not maintain a translated copy of their scoring or performance formulas.

## Offline replay path

1. [ReplayController.loadOfficialReplays](../../app/dance/rcontroller.go) collects lazer replay paths and effective mods, alongside the selected original `.osu` file. Stable replay controllers keep their Go rules.
2. [lazer.Rejudge](../../app/rulesets/osu/lazer/client.go) resolves `lazer-rules-host/danser-lazer-rules` and runs a bounded worker pool. Each host receives one map/replay pair and an optional mods override. Results retain the input ordering.
3. [ReplayAnalysisGame](ReplayAnalysisGame.cs) loads a `FlatWorkingBeatmap`, wraps it in [SilentWorkingBeatmap](SilentWorkingBeatmap.cs), and decodes the `.osr` with an official `LegacyScoreDecoder` subclass. The supplied map must match the replay's map hash and the ruleset must be osu!standard.
4. An official `ReplayPlayer` creates the playable beatmap and gameplay state. Before seeking through the replay, the host subscribes to `ScoreProcessor.NewJudgement`. Every emitted result is captured, including slider components. The seek target extends past both the replay and the final object, allowing completion.
5. The host returns historical `recorded` data, newly calculated `rejudged` data and the chronological `judgements` array. Danser attaches the result to the matching cursor and applies it as its own presentation clock advances.

The replay's stored score is captured before applying mod overrides. It is retained for inspection and never substituted for the recalculated score.

## Live input path

[PlayerController](../../app/dance/pcontroller.go) prepares a full-map session when both the official engine and lazer gameplay are selected. [Player](../../app/states/player.go) starts the session after quickstart warm-up. Partial `-start` or `-end` play is rejected on this path.

The controller samples cursor position at approximately 60 Hz and sends button-state changes immediately. Small BASS clock corrections are clamped only in the outgoing timestamps to keep replay input monotonic. Danser's own clock is not changed.

[LiveSession](../../app/rulesets/osu/lazer/live.go) starts one persistent host and waits for `ready`. It then sends `frame` requests containing frame ID, time, position and left/right/smoke states. [LiveAnalysisGame](LiveAnalysisGame.cs) appends official `OsuReplayFrame` objects to an incomplete replay and lets the official player consume them. The host acknowledges processed frames and returns pending judgement events. The controller waits for that acknowledgement before applying results.

At the end, `finish` marks the replay input complete. The host returns remaining judgements and the final score in `complete`; closing the session releases the subprocess. `error` messages, invalid frame order and incompatible responses fail the official session.

## Judgements, scores and performance

[ScoreAnalysis](ScoreAnalysis.cs) is shared by offline and live play. It maps official hit objects and nested components back to danser's top-level object indices. Each event contains its part, result and maximum result, judgement time and offset, combo before/after, whether it affects score, optional hit cursor position and a score snapshot.

For every snapshot, `ScoreProcessor.PopulateScore` fills the official score fields. The host calculates difficulty with the official difficulty calculator and performance with the official performance calculator. Intermediate snapshots use the timed difficulty at or before the judged object's end; final snapshots use full-map difficulty.

| Output | Source |
| --- | --- |
| Standardised score, accuracy, combo, rank, statistics | Official score processor |
| Health and failure state | Official gameplay state at capture time |
| Actual PP | Official performance calculator with the populated score |
| Full-combo PP | Host-created hypothetical score: replace misses and missed ticks with hits, restore achievable combo, recompute accuracy, then call the official calculator |
| Perfect-play PP | Host-created hypothetical score: use accumulated maximum statistics, achievable combo and full accuracy, then call the official calculator |

The hypothetical PP variants are defined in `ScoreAnalysis.calculatePerformance`; they are not a separate client-provided forecast API. They use the maximum statistics accumulated by that point, so intermediate values describe the processed portion, not an assumed perfect completion of the whole remaining map. Actual PP is the value to compare with the actual client score.

[official_lazer.go](../../app/rulesets/osu/official_lazer.go) validates object indices and result mappings, applies snapshots, and emits danser hit notifications. Great/Ok/Meh/Miss become the existing 300/100/50/Miss counters. Nested results drive slider displays and combo-break information. Raw nested statistics remain available in the host JSON even when the HUD has no corresponding field. The ordinary Go score path is bypassed for these cursors, preventing a second scoring update. The PP overlay consumes the supplied actual and hypothetical values.

## Mods and protocol

Replay and live adapters convert danser's effective mod settings into official acronym/settings objects, removing the danser-only lazer selector. [ModParser](ModParser.cs) uses `InstantiateValidModsForRuleset` and `CheckValidForGameplay` to instantiate and validate overrides. Mod validity does not prove identical rendering in danser: geometry, cursor rendering and audio still belong to danser.

The wire schemas live in [Protocol.cs](Protocol.cs) and [protocol.go](../../app/rulesets/osu/lazer/protocol.go). Version constants are `Protocol.Version` in C# and `ProtocolVersion` in [client.go](../../app/rulesets/osu/lazer/client.go). Incompatible schema changes require updating both. Go checks the protocol, ruleset identity and presence of a source revision; it does not compare that revision with the local submodule automatically. A stale but protocol-compatible host must be detected by checking the reported revision.

## Update and verification boundaries

Update the submodule to a reviewed upstream commit, check SDK/framework requirements and changed scoring APIs, rebuild the host, then rebuild the application. Review changes to score processors, hit objects, mods, difficulty and performance calculations before interpreting changed expected values. Commit the submodule pointer and any adapter changes together. Installation and commands are maintained in the [host](README.md) and [Linux installation](../linux/README.md) guides.

Run the Go protocol/adapter tests, host build, a known replay comparison and the [manual acceptance checklist](ACCEPTANCE.md). Compare identical map bytes, replay frames, mods/settings and scoring version. Match the client's standardised score display and local calculation version rather than historical website results.

Using official rules establishes the calculation authority; it does not by itself prove every input, mod, rendering or frame-timing path. Health is captured with judgement/final snapshots, not continuously streamed every render frame. Manual live attempts have different input timing. The repository's Go tests exercise the protocol contract; they do not include a comprehensive committed live-versus-offline gameplay fixture matrix. Exact live equivalence requires driving both paths with the same input stream.
