package utils

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/wieku/danser-go/build"
)

var updateClient = &http.Client{Timeout: 10 * time.Second}

// GetLatestVersionFromGitHub includes fork releases marked as prereleases.
func GetLatestVersionFromGitHub() (url string, tag string, err error) {
	request, err := http.NewRequest(http.MethodGet, "https://api.github.com/repos/Chesszyh/danser-go/releases?per_page=100", nil)
	if err != nil {
		return "", "", err
	}
	response, err := updateClient.Do(request)
	if err != nil {
		return "", "", err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return "", "", fmt.Errorf("GitHub releases returned HTTP %d", response.StatusCode)
	}
	var releases []struct {
		URL   string `json:"html_url"`
		Tag   string `json:"tag_name"`
		Draft bool   `json:"draft"`
	}
	if err = json.NewDecoder(response.Body).Decode(&releases); err != nil {
		return "", "", err
	}
	var highest uint64
	for _, release := range releases {
		version, parseErr := TransformVersion(release.Tag)
		if release.Draft || parseErr != nil {
			continue
		}
		if tag == "" || version > highest {
			url, tag, highest = release.URL, release.Tag, version
		}
	}
	if tag == "" {
		return "", "", fmt.Errorf("no supported danser release was found")
	}
	return url, tag, nil
}

// TransformVersion orders numeric releases, legacy snapshots and fork revisions.
func TransformVersion(version string) (uint64, error) {
	base, suffix, hasSuffix := strings.Cut(strings.TrimPrefix(version, "v"), "-")
	parts := strings.Split(strings.TrimSuffix(base, "b"), ".")
	invalid := func() (uint64, error) { return 0, fmt.Errorf("unsupported danser version %q", version) }
	if len(parts) != 3 {
		return invalid()
	}
	var result uint64
	for _, part := range parts {
		if part == "" || strings.Trim(part, "0123456789") != "" {
			return invalid()
		}
		number, err := strconv.ParseUint(part, 10, 16)
		if err != nil || number > 9999 {
			return invalid()
		}
		result = result*10000 + number
	}
	revision := uint64(9999)
	if hasSuffix {
		switch {
		case strings.HasPrefix(suffix, "lazer."):
			suffix = strings.TrimPrefix(suffix, "lazer.")
		case strings.HasPrefix(suffix, "snapshot"):
			suffix = strings.TrimPrefix(suffix, "snapshot")
		case strings.HasPrefix(suffix, "s"):
			suffix = strings.TrimPrefix(suffix, "s")
		default:
			return invalid()
		}
		if suffix == "" || strings.Trim(suffix, "0123456789") != "" {
			return invalid()
		}
		number, err := strconv.ParseUint(suffix, 10, 16)
		if err != nil || number >= 9999 {
			return invalid()
		}
		revision = number
	}
	return result*10000 + revision, nil
}

type UpdateStatus int

const (
	Failed = UpdateStatus(iota)
	Ignored
	UpToDate
	Snapshot
	UpdateAvailable
)

func CheckForUpdate() (UpdateStatus, string, error) {
	if build.Stream != "Release" || strings.Contains(build.VERSION, "dev") {
		return Ignored, "", nil
	}
	exeVersion, err := TransformVersion(build.VERSION)
	if err != nil {
		return Failed, "", err
	}
	log.Println("Checking GitHub for a new version of danser...")
	url, tag, err := GetLatestVersionFromGitHub()
	if err != nil {
		return Failed, "", err
	}
	githubVersion, err := TransformVersion(tag)
	if err != nil {
		return Failed, "", err
	}
	if exeVersion >= githubVersion {
		return UpToDate, "", nil
	}
	return UpdateAvailable, url, nil
}
