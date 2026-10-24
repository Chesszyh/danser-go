# Releases

Pull requests and pushes to `master` run the Linux, Windows and macOS build workflows.
The macOS workflow also verifies the relocated application, official replay and live
rules, screenshots, and recording output.

For a release, add notes in `docs/releases/<tag>.md`, commit the changes, and push an
annotated `v` tag pointing to that commit. The Release workflow builds all three
platforms from the tag and publishes their artifacts after every build succeeds.
Tags containing a hyphen create a prerelease. Build tools read the Go version from
`go.mod` and the .NET SDK from `third_party/osu/global.json`.
