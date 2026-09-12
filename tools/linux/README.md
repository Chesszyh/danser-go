# Install danser-lazer on Linux

[简体中文](README.zh-CN.md)

This installs a separate Linux x86-64 application for the current user. The application menu entry and command are named `danser-lazer`; launching without arguments opens the existing danser launcher. The initial settings enable official lazer rules and cap rendering at 120 FPS. Existing installations retain their settings when updated.

Install the [Go/native build dependencies](../../README.md#building-the-project), the SDK selected by `third_party/osu/global.json`, `desktop-file-utils`, and `jq`. Run the installer from a graphical desktop session: on first installation it uses danser's settings initialization to detect the primary monitor resolution before applying the official-engine preset. From the repository root, run:

```bash
sh tools/linux/install.sh
```

If the SDK is installed outside `PATH`, set `DOTNET` to its executable. If `/tmp` has insufficient space, point `GOTMPDIR` at an existing directory with enough disk space. The installer builds the Go application and publishes the rules host with its own .NET runtime.

```bash
DOTNET=/path/to/dotnet GOTMPDIR=/path/to/build-temp sh tools/linux/install.sh
```

Files are installed to `${XDG_DATA_HOME:-$HOME/.local/share}/danser-lazer`, with a command symlink in `$HOME/.local/bin` and a desktop entry in the XDG applications directory. Settings, database and generated output belong to that application directory. The existing danser-go installation is independent. The installer does not copy its settings, credentials or database.

Open **danser-lazer** from the application menu, or run:

```bash
danser-lazer
danser-lazer /path/to/replay.osr
danser-lazer -play -mods=LZ -md5=<beatmap-md5>
```

Add `$HOME/.local/bin` to `PATH` if needed, or invoke the command there directly. Select the Songs and Skins directories in the launcher. A lazer export with separate `beatmap/` and `audio/` folders must be arranged into a danser Songs subdirectory with the `.osu` file and its referenced audio together. Preserve the `.osu` bytes so replay matching still works.

The launcher uses the installed configuration's engine choice. For live official scoring, select lazer gameplay (`LZ`); stable replays and non-lazer modes retain their existing scoring path. See the [rules host guide](../lazer-rules-host/README.md) for engine scope and the [acceptance checklist](../lazer-rules-host/ACCEPTANCE.md) for comparison with the client.

Rerun the installer after updating the checkout to rebuild and update the application. To uninstall, remove the `danser-lazer.desktop` entry, the `$HOME/.local/bin/danser-lazer` symlink and the installed `danser-lazer` directory. That directory also contains its settings and generated recordings; retain those if needed.
