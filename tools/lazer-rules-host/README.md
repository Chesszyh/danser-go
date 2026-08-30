# Official osu!lazer rules host

This host runs an osu!standard replay through the official osu!lazer ruleset. Danser keeps its existing renderer and replay cursor, while the host supplies authoritative judgement events, score, combo, health, rank, and performance points (PP).

The osu! source is pinned by the `third_party/osu` Git submodule. Every response includes that source revision. Danser rejects an incompatible response or host failure instead of silently switching scoring engines.

## Current scope

Official rules are available for one local lazer replay loaded with `-replay`. The replay's original mods are required. Live play, knockout or other multi-replay modes, and `-mods`/`-mods2` overrides still use the built-in engine.

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
```

The built-in engine remains the default so existing source builds and non-replay modes keep working without the .NET host.

## Verify independently

The host prints one JSON document to standard output:

```bash
./lazer-rules-host/danser-lazer-rules rejudge \
  --beatmap /path/to/map.osu \
  --replay /path/to/replay.osr
```

`recorded` is the score stored in the replay. `rejudged` and `judgements` are calculated by the pinned osu! source.

## Update osu!lazer

Review and pin an exact upstream revision, rebuild the host, then run both the Go and host checks:

```bash
git -C third_party/osu fetch origin
git -C third_party/osu checkout <reviewed-osu-revision>
dotnet build tools/lazer-rules-host/Danser.LazerRulesHost.csproj
go test ./app/rulesets/osu/...
```

Protocol changes belong in `Protocol.cs` and `app/rulesets/osu/lazer/protocol.go`. Increase `ProtocolVersion` on both sides for incompatible changes.
