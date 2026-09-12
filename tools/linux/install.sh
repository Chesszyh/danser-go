#!/bin/sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
app_dir="$data_home/danser-lazer"
bin_dir="$HOME/.local/bin"
build_dir="$repo_dir/dist/danser-lazer"
dotnet_cmd=${DOTNET:-dotnet}

command -v desktop-file-install >/dev/null
command -v update-desktop-database >/dev/null
command -v jq >/dev/null
cd "$repo_dir"
git submodule update --init --recursive third_party/osu
mkdir -p "$build_dir"
"$dotnet_cmd" publish tools/lazer-rules-host/Danser.LazerRulesHost.csproj \
    --configuration Release --runtime linux-x64 --self-contained true \
    --output "$build_dir/lazer-rules-host" -m:2
go build -p 2 -o "$build_dir/danser-lazer-bin" .

mkdir -p "$app_dir/settings" "$bin_dir" "$data_home/applications"
install -m 755 "$build_dir/danser-lazer-bin" "$app_dir/danser-lazer-bin"
install -m 755 tools/linux/danser-lazer "$app_dir/danser-lazer"
cp -a "$build_dir/lazer-rules-host" "$app_dir/"
cp -a assets "$app_dir/"
install -m 644 libbass.so libbass_fx.so libbassmix.so libyuv.so LICENSE CREDITS.md "$app_dir/"
install -m 644 third_party/osu/LICENCE "$app_dir/osu-LICENCE"
if [ ! -f "$app_dir/settings/default.json" ]; then
    "$app_dir/danser-lazer-bin" -noupdatecheck
    jq -s '.[0] * .[1]' "$app_dir/settings/default.json" tools/linux/settings.json \
        > "$app_dir/settings/default.json.tmp"
    mv "$app_dir/settings/default.json.tmp" "$app_dir/settings/default.json"
fi
ln -sfn "$app_dir/danser-lazer" "$bin_dir/danser-lazer"
desktop-file-install --dir="$data_home/applications" \
    --set-key=Exec --set-value="\"$bin_dir/danser-lazer\" %f" \
    --set-key=Path --set-value="$app_dir" \
    --set-key=Icon --set-value="$app_dir/assets/textures/coinbig.png" \
    tools/linux/danser-lazer.desktop
update-desktop-database "$data_home/applications"
printf 'Installed danser-lazer in %s\nLaunch it from the application menu or %s/danser-lazer.\n' "$app_dir" "$bin_dir"
