# Releases

Pull requests and pushes to `master` run the Linux and macOS workflows. Both build
with the official rules host. Linux verifies packaged replay and live scoring;
macOS also verifies native rendering, default launcher startup with update checks,
screenshots, recording output and the relocated application.

For a release, add notes in `docs/releases/<tag>.md`, commit the changes, and push an
annotated `vMAJOR.MINOR.PATCH-lazer.N` tag pointing to that commit. The Release
workflow builds Linux x86-64 and macOS arm64 from the tag. It uploads both platforms
to a draft and publishes only after all uploads succeed. Rerunning a failed upload
can resume that draft; an already published release is not overwritten.
Fork tags currently publish as prereleases. The application checks this fork's
release list, including prereleases, and compares numeric fork revisions.

The macOS display version follows the base version; the bundle build number is
the Release workflow run number. Local builds use `local-codesign` when available;
CI bundles remain ad-hoc signed. The Go and .NET versions come from `go.mod` and
`third_party/osu/global.json`.

## Official osu!lazer updates

`Update official lazer` checks daily at 10:23 Asia/Shanghai and can also be run
manually. It follows published non-prerelease releases from `ppy/osu`, compares
commit ancestry with `third_party/osu`, and skips releases already contained in
the pinned source. It does not follow individual development commits.

A new release creates or resumes an `automation/osu-lazer-*` branch and PR, with
the next fork revision and release notes. The workflow directly calls both build
workflows for that exact candidate commit. If either fails, the PR remains open;
no merge, tag or release occurs. Changes to scoring interfaces, SDK requirements,
or the pinned Inter resource replacement may require adapting that PR before
rerunning the update workflow. Numerical scoring can change with upstream rules;
passing protocol/replay checks is not proof of identical results for all maps.

After both platforms pass, the workflow checks that the PR head and base have not
changed, merges the PR, creates an annotated release tag, and dispatches Release
explicitly. Release rebuilds and validates the tagged merge commit before
publishing. This explicit dispatch is required because a `GITHUB_TOKEN` tag push
does not trigger another push workflow. A failed final step can be rerun from the
Actions page without overwriting a tag pointing elsewhere.

Repository Actions settings must allow workflows to create PRs. Jobs request
contents/PR write access, and the final job requests Actions write access to
start Release. No personal access token is required. Default-branch rules still
apply to automatic merging.

## Updating a local Mac

Run `python3 tools/macos-install.py --tag <tag>` to download and install a release,
or add `--archive /path/to/danser-macos.zip` to use an existing download. The
installer verifies and signs the bundle, tests it with isolated settings, replaces
`/Applications/danser.app`, and checks startup using the existing configuration.
It retains the previous app until startup succeeds and restores it on failure.
Settings, maps, replays and recordings are preserved. Temporary downloads and the
previous app are removed after success.
