package main

import (
	"archive/zip"
	"bytes"
	"os"
	"path/filepath"
	"testing"
)

func TestUnpackVersionedSharedLibraryLink(t *testing.T) {
	var contents bytes.Buffer
	writer := zip.NewWriter(&contents)
	library, _ := writer.Create("ffmpeg/lib/libavdevice.so.62.3.103")
	library.Write([]byte("\x7fELF library payload"))
	header := &zip.FileHeader{Name: "ffmpeg/lib/libavdevice.so.62"}
	header.SetMode(os.ModeSymlink | 0777)
	link, _ := writer.CreateHeader(header)
	link.Write([]byte("libavdevice.so.62.3.103"))
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	archive, err := zip.NewReader(bytes.NewReader(contents.Bytes()), int64(contents.Len()))
	if err != nil {
		t.Fatal(err)
	}
	destination := filepath.Join(t.TempDir(), "libavdevice.so.62")
	unpack(archive.File[1], destination, archive)
	data, err := os.ReadFile(destination)
	if err != nil {
		t.Fatal(err)
	}
	if string(data) != "\x7fELF library payload" {
		t.Fatalf("library contains link text instead of executable bytes: %q", data)
	}
}
