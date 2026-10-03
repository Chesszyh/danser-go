#!/bin/sh

set -eu

if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
	echo "The macOS distribution must be built on Apple Silicon macOS" >&2
	exit 1
fi

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
build_dir="$repo_dir/dist/build-macos"
app_dir="$build_dir/danser.app"
macos_dir="$app_dir/Contents/MacOS"
frameworks_dir="$app_dir/Contents/Frameworks"
resources_dir="$app_dir/Contents/Resources"
deps_dir=${DANSER_MACOS_DEPS_DIR:-"$repo_dir/.deps/macos"}
deps_dir=$(CDPATH= cd -- "$deps_dir" && pwd)
export DANSER_MACOS_DEPS_DIR="$deps_dir"
dotnet_cmd=${DOTNET:-dotnet}
version=${1:-dev-macos}
bundle_version=${2:-0.0.0}
deployment_target=15.0

for tool in go git codesign iconutil sips python3; do
	if ! command -v "$tool" >/dev/null 2>&1; then
		echo "Required build tool is missing: $tool" >&2
		exit 1
	fi
done

if ! command -v "$dotnet_cmd" >/dev/null 2>&1; then
	echo "Required build tool is missing: $dotnet_cmd" >&2
	exit 1
fi

commit_hash=$(git -C "$repo_dir" rev-parse HEAD)

for library in libSDL3.dylib libbass.dylib libbass_fx.dylib libbassmix.dylib libyuv.a; do
	if [ ! -f "$deps_dir/lib/$library" ]; then
		echo "Missing $deps_dir/lib/$library; run tools/macos-deps.sh first" >&2
		exit 1
	fi
done

git -C "$repo_dir" submodule update --init --recursive third_party/osu
cd "$repo_dir"

rm -rf "$app_dir"
mkdir -p "$macos_dir" "$frameworks_dir" "$resources_dir"

(
	cd "$repo_dir/third_party/osu"
	DOTNET_CLI_TELEMETRY_OPTOUT=1 "$dotnet_cmd" publish \
		"$repo_dir/tools/lazer-rules-host/Danser.LazerRulesHost.csproj" \
		--configuration Release \
		--runtime osx-arm64 \
		--self-contained true \
		--output "$macos_dir/lazer-rules-host" \
		-m:2
)

if [ ! -x "$macos_dir/lazer-rules-host/danser-lazer-rules" ]; then
	echo "Official osu!lazer rules host was not published" >&2
	exit 1
fi

MACOSX_DEPLOYMENT_TARGET="$deployment_target" \
	CGO_CFLAGS="-O2 -g -mmacosx-version-min=$deployment_target" \
	CGO_CXXFLAGS="-O2 -g -mmacosx-version-min=$deployment_target" \
	CGO_LDFLAGS="-mmacosx-version-min=$deployment_target" \
	DANSER_MACOS_RPATH="@executable_path/../Frameworks" \
	DANSER_MACOS_GO_TAGS="exclude_cimgui_glfw exclude_cimgui_sdli" \
	"$repo_dir/tools/macos-go.sh" build \
	-trimpath \
	-ldflags "-s -w -X github.com/wieku/danser-go/build.VERSION=$version -X github.com/wieku/danser-go/build.Stream=Release -X github.com/wieku/danser-go/build.CommitHash=$commit_hash" \
	-o "$macos_dir/danser" .
cp "$macos_dir/danser" "$macos_dir/danser-cli"

go run tools/assets/assets.go "$repo_dir" "$macos_dir"
cp "$deps_dir/lib/libSDL3.dylib" "$frameworks_dir/"
cp "$deps_dir/lib/libbass.dylib" "$frameworks_dir/"
cp "$deps_dir/lib/libbass_fx.dylib" "$frameworks_dir/"
cp "$deps_dir/lib/libbassmix.dylib" "$frameworks_dir/"
cp "$repo_dir/LICENSE" "$repo_dir/CREDITS.md" "$resources_dir/"
cp "$repo_dir/third_party/osu/LICENCE" "$resources_dir/osu-LICENCE"
cp -R "$deps_dir/licenses" "$resources_dir/ThirdPartyNotices"
rm -rf "$build_dir/collected-notices"
rm -f "$build_dir/notices-incomplete"
if ! python3 "$repo_dir/tools/license-preflight/collect_notices.py" \
	--repo "$repo_dir" --host "$macos_dir/lazer-rules-host" \
	--go-binary "$macos_dir/danser" --native-notices "$deps_dir/licenses" \
	--go-root "$(go env GOROOT)" \
	--out "$build_dir/collected-notices"; then
	echo "Dependency notice collection failed; runtime diagnostics can continue, but archiving/release is blocked" >&2
	touch "$build_dir/notices-incomplete"
fi
cp -R "$build_dir/collected-notices" "$resources_dir/CollectedThirdPartyNotices"

iconset_dir="$build_dir/danser.iconset"
rm -rf "$iconset_dir"
mkdir -p "$iconset_dir"
cp "$repo_dir/assets/textures/dansercoin16.png" "$iconset_dir/icon_16x16.png"
cp "$repo_dir/assets/textures/dansercoin32.png" "$iconset_dir/icon_16x16@2x.png"
cp "$repo_dir/assets/textures/dansercoin32.png" "$iconset_dir/icon_32x32.png"
cp "$repo_dir/assets/textures/dansercoin64.png" "$iconset_dir/icon_32x32@2x.png"
cp "$repo_dir/assets/textures/dansercoin128.png" "$iconset_dir/icon_128x128.png"
cp "$repo_dir/assets/textures/dansercoin256.png" "$iconset_dir/icon_128x128@2x.png"
cp "$repo_dir/assets/textures/dansercoin256.png" "$iconset_dir/icon_256x256.png"
sips -z 512 512 "$repo_dir/assets/textures/dansercoin256.png" --out "$iconset_dir/icon_256x256@2x.png" >/dev/null
sips -z 512 512 "$repo_dir/assets/textures/dansercoin256.png" --out "$iconset_dir/icon_512x512.png" >/dev/null
sips -z 1024 1024 "$repo_dir/assets/textures/dansercoin256.png" --out "$iconset_dir/icon_512x512@2x.png" >/dev/null
iconutil -c icns "$iconset_dir" -o "$resources_dir/danser.icns"
rm -rf "$iconset_dir"

cat >"$app_dir/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDisplayName</key>
	<string>danser</string>
	<key>CFBundleExecutable</key>
	<string>danser</string>
	<key>CFBundleIdentifier</key>
	<string>com.github.wieku.danser-go</string>
	<key>CFBundleIconFile</key>
	<string>danser.icns</string>
	<key>CFBundleInfoDictionaryVersion</key>
	<string>6.0</string>
	<key>CFBundleName</key>
	<string>danser</string>
	<key>CFBundlePackageType</key>
	<string>APPL</string>
	<key>CFBundleShortVersionString</key>
	<string>$bundle_version</string>
	<key>CFBundleVersion</key>
	<string>$bundle_version</string>
	<key>LSApplicationCategoryType</key>
	<string>public.app-category.entertainment</string>
	<key>LSMinimumSystemVersion</key>
	<string>$deployment_target</string>
	<key>NSHighResolutionCapable</key>
	<true/>
	<key>NSPrincipalClass</key>
	<string>NSApplication</string>
</dict>
</plist>
EOF

plutil -lint "$app_dir/Contents/Info.plist"
codesign --force --deep --sign - "$app_dir"
codesign --verify --deep --strict --verbose=2 "$app_dir"

echo "$app_dir"
