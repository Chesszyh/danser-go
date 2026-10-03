#!/usr/bin/env python3
"""Package exact verified macOS build sources; no native build or rights clearance.
Only --fetch permits downloads, from the checked-in SHA256-pinned manifest.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from urllib.parse import urlparse


def check(condition, message):
    if not condition:
        raise ValueError(message)


def run(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True,
        env=dict(os.environ, GOTOOLCHAIN="local", GOPROXY="off", GOSUMDB="off")).strip()


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def relative(value):
    p = PurePosixPath(value)
    check(value and not p.is_absolute() and all(x not in ("..", ".git") for x in p.parts),
          "Unsafe source path: " + value)
    return p


def safe_link(root, destination, target):
    check(not os.path.isabs(target), "Absolute symlink: " + str(destination))
    resolved = (destination.parent / target).resolve()
    check(resolved == root.resolve() or root.resolve() in resolved.parents,
          "Symlink escapes source component: " + str(destination))
    os.symlink(target, destination)


def copy_tree(source, destination, excluded_roots=()):
    """Copy one specifically selected source tree, never a whole cache or home."""
    check(source.is_dir() and not source.is_symlink(), "Missing/linked source directory: " + str(source))
    destination.mkdir(parents=True, exist_ok=True)
    for p in sorted(source.rglob("*")):
        rel = p.relative_to(source)
        if rel.parts[0] in excluded_roots:
            continue
        if any(x in (".git", "__pycache__", ".DS_Store") for x in rel.parts):
            continue
        check(not p.is_symlink(), "Unexpected symlink in copied source: " + str(p))
        target = destination / rel
        if p.is_dir():
            target.mkdir(exist_ok=True)
        else:
            check(p.is_file(), "Unsupported source file: " + str(p))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, target)
            target.chmod(0o755 if p.stat().st_mode & 0o111 else 0o644)


def export_git(repo, destination, expected=None):
    """Export all tracked blobs, unaffected by git-archive export-ignore rules."""
    commit = run("git", "-C", str(repo), "rev-parse", "HEAD")
    check(expected is None or commit == expected, "Git source revision mismatch: " + str(repo))
    check(not run("git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"),
          "Tracked Git source is dirty: " + str(repo))
    destination.mkdir(parents=True, exist_ok=True)
    entries = subprocess.check_output(["git", "-C", str(repo), "ls-tree", "-rz", "HEAD"]).split(b"\0")
    result = {"commit": commit, "tree": run("git", "-C", str(repo), "rev-parse", "HEAD^{tree}"), "submodules": {}}
    with subprocess.Popen(["git", "-C", str(repo), "cat-file", "--batch"],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE) as process:
        try:
            for entry in entries:
                if not entry:
                    continue
                meta, name = entry.split(b"\t", 1)
                mode, kind, oid = meta.split()
                rel = relative(os.fsdecode(name))
                target = destination / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                if mode == b"160000":
                    check(not (repo / rel).is_symlink(), "Linked submodule checkout")
                    result["submodules"][str(rel)] = export_git(repo / rel, target, oid.decode())
                    continue
                check(kind == b"blob" and mode in (b"100644", b"100755", b"120000"),
                      "Unsupported Git tree entry: " + str(rel))
                process.stdin.write(oid + b"\n")
                process.stdin.flush()
                header = process.stdout.readline().split()
                check(len(header) == 3 and header[0] == oid and header[1] == b"blob", "Git blob read failed")
                data = process.stdout.read(int(header[2]))
                check(process.stdout.read(1) == b"\n", "Git blob framing failed")
                if mode == b"120000":
                    safe_link(destination, target, os.fsdecode(data))
                else:
                    target.write_bytes(data)
                    target.chmod(0o755 if mode == b"100755" else 0o644)
        finally:
            process.stdin.close()
        check(process.wait() == 0, "Git blob export failed")
    return result


def go_dependencies(text):
    found = []
    for line in text.splitlines():
        fields = line.strip().split()
        if fields and fields[0] == "dep" and len(fields) >= 3:
            found.append({"path": fields[1], "version": fields[2], "sum": fields[3] if len(fields) > 3 else ""})
        elif fields and fields[0] == "=>" and len(fields) >= 3 and found:
            found[-1]["replacement"] = {"path": fields[1], "version": fields[2],
                                        "sum": fields[3] if len(fields) > 3 else ""}
    return found


def escape_module(value):
    return "".join("!" + c.lower() if "A" <= c <= "Z" else c for c in value)


def package_go(inventory, evidence, cache, destination):
    deps = go_dependencies(evidence)
    expected = {(d.get("replacement") or d)["path"] + "@" + (d.get("replacement") or d)["version"]: d for d in deps}
    records = [r for r in inventory["packages"] if r.get("ecosystem") == "Go"]
    check(expected and len(records) == len(expected) and {r["key"] for r in records} == set(expected),
          "Go source inventory does not cover every linked dependency")
    result = []
    for record in sorted(records, key=lambda r: r["key"]):
        dep = expected[record["key"]]
        actual = dep.get("replacement") or dep
        check(actual["version"].startswith("v"), "Local/unversioned Go replacement needs explicit source review")
        cache_rel = relative(escape_module(actual["path"]) + "@" + escape_module(actual["version"]))
        source = Path(record["sourceDirectory"])
        check(source.resolve() == (cache / cache_rel).resolve() and cache.resolve() in source.resolve().parents,
              "Go source directory is outside its exact module-cache location: " + record["key"])
        copy_tree(source, destination / cache_rel)
        metadata = cache / "cache/download" / escape_module(actual["path"]) / "@v"
        metadata_files = []
        for suffix in (".mod", ".info", ".ziphash"):
            item = metadata / (escape_module(actual["version"]) + suffix)
            if item.exists():
                check(item.is_file() and not item.is_symlink(), "Linked Go module metadata is unsafe")
                if suffix == ".ziphash" and actual["sum"]:
                    check(item.read_text().strip() == actual["sum"], "Go cached module sum differs from binary")
                target = destination.parent / "go-module-metadata" / cache_rel / item.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(item, target)
                metadata_files.append(target.relative_to(destination.parent).as_posix())
        result.append({"key": record["key"], "original": dep, "directory": "go-modules/" + str(cache_rel),
                       "metadataFiles": metadata_files})
    return result


def package_sdl(archive, source, destination, checksum):
    check(digest(archive) == checksum, "SDL archive hash mismatch")
    destination.mkdir(parents=True)
    included = set()
    with tarfile.open(archive, "r:gz") as tar:
        links = []
        for member in tar:
            path = relative(member.name)
            check(path.parts[0] == source.name, "Unexpected SDL source archive root")
            if len(path.parts) == 1:
                continue
            rel = Path(*path.parts[1:])
            target, original = destination / rel, source / rel
            included.add(rel.as_posix())
            # Archives may omit directory members while retaining their files.
            # Count only the actual ancestors implied by each pinned member,
            # and still reject source parents replaced with symlinks.
            for parent in rel.parents:
                if parent == Path("."):
                    continue
                original_parent = source / parent
                check(original_parent.is_dir() and not original_parent.is_symlink(),
                      "SDL source directory differs: " + str(parent))
                included.add(parent.as_posix())
            if member.isdir():
                check(original.is_dir() and not original.is_symlink(), "SDL source directory differs: " + str(rel))
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                check(original.is_file() and not original.is_symlink(), "SDL source file missing/linked: " + str(rel))
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as incoming, target.open("wb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
                check(digest(original) == digest(target), "Built SDL source differs from pinned archive: " + str(rel))
                target.chmod(0o755 if member.mode & 0o111 else 0o644)
            elif member.issym():
                check(original.is_symlink() and os.readlink(original) == member.linkname,
                      "Built SDL source link differs: " + str(rel))
                links.append((target, member.linkname))
            else:
                raise ValueError("Unsupported SDL archive member: " + member.name)
        for target, link in links:
            target.parent.mkdir(parents=True, exist_ok=True)
            safe_link(destination, target, link)
    extra = {p.relative_to(source).as_posix() for p in source.rglob("*")} - included - {".archive-sha256"}
    check(not extra, "Unexpected files in built SDL source: " + str(sorted(extra)[:5]))


def source_archive(item, cache, destination, fetch):
    rel = relative(item["file"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    candidate = cache / rel if cache else None
    if candidate and candidate.is_file() and not candidate.is_symlink():
        shutil.copyfile(candidate, destination)
    else:
        check(fetch, "Missing source archive; provide --archives-cache or --fetch: " + str(rel))
        parsed = urlparse(item["url"])
        check(parsed.scheme == "https" and parsed.hostname in ("ffmpeg.org", "codeload.github.com")
              and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment,
              "Unapproved source URL")
        subprocess.run(["curl", "--fail", "--location", "--proto", "=https", "--proto-redir", "=https",
                        "--retry", "3", "--connect-timeout", "20", "--max-time", "600",
                        item["url"], "--output", str(destination)], check=True)
    check(re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) and digest(destination) == item["sha256"],
          "Source archive SHA256 mismatch: " + str(rel))


def check_host_sources(inventory, materials):
    """Match source mappings to this build's pre-signing published-binary evidence."""
    packages = {r["key"]: r for r in inventory["packages"] if r.get("ecosystem") == "NuGet"}
    binaries = {Path(b["publishedPath"]).name: b["sha256"] for b in inventory.get("binaries", [])
                if "publishedPath" in b}
    ffmpeg = json.loads((materials / "ffmpeg-notices/SOURCES.json").read_text())
    check(packages.get(ffmpeg["nugetPackage"], {}).get("packageSha256") == ffmpeg["nugetPackageSha256"],
          "FFmpeg source mapping does not match actual NuGet package")
    for lib in ffmpeg["binaries"]:
        check(binaries.get(lib["filename"]) == lib["sha256"], "FFmpeg binary/source mapping changed")
    lgpl = json.loads((materials / "lgpl-sources/SOURCES.json").read_text())
    for component in lgpl["packages"]:
        key = component["id"] + "/" + component["version"]
        check(packages.get(key, {}).get("packageSha256") == component["packageSha256"],
              "LGPL package/source mapping changed: " + key)
        check(any(binaries.get(Path(asset["path"]).name) == asset["sha256"] for asset in component["assets"]),
              "LGPL published DLL/source mapping changed: " + key)


def file_manifest(root):
    return [{"path": p.relative_to(root).as_posix(),
             **({"symlink": os.readlink(p)} if p.is_symlink() else {"sha256": digest(p), "bytes": p.stat().st_size})}
            for p in sorted(root.rglob("*")) if p.is_file() or p.is_symlink()]


def package_resources(source, kit, destination):
    """Audit and stage only modified source, never original packages or Git history."""
    check(source.is_dir() and not source.is_symlink(), "Resource source must be a real directory")
    destination.mkdir(parents=True)
    lock_path = kit / "pinned-resource-lock.json.gz"
    if not lock_path.exists():
        lock_path = kit / "pinned-resource-lock.json"
    locked_bytes = lock_path.read_bytes()
    if lock_path.suffix == ".gz":
        locked_bytes = gzip.decompress(locked_bytes)
    lock = json.loads(locked_bytes)
    # Root legal/readme files are outside the font generator's project audit.
    for name in ("LICENCE.md", "README.md"):
        path = source / name
        check(path.is_file() and not path.is_symlink(), "Missing root resource notice: " + name)
        data = path.read_bytes()
        expected = lock["files"][name]
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        check(len(data) == expected["size"] and blob == expected["git_blob_sha1"],
              "Resource root notice differs from pinned source: " + name)
        (destination / name).write_bytes(data)
    # Build output is excluded only at the project's known bin/ and obj/ roots.
    # All other project files are copied, so audit detects unexpected backups.
    copy_tree(source / "osu.Game.Resources", destination / "osu.Game.Resources", ("bin", "obj"))
    generator = kit / "replace_restricted_fonts.py"
    result = json.loads(subprocess.check_output([sys.executable, "-B", str(generator),
                                                "audit", str(destination)], text=True))
    check(result.get("status") == "passed" and result.get("restricted_original_payloads") == 0,
          "Modified resource source audit failed")
    tools = destination / "replacement-tools"
    tools.mkdir()
    for name in ("replace_restricted_fonts.py", lock_path.name):
        check(not (kit / name).is_symlink(), "Resource generator input is linked")
        shutil.copyfile(kit / name, tools / name)
    provenance = destination / "osu.Game.Resources/Fonts/OPEN_FONT_PROVENANCE.json"
    return {"directory": "modified-resources", "sourceAudit": result,
            "provenanceSha256": digest(provenance), "generatorSha256": digest(generator),
            "lockSha256": digest(lock_path),
            "binaryVerification": "Source audit only; extracted shipped DLL resources require separate verification"}


def package(a):
    here = Path(__file__).resolve().parent
    repo = a.repo.resolve()
    build = (a.build_dir or repo / "dist/build-macos").resolve()
    deps = (a.deps or Path(os.environ.get("DANSER_MACOS_DEPS_DIR", repo / ".deps/macos"))).resolve()
    output = a.out or build / "danser-macos-source.tar.gz"
    check(not output.exists(), "Output already exists: " + str(output))
    check(not (build / "notices-incomplete").exists(), "Notice collection failed")
    inventory = json.loads((build / "collected-notices/inventory.json").read_text())
    check(not inventory.get("fatalErrors"), "Notice inventory has fatal errors")
    build_info = json.loads((build / "build-info.json").read_text())
    evidence = (build / "collected-notices/Evidence/go-build-info.txt").read_text()
    settings = {fields[1].split("=", 1)[0]: fields[1].split("=", 1)[1]
                for line in evidence.splitlines() if len(fields := line.strip().split()) == 2
                and fields[0] == "build" and "=" in fields[1]}
    check(settings.get("vcs.modified") != "true", "Go binary was built from modified/untracked source")
    check(settings.get("vcs.revision", build_info["sourceRevision"]) == build_info["sourceRevision"],
          "Go binary source revision differs from verified build")
    binary = build / "danser.app/Contents/MacOS/danser"
    current = run("go", "version", "-m", str(binary))
    check(current.splitlines()[1:] == evidence.strip().splitlines()[1:] and
          current.splitlines()[0].split()[-1] == evidence.splitlines()[0].split()[-1],
          "Go executable differs from the notice inventory")
    host = (build / "danser.app/Contents/MacOS/lazer-rules-host").is_dir()
    check(not getattr(a, "require_open_font_sources", False) or not host or getattr(a, "resource_source", None),
          "This full-host release requires audited modified resource source")
    check(host == any(r.get("ecosystem") == "NuGet" for r in inventory["packages"]),
          "Optional host presence differs from NuGet notice inventory")
    pins = json.loads((here / "sources.json").read_text())
    if host:
        check_host_sources(inventory, here / "materials")
    cache = (a.go_mod_cache or Path(run("go", "env", "GOMODCACHE"))).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="danser-source-", dir=output.parent) as work:
        root = Path(work) / "danser-macos-source"
        root.mkdir()
        app = export_git(repo, root / "application", build_info["sourceRevision"])
        check("third_party/osu" in app["submodules"], "Missing materialized osu submodule")
        check(app["submodules"]["third_party/osu"]["commit"] == build_info.get("osuSourceRevision"),
              "osu source revision differs from verified build")
        modules = package_go(inventory, evidence, cache, root / "go-modules")
        native = pins["native"]
        libyuv = export_git(deps / "src" / ("libyuv-" + native["libyuv"]["commit"]),
                            root / "native/libyuv", native["libyuv"]["commit"])
        sdl_name = "SDL3-" + native["SDL3"]["version"]
        package_sdl(deps / "archives" / (sdl_name + ".tar.gz"), deps / "src" / sdl_name,
                    root / "native" / sdl_name, native["SDL3"]["sha256"])
        selected = [i for i in pins["archives"] if i.get("when") != "host" or host]
        for item in selected:
            source_archive(item, a.archives_cache, root / "upstream" / relative(item["file"]), a.fetch)
        for item in pins["materials"]:
            if item.get("when") == "host" and not host:
                continue
            source = here / "materials" / relative(item["file"])
            check(source.is_file() and not source.is_symlink() and digest(source) == item["sha256"],
                  "Checked-in source material changed: " + item["file"])
            target = root / "upstream" / relative(item["file"])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            target.chmod(0o755 if source.suffix == ".sh" else 0o644)
        copy_tree(build / "collected-notices", root / "notices")
        resource_source = getattr(a, "resource_source", None)
        modified_resources = None
        if resource_source:
            check(host, "Resource source supplied for a distribution without the rules host")
            kit = getattr(a, "resource_kit", None) or repo / "tools/lazer-fonts"
            modified_resources = package_resources(resource_source, kit, root / "modified-resources")
        for name in ("README-source.md", "build-ffmpeg-from-bundled-source.sh", "sources.json", "package_source.py"):
            shutil.copyfile(here / name, root / name)
        (root / "build-ffmpeg-from-bundled-source.sh").chmod(0o755)
        manifest = {"schemaVersion": 1, "applicationRepository": "https://github.com/Chesszyh/danser-go",
                    "application": app, "buildInfo": build_info,
                    "goToolchain": evidence.splitlines()[0].split()[-1], "goModules": modules,
                    "native": {**native, "libyuvGit": libyuv}, "optionalRulesHostIncluded": host,
                    "modifiedResources": modified_resources,
                    "sourceArchives": selected,
                    "nugetPackages": [{k: v for k, v in r.items() if k in ("key", "metadata", "packageSha256")}
                                      for r in inventory["packages"] if r.get("ecosystem") == "NuGet"],
                    "limitations": ["Source/provenance package, not independently reproduced bit-identical binaries",
                                    "Does not determine complete redistribution or artwork rights clearance",
                                    "BASS proprietary source is not supplied; vendor notices remain applicable"],
                    "files": file_manifest(root)}
        text = json.dumps(manifest, indent=2) + "\n"
        (root / "source-manifest.json").write_text(text)
        temporary = Path(work) / "output.tar.gz"
        with temporary.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as gz:
            with tarfile.open(fileobj=gz, mode="w") as tar:
                for path in [root, *sorted(root.rglob("*"))]:
                    info = tar.gettarinfo(str(path), arcname=str(path.relative_to(root.parent)))
                    info.uid = info.gid = info.mtime = 0
                    info.uname = info.gname = ""
                    if info.isfile():
                        with path.open("rb") as source:
                            tar.addfile(info, source)
                    else:
                        tar.addfile(info)
        os.replace(temporary, output)
        output.with_name("danser-macos-source-manifest.json").write_text(text)
        output.with_name(output.name + ".sha256").write_text(digest(output) + "  " + output.name + "\n")
    print(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--deps", type=Path)
    parser.add_argument("--go-mod-cache", type=Path)
    parser.add_argument("--archives-cache", type=Path)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--resource-source", type=Path, help="Modified osu-resources checkout, after Inter replacement")
    parser.add_argument("--resource-kit", type=Path, help="Directory containing audited generator and pinned lock")
    parser.add_argument("--require-open-font-sources", action="store_true",
                        help="Fail full-host packaging unless modified resource source is supplied")
    package(parser.parse_args())


if __name__ == "__main__":
    main()
