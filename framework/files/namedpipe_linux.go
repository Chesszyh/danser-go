//go:build linux

package files

import (
	"os"

	"golang.org/x/sys/unix"
)

func setPipeSize(file *os.File) error {
	_, err := unix.FcntlInt(file.Fd(), unix.F_SETPIPE_SZ, 65536)
	return err
}
