# Official osu!lazer rules host

This host runs osu!standard replay and live input through the official osu!lazer ruleset. Danser keeps its existing renderer and cursor handling, while the host supplies authoritative judgement events, score, combo, health, rank, and performance points (PP).

The osu! source is pinned by the `third_party/osu` Git submodule. Every response includes that source revision. Danser rejects an incompatible response or host failure instead of silently switching scoring engines.

## Current scope

Official rules are available for local lazer replays loaded with `-replay`, `-knockout`, or `-knockout2`, and for full-map lazer `-play`. Knockout replays are analysed by at most two host processes at once to bound memory use. Replay overrides and live `-mods` / `-mods2` selections are converted to osu!'s acronym/settings representation and validated by the official ruleset.

Live play streams frames to one persistent host and waits for each frame acknowledgement before publishing official judgements. `-start` and `-end` are rejected only when the official live engine is selected because a trimmed danser beatmap is not an official full-map score. The built-in engine retains the existing partial-play behaviour.

## Build

The host requires the .NET 8 SDK.

```bash
git submodule update --init --recursive third_party/osu
dotnet publish tools/lazer-rules-host/Danser.LazerRulesHost.csproj \
  --configuration Release \
  --output lazer-rules-host
go build
```

Set `Gameplay.LazerRulesEngine` to `official` in the selected settings file. For a one-off run, use:

```bash
./danser-go -replay=/path/to/replay.osr \
  -sPatch='{"Gameplay":{"LazerRulesEngine":"official"}}'

./danser-go -play -mods=LZHD \
  -sPatch='{"Gameplay":{"LazerRulesEngine":"official"}}' \
  -md5=<beatmap-md5>
```

The built-in engine remains the default so existing source builds and non-replay modes keep working without the .NET host.

## Verify independently

The host prints one JSON document to standard output:

```bash
./lazer-rules-host/danser-lazer-rules rejudge \
  --beatmap /path/to/map.osu \
  --replay /path/to/replay.osr \
  --mods-json '[{"acronym":"HD"}]'
```

Omit `--mods-json` to use the replay's original mods. `recorded` is always the score stored in the replay. `rejudged`, per-judgement score snapshots, and actual, full-combo, and perfect-play PP are calculated by the pinned osu! source. The `live` command uses a JSON Lines request/acknowledgement protocol on standard input and output; danser owns that protocol and users normally do not invoke it directly.

## Update osu!lazer

Review and pin an exact upstream revision, rebuild the host, then run both the Go and host checks:

```bash
git -C third_party/osu fetch origin
git -C third_party/osu checkout <reviewed-osu-revision>
dotnet build tools/lazer-rules-host/Danser.LazerRulesHost.csproj
go test ./app/rulesets/osu/...
```

Protocol changes belong in `Protocol.cs` and `app/rulesets/osu/lazer/protocol.go`. Increase `ProtocolVersion` on both sides for incompatible changes.
