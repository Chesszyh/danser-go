package platform

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"github.com/wieku/danser-go/framework/env"
)

func ffmpegFixture(t *testing.T, directory, name string) string {
	t.Helper()
	path := filepath.Join(directory, name)
	if err := os.WriteFile(path, []byte("#!/bin/sh\nexit 0\n"), 0755); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestFFmpegExplicitDirectory(t *testing.T) {
	env.Init("danser-ffmpeg-test")
	directory := t.TempDir()
	path := ffmpegFixture(t, directory, "ffmpeg")
	t.Setenv("DANSER_FFMPEG_DIR", directory)
	t.Setenv("PATH", t.TempDir())
	actual, err := findFFmpeg()
	if err != nil || actual != path {
		t.Fatalf("got %q, %v; want %q", actual, err, path)
	}
	if err := os.Chmod(path, 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := findFFmpeg(); err == nil || !strings.Contains(err.Error(), "DANSER_FFMPEG_DIR") {
		t.Fatalf("invalid explicit path must not silently use a different installation: %v", err)
	}
}

func TestFFmpegPathPrecedesHomebrew(t *testing.T) {
	env.Init("danser-ffmpeg-test")
	directory := t.TempDir()
	path := ffmpegFixture(t, directory, "ffmpeg")
	t.Setenv("DANSER_FFMPEG_DIR", "")
	t.Setenv("PATH", directory)
	actual, err := findFFmpeg()
	if err != nil || actual != path {
		t.Fatalf("got %q, %v; want %q", actual, err, path)
	}
}

func TestFFmpegFinderEnvironment(t *testing.T) {
	env.Init("danser-ffmpeg-test")
	want := ""
	for _, path := range []string{"/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"} {
		if _, err := exec.LookPath(path); err == nil {
			want = path
			break
		}
	}
	if want == "" {
		t.Skip("Homebrew FFmpeg is not installed")
	}
	t.Setenv("DANSER_FFMPEG_DIR", "")
	t.Setenv("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
	actual, err := findFFmpeg()
	if err != nil || actual != want {
		t.Fatalf("got %q, %v; want %q", actual, err, want)
	}
}

func TestPrepareFFmpegRecoversAfterMissingDependency(t *testing.T) {
	env.Init("danser-ffmpeg-test")
	ffmpegInit, ffPath = false, ""
	t.Cleanup(func() { ffmpegInit, ffPath = false, "" })
	directory := t.TempDir()
	t.Setenv("DANSER_FFMPEG_DIR", directory)
	if _, err := PrepareFFMpeg("ffmpeg"); err == nil {
		t.Fatal("missing executable was accepted")
	}
	for _, name := range []string{"ffmpeg", "ffprobe"} {
		ffmpegFixture(t, directory, name)
	}
	for _, name := range []string{"ffmpeg", "ffprobe"} {
		cmd, err := PrepareFFMpeg(name, "-version")
		if err != nil {
			t.Fatal(err)
		}
		if cmd.Path != filepath.Join(directory, name) || cmd.Dir != directory {
			t.Fatalf("wrong command location: %+v", cmd)
		}
		if err := cmd.Run(); err != nil {
			t.Fatal(err)
		}
	}
}
