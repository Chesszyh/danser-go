//go:build darwin

package files

import (
	"errors"
	"os"
	"testing"
)

func TestNamedPipeDarwin(t *testing.T) {
	pipe, err := NewNamedPipe(t.TempDir(), "test")
	if err != nil {
		t.Fatal(err)
	}

	path := pipe.Path()
	payload := []byte("danser")
	if _, err = pipe.Write(payload); err != nil {
		t.Fatal(err)
	}

	got := make([]byte, len(payload))
	if _, err = pipe.Read(got); err != nil {
		t.Fatal(err)
	}
	if string(got) != string(payload) {
		t.Fatalf("read %q, want %q", got, payload)
	}

	if err = pipe.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err = os.Stat(path); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("pipe still exists after Close: %v", err)
	}
}
