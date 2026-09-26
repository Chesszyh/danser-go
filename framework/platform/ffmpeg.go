package platform

import (
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"

	"github.com/wieku/danser-go/framework/files"
)

var ffmpegInit bool
var ffPath string
var ffmpegMutex sync.Mutex

func findFFmpeg() (string, error) {
	if directory := strings.TrimSpace(os.Getenv("DANSER_FFMPEG_DIR")); directory != "" {
		path, err := exec.LookPath(filepath.Join(directory, "ffmpeg"))
		if err != nil {
			return "", fmt.Errorf("FFmpeg is unavailable in DANSER_FFMPEG_DIR %q: %w", directory, err)
		}
		return filepath.Abs(path)
	}

	if path, err := files.GetCommandExec("ffmpeg", "ffmpeg"); err == nil {
		return filepath.Abs(path)
	}

	if runtime.GOOS == "darwin" {
		// Finder launches do not inherit the user's shell startup files.
		for _, directory := range []string{"/opt/homebrew/bin", "/usr/local/bin"} {
			if path, err := exec.LookPath(filepath.Join(directory, "ffmpeg")); err == nil {
				return path, nil
			}
		}
		return "", fmt.Errorf("FFmpeg not found. Install it with 'brew install ffmpeg', or set DANSER_FFMPEG_DIR to the directory containing ffmpeg and ffprobe")
	}

	return "", fmt.Errorf("FFmpeg not found. Install it next to danser or in PATH, or set DANSER_FFMPEG_DIR to the directory containing ffmpeg and ffprobe")
}

func PrepareFFMpeg(cmdName string, args ...string) (*exec.Cmd, error) {
	ffmpegMutex.Lock()
	defer ffmpegMutex.Unlock()

	if !ffmpegInit {
		ffmpegExec, err := findFFmpeg()
		if err != nil {
			return nil, err
		}

		ffPath = filepath.Dir(ffmpegExec)
		ffmpegInit = true
		log.Println("FFmpeg exec location:", ffmpegExec)
	}

	execPath := filepath.Join(ffPath, cmdName)

	if runtime.GOOS != "windows" {
		if stat, err := os.Stat(execPath); err == nil {
			os.Chmod(execPath, (stat.Mode()&os.ModePerm)|0111) // Just try
		}
	}

	cmd := exec.Command(execPath, args...)
	cmd.Dir = ffPath

	return cmd, nil
}
