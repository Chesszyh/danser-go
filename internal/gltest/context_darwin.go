package gltest

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/wieku/danser-go/framework/assets"
	"github.com/wieku/danser-go/framework/env"
	"github.com/wieku/danser-go/framework/goroutines"
	"github.com/wieku/danser-go/framework/platform/gcontext"
)

func Run(m *testing.M) {
	if os.Getenv("DANSER_TEST_OPENGL") != "1" {
		os.Exit(m.Run())
	}

	root, err := os.Getwd()
	if err != nil {
		panic(err)
	}
	for {
		if _, err := os.Stat(filepath.Join(root, "go.mod")); err == nil {
			break
		}
		parent := filepath.Dir(root)
		if parent == root {
			panic("cannot locate test assets")
		}
		root = parent
	}
	env.Init("danser-gl-test")
	link := filepath.Join(env.LibDir(), "assets")
	if err := os.Symlink(filepath.Join(root, "assets"), link); err != nil {
		panic(err)
	}
	if os.Getenv("DANSER_MACOS_DEPS_DIR") == "" {
		if err := os.Setenv("DANSER_MACOS_DEPS_DIR", filepath.Join(root, ".deps", "macos")); err != nil {
			panic(err)
		}
	}
	assets.Init(true)
	code := 1
	// Cocoa contexts and all test drawing must stay on the process's main thread.
	goroutines.RunMain(func() {
		goroutines.CallMain(func() {
			if err := gcontext.Initialize(true); err != nil {
				panic(err)
			}
			gcontext.SDLCreateWindow(128, 128, "danser graphics tests", gcontext.OptionalProps{Hidden: true})
			if err := gcontext.GLInit(false); err != nil {
				panic(err)
			}
		})
		code = m.Run()
	})
	_ = os.Remove(link)
	os.Exit(code)
}

func Do(t *testing.T, check func() error) {
	t.Helper()
	if os.Getenv("DANSER_TEST_OPENGL") != "1" {
		t.Skip("set DANSER_TEST_OPENGL=1 to run native OpenGL tests")
	}
	var err error
	goroutines.CallMain(func() { err = check() })
	if err != nil {
		t.Fatal(err)
	}
}
