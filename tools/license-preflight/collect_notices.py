#!/usr/bin/env python3
"""Offline notice collector. Reads exact build outputs/caches; writes only --out.

Run after dotnet publish / Go build and before app signing. Never downloads,
restores packages or executes shipped binaries. Inventory is not legal clearance.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath

NOTICE = re.compile(r"(^|[._ -])(licen[cs]e|copying|copyright|notice|notices|third[-_ ]?party(?:[-_ ]?notices?)?|ofl|ufl|patents|authors)([._ -]|$)", re.I)
REQUIRED_NATIVE = ("BASS.txt", "BASSmix.txt", "BASS_FX.txt", "SDL3-LICENSE.txt", "libyuv-LICENSE.txt")
MAX_TEXT = 4 * 1024 * 1024

def sha(data):
    return hashlib.sha256(data).hexdigest()

def safe(value):
    return re.sub(r"[^A-Za-z0-9._+-]", "_", value)

def is_text(data):
    if len(data) > MAX_TEXT or b"\0" in data:
        return False
    try:
        data.decode("utf-8-sig")
        return True
    except UnicodeDecodeError:
        return False

def metadata(data):
    root = ET.fromstring(data)
    for node in root.iter():
        node.tag = node.tag.rsplit("}", 1)[-1]
    meta = root.find("metadata")
    if meta is None:
        raise ValueError("nuspec has no metadata")
    result = {key: meta.findtext(key) for key in
              ("id", "version", "authors", "copyright", "projectUrl", "licenseUrl")}
    node = meta.find("license")
    result["license"] = ({"type": node.get("type"), "value": node.text}
                         if node is not None else None)
    node = meta.find("repository")
    result["repository"] = dict(node.attrib) if node is not None else None
    return result

def json_stream(text):
    decoder = json.JSONDecoder()
    text = text.lstrip()
    while text:
        obj, end = decoder.raw_decode(text)
        yield obj
        text = text[end:].lstrip()

def go_dependencies(text):
    found = []
    for line in text.splitlines():
        fields = line.strip().split()
        if fields and fields[0] == "dep" and len(fields) >= 3:
            found.append({"path": fields[1], "version": fields[2]})
        elif fields and fields[0] == "=>" and len(fields) >= 3 and found:
            found[-1]["replacement"] = {"path": fields[1], "version": fields[2]}
    return found

def binary_strings(data):
    values = {b.decode("ascii") for b in re.findall(rb"[ -~]{12,}", data)}
    return sorted(s for s in values if s.startswith("--disable-static ") or
                  re.fullmatch(r"FFmpeg version [\w.+-]+", s) or
                  re.match(r"lib(?:avcodec|avformat|avutil|swscale) license:", s))

class Collector:
    def __init__(self, out):
        self.out = out
        out.mkdir(parents=True, exist_ok=False)
        self.records, self.gaps, self.errors, self.binaries = [], [], [], []

    def write(self, relative, data, origin):
        rel = PurePosixPath(relative)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("Unsafe output path")
        dest = self.out.joinpath(*rel.parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.read_bytes() != data:
            raise ValueError("Conflicting notice destination: " + str(rel))
        dest.write_bytes(data)
        return {"file": str(rel), "sha256": sha(data), "origin": str(origin)}

    def directory(self, folder, prefix, all_text=False):
        notices = []
        folder = folder.resolve()
        if not folder.is_dir():
            self.gaps.append("Missing directory: " + str(folder))
            return notices
        for path in sorted(folder.rglob("*")):
            if path.is_symlink() or not path.is_file() or ".git" in path.parts:
                continue
            if (all_text or NOTICE.search(path.name)) and path.stat().st_size <= MAX_TEXT:
                data = path.read_bytes()
                if is_text(data):
                    notices.append(self.write(prefix + "/" + path.relative_to(folder).as_posix(), data, path))
        return notices

    def nuget(self, folder=None, archive=None, expected=None):
        origin = str(archive or folder)
        z = zipfile.ZipFile(archive) if archive else None
        if z:
            names, read = z.namelist(), z.read
        else:
            if not folder or not folder.is_dir():
                self.gaps.append("NuGet cache unavailable: " + str(folder))
                return
            names = [p.relative_to(folder).as_posix() for p in folder.rglob("*")
                     if p.is_file() and not p.is_symlink()]
            read = lambda name: (folder / name).read_bytes()
        try:
            nuspecs = [n for n in names if n.lower().endswith(".nuspec") and "/" not in n]
            if len(nuspecs) != 1:
                self.gaps.append("Expected one root nuspec: " + origin)
                return
            meta = metadata(read(nuspecs[0]))
            key = meta["id"] + "/" + meta["version"]
            prefix = "NuGet/" + safe(meta["id"]) + "/" + safe(meta["version"])
            record = {"ecosystem": "NuGet", "key": key, "metadata": meta,
                      "notices": [], "expectedInPublish": expected}
            self.write(prefix + "/package.nuspec", read(nuspecs[0]), origin + ":" + nuspecs[0])
            explicit = meta.get("license") or {}
            explicit_name = explicit.get("value") if explicit.get("type") == "file" else None
            for name in sorted(names):
                rel = PurePosixPath(name)
                if rel.is_absolute() or ".." in rel.parts:
                    self.gaps.append("Unsafe package path: " + name)
                    continue
                if NOTICE.search(rel.name) or name == explicit_name:
                    data = read(name)
                    if is_text(data):
                        record["notices"].append(self.write(prefix + "/" + name, data, origin + ":" + name))
                if name.startswith("runtimes/osx") and name.endswith(".dylib"):
                    data = read(name)
                    self.binaries.append({"package": key, "packagePath": name,
                                          "sha256": sha(data), "size": len(data),
                                          "embeddedVersionAndLicense": binary_strings(data)})
            if not record["notices"]:
                self.gaps.append("No readable notice body in " + key +
                                 "; resolve exact source/standard licence plus copyright")
            if explicit_name and not any(n["file"] == prefix + "/" + explicit_name
                                         for n in record["notices"]):
                self.gaps.append("Declared licence file missing in " + key + ": " + explicit_name)
            if "NativeLibs" in meta["id"]:
                self.gaps.append(key + ": package MIT does not cover native FFmpeg/BASS payload")
            if archive:
                record["packageSha256"] = sha(archive.read_bytes())
            self.records.append(record)
        finally:
            if z:
                z.close()

    def finish(self):
        data = {"schemaVersion": 1, "packages": self.records, "binaries": self.binaries,
                "reviewGaps": sorted(set(self.gaps)), "fatalErrors": sorted(set(self.errors)),
                "warning": "Inventory only. Review unresolved notices and corresponding-source obligations."}
        self.write("inventory.json", (json.dumps(data, indent=2) + "\n").encode(), "generated")
        lines = ["THIRD-PARTY NOTICE INVENTORY", "", data["warning"], ""]
        for item in self.records:
            lines += [item.get("key", "Unknown component")]
            meta = item.get("metadata", {})
            for key in ("authors", "copyright", "license", "repository"):
                if meta.get(key):
                    lines.append("  " + key + ": " + str(meta[key]))
            lines += ["  notice: " + n["file"] for n in item.get("notices", [])]
            lines.append("")
        lines += ["OPEN REVIEW ITEMS"] + ["- " + g for g in sorted(set(self.gaps))]
        lines += ["", "FATAL COLLECTION ERRORS"] + ["- " + g for g in sorted(set(self.errors))]
        self.write("INDEX.txt", ("\n".join(lines) + "\n").encode(), "generated")

def read_go(a, collector):
    env = dict(os.environ, GOPROXY="off", GOSUMDB="off", GOTOOLCHAIN="local")
    try:
        build = (a.go_build_info.read_text() if a.go_build_info else
                 subprocess.check_output(["go", "version", "-m", str(a.go_binary)],
                                         text=True, env=env))
        modules_text = (a.go_module_list.read_text() if a.go_module_list else
                        subprocess.check_output(["go", "list", "-mod=readonly", "-m", "-json", "all"],
                                                cwd=a.repo, text=True, env=env))
        goroot = a.go_root or Path(subprocess.check_output(["go", "env", "GOROOT"],
                                                           text=True, env=env).strip())
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        collector.errors.append("Go inventory failed: " + str(exc))
        return
    collector.write("Evidence/go-build-info.txt", build.encode(), "go version -m")
    collector.write("Evidence/go-module-list.json", modules_text.encode(), "go list -m")
    collector.directory(goroot, "GoRuntime")
    by_key = {}
    for mod in json_stream(modules_text):
        actual = mod.get("Replace") or mod
        by_key[(actual["Path"], actual.get("Version", "(devel)"))] = actual
    for dep in go_dependencies(build):
        actual = dep.get("replacement") or dep
        found = by_key.get((actual["path"], actual["version"]))
        key = actual["path"] + "@" + actual["version"]
        if not found or not found.get("Dir"):
            collector.gaps.append("Missing cached Go source: " + key)
            continue
        notices = collector.directory(Path(found["Dir"]), "GoModules/" + safe(key))
        collector.records.append({"ecosystem": "Go", "key": key, "original": dep,
                                  "sourceDirectory": found["Dir"], "notices": notices})
        if not notices:
            collector.gaps.append("No readable Go module notice: " + key)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True, type=Path, help="Must not already exist")
    p.add_argument("--repo", type=Path)
    p.add_argument("--host", type=Path, help="Published lazer-rules-host directory")
    p.add_argument("--nuget-root", type=Path, default=Path.home() / ".nuget/packages")
    p.add_argument("--nupkg", type=Path, action="append", default=[])
    p.add_argument("--go-binary", type=Path)
    p.add_argument("--go-build-info", type=Path)
    p.add_argument("--go-module-list", type=Path)
    p.add_argument("--go-root", type=Path)
    p.add_argument("--native-notices", type=Path)
    p.add_argument("--font-notices", type=Path, default=Path(__file__).parent / "font-notices")
    p.add_argument("--ffmpeg-notices", type=Path, default=Path(__file__).parent / "ffmpeg-notices")
    p.add_argument("--strict-review", action="store_true", help="Also fail on unresolved review items")
    a = p.parse_args()
    c = Collector(a.out)
    for nupkg in a.nupkg:
        c.nuget(archive=nupkg)
    if a.repo:
        for path in ("LICENSE", "CREDITS.md", "go.mod", "go.sum", ".gitmodules",
                     "third_party/osu/LICENCE", "third_party/osu/global.json"):
            src = a.repo / path
            if src.is_file():
                c.write("Project/" + path, src.read_bytes(), src)
    if a.native_notices:
        for name in REQUIRED_NATIVE:
            source = a.native_notices / name
            if not source.is_file() or not source.stat().st_size:
                c.errors.append("Missing required native notice: " + name)
        c.directory(a.native_notices, "Native", all_text=True)
    elif a.host:
        c.errors.append("--native-notices is required for release collection")
    for name in ("Quicksand-OFL.txt", "Ubuntu-UFL.txt", "FontAwesome-6.1.1-LICENSE.txt", "COPYRIGHTS.txt", "SOURCES.json"):
        if not (a.font_notices / name).is_file():
            c.errors.append("Missing required font notice: " + name)
    if a.repo and (a.font_notices / "SOURCES.json").is_file():
        for font in json.loads((a.font_notices / "SOURCES.json").read_text()):
            asset = a.repo / font["assetPath"]
            if not asset.is_file() or sha(asset.read_bytes()) != font["assetSha256"]:
                c.errors.append("Font changed or absent; reverify notice: " + font["assetPath"])
    c.directory(a.font_notices, "Fonts", all_text=True)
    if a.host:
        dep_files = sorted(a.host.glob("*.deps.json"))
        if len(dep_files) != 1:
            c.errors.append("Expected one published host .deps.json")
        else:
            deps = json.loads(dep_files[0].read_text())
            c.write("Evidence/" + dep_files[0].name, dep_files[0].read_bytes(), dep_files[0])
            for key, details in sorted(deps.get("libraries", {}).items()):
                if details.get("type") not in ("package", "runtimepack"):
                    continue
                name, version = key.rsplit("/", 1)
                name = name.removeprefix("runtimepack.")
                c.nuget(folder=a.nuget_root / name.lower() / version.lower(), expected=key)
        ffmpeg_present = False
        for path in sorted(a.host.rglob("*")):
            if path.is_file() and not path.is_symlink():
                data = path.read_bytes()
                if re.match(r"lib(avcodec|avformat|avutil|swscale)\.", path.name):
                    ffmpeg_present = True
                c.binaries.append({"publishedPath": path.relative_to(a.host).as_posix(),
                                   "sha256": sha(data), "size": len(data),
                                   "embeddedVersionAndLicense": binary_strings(data)
                                   if path.suffix == ".dylib" else []})
        if ffmpeg_present:
            for name in ("COPYING.LGPLv2.1", "FFmpeg-4.3.3-NOTICE.txt"):
                path = a.ffmpeg_notices / name
                if not path.is_file() or not path.stat().st_size:
                    c.errors.append("Missing required FFmpeg notice: " + name)
            c.directory(a.ffmpeg_notices, "Native/FFmpeg", all_text=True)
            manifest = a.ffmpeg_notices / "SOURCES.json"
            if not manifest.is_file():
                c.errors.append("Missing FFmpeg exact-source manifest")
            else:
                expected = json.loads(manifest.read_text())
                for lib in expected["binaries"]:
                    matches = list(a.host.rglob(lib["filename"]))
                    if len(matches) != 1 or sha(matches[0].read_bytes()) != lib["sha256"]:
                        c.errors.append("FFmpeg binary differs from source manifest; inspect before accepting notice: " + lib["filename"])
        c.directory(a.host, "PublishedHostNotices")
    if a.go_binary or (a.go_build_info and a.go_module_list):
        read_go(a, c)
    elif a.host:
        c.errors.append("Go inventory required: provide --go-binary or both saved Go inputs")
    c.finish()
    print(json.dumps({"output": str(a.out), "packages": len(c.records),
                      "reviewItems": len(set(c.gaps)), "fatalErrors": len(set(c.errors))}))
    return 2 if c.errors or (a.strict_review and c.gaps) else 0

if __name__ == "__main__":
    sys.exit(main())
