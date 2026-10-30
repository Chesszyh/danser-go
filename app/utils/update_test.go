package utils

import (
	"io"
	"net/http"
	"strings"
	"testing"

	"github.com/wieku/danser-go/build"
)

type releaseTransport func(*http.Request) (*http.Response, error)

func (f releaseTransport) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func mockReleases(t *testing.T, status int, body string) {
	t.Helper()
	previous := updateClient
	t.Cleanup(func() { updateClient = previous })
	updateClient = &http.Client{Transport: releaseTransport(func(r *http.Request) (*http.Response, error) {
		if r.URL.String() != "https://api.github.com/repos/Chesszyh/danser-go/releases?per_page=100" {
			t.Fatalf("unexpected update source: %s", r.URL)
		}
		return &http.Response{StatusCode: status, Body: io.NopCloser(strings.NewReader(body))}, nil
	})}
}

func TestReleaseVersionOrdering(t *testing.T) {
	versions := []string{"0.6.7-s12", "0.6.7-snapshot13", "0.6.7", "v0.12.1-lazer.4", "0.12.1-lazer.5", "0.12.1", "0.12.2-lazer.1"}
	var previous uint64
	for _, version := range versions {
		got, err := TransformVersion(version)
		if err != nil || got <= previous {
			t.Fatalf("%s: value=%d, previous=%d, error=%v", version, got, previous, err)
		}
		previous = got
	}
	for _, version := range []string{"", "macos-2026.10.03", "0.12.1-lazer.x", "0.12.1-lazer.-1", "0.12.1-lazer.10000", "0.12", "10000.0.0", "0.12.1-dev"} {
		if _, err := TransformVersion(version); err == nil {
			t.Fatalf("accepted invalid version %q", version)
		}
	}
}

func TestForkUpdateFromReleaseBuild(t *testing.T) {
	stream, version := build.Stream, build.VERSION
	t.Cleanup(func() { build.Stream, build.VERSION = stream, version })
	build.Stream, build.VERSION = "Release", "0.12.1-lazer.4"
	mockReleases(t, 200, `[{"tag_name":"macos-2026.10.03"},{"tag_name":"v0.12.1-lazer.6","draft":true},{"tag_name":"v0.12.1-lazer.5","prerelease":true,"html_url":"https://github.com/Chesszyh/danser-go/releases/tag/v0.12.1-lazer.5"},{"tag_name":"v0.12.1-lazer.3"}]`)
	status, url, err := CheckForUpdate()
	if err != nil || status != UpdateAvailable || !strings.HasSuffix(url, "v0.12.1-lazer.5") {
		t.Fatalf("%v %s %v", status, url, err)
	}
	build.VERSION = "0.12.1-lazer.5"
	status, _, err = CheckForUpdate()
	if err != nil || status != UpToDate {
		t.Fatalf("%v %v", status, err)
	}
}

func TestUpdateFailureDoesNotPanic(t *testing.T) {
	for _, fixture := range []struct {
		status int
		body   string
	}{{403, `{}`}, {200, `invalid`}, {200, `[]`}, {200, `[{"tag_name":"invalid"}]`}} {
		t.Run(fixture.body, func(t *testing.T) {
			mockReleases(t, fixture.status, fixture.body)
			if _, _, err := GetLatestVersionFromGitHub(); err == nil {
				t.Fatal("expected update error")
			}
		})
	}
}
