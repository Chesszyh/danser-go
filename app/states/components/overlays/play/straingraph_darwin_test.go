package play

import (
	"fmt"
	"os"
	"testing"

	"github.com/go-gl/gl/v3.3-core/gl"
	"github.com/wieku/danser-go/app/beatmap"
	"github.com/wieku/danser-go/app/beatmap/difficulty"
	"github.com/wieku/danser-go/app/beatmap/objects"
	"github.com/wieku/danser-go/app/rulesets/osu/performance/api"
	"github.com/wieku/danser-go/app/settings"
	"github.com/wieku/danser-go/framework/env"
	"github.com/wieku/danser-go/framework/goroutines"
	"github.com/wieku/danser-go/framework/graphics/batch"
	"github.com/wieku/danser-go/framework/graphics/texture"
	"github.com/wieku/danser-go/framework/math/vector"
	"github.com/wieku/danser-go/framework/platform/gcontext"
)

func TestMain(m *testing.M) {
	if os.Getenv("DANSER_TEST_OPENGL") != "1" {
		os.Exit(m.Run())
	}

	// Cocoa requires context creation and drawing on the process's main thread.
	code := 1
	goroutines.RunMain(func() { code = m.Run() })
	os.Exit(code)
}

func TestStrainGraphRendering(t *testing.T) {
	if os.Getenv("DANSER_TEST_OPENGL") != "1" {
		t.Skip("set DANSER_TEST_OPENGL=1 and DANSER_MACOS_DEPS_DIR to run the native OpenGL test")
	}

	var err error
	goroutines.CallMain(func() { err = checkStrainGraphRendering() })
	if err != nil {
		t.Fatal(err)
	}
}

func checkStrainGraphRendering() error {
	env.Init("danser-strain-graph-test")
	if err := gcontext.Initialize(true); err != nil {
		return err
	}
	gcontext.SDLCreateWindow(128, 128, "strain graph test", gcontext.OptionalProps{Hidden: true})
	if err := gcontext.GLInit(false); err != nil {
		return err
	}

	settings.Graphics.Width, settings.Graphics.Height = 1024, 768
	settings.Graphics.Fullscreen = true
	beatMap := &beatmap.BeatMap{Diff: difficulty.NewDifficulty(5, 4, 5, 5)}
	for _, time := range []float64{1000, 1400, 1800, 2200} {
		beatMap.HitObjects = append(beatMap.HitObjects, objects.DummyCircle(vector.NewVec2f(256, 192), time))
	}
	graph := NewStrainGraph(beatMap, api.StrainPeaks{Total: []float64{1, 4, 2, 6}}, false, false)
	graph.drawFBO(&batch.QuadBatch{})
	defer graph.fbo.Dispose()
	if glErr := gl.GetError(); glErr != gl.NO_ERROR {
		var maxSamples int32
		gl.GetIntegerv(gl.MAX_SAMPLES, &maxSamples)
		return fmt.Errorf("strain graph rendering: OpenGL error 0x%x (maximum samples: %d)", glErr, maxSamples)
	}

	pixels := make([]byte, graph.fbo.GetWidth()*graph.fbo.GetHeight()*4)
	texture.ReadPixels(graph.fbo.Texture(), gl.RGBA, gl.UNSIGNED_BYTE, int32(len(pixels)), gl.Ptr(pixels))
	visible := 0
	for i := 3; i < len(pixels); i += 4 {
		if pixels[i] > 128 {
			visible++
		}
	}
	if visible == 0 || visible == len(pixels)/4 {
		return fmt.Errorf("strain graph should contain visible peaks and transparent space, got %d/%d opaque pixels", visible, len(pixels)/4)
	}
	if glErr := gl.GetError(); glErr != gl.NO_ERROR {
		return fmt.Errorf("strain graph readback: OpenGL error 0x%x", glErr)
	}
	return nil
}
