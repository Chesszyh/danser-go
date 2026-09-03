//go:build !windows && !linux

package files

import "os"

func setPipeSize(_ *os.File) error {
	return nil
}
