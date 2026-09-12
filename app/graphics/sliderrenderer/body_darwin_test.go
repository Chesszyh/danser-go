package sliderrenderer

import (
	"fmt"
	"os"
	"path/filepath"
	"testing"

	"github.com/go-gl/gl/v3.3-core/gl"
	"github.com/go-gl/mathgl/mgl32"
	"github.com/wieku/danser-go/app/settings"
	"github.com/wieku/danser-go/framework/assets"
	"github.com/wieku/danser-go/framework/env"
	"github.com/wieku/danser-go/framework/goroutines"
	"github.com/wieku/danser-go/framework/graphics/buffer"
	"github.com/wieku/danser-go/framework/graphics/texture"
	"github.com/wieku/danser-go/framework/graphics/viewport"
	"github.com/wieku/danser-go/framework/math/color"
	"github.com/wieku/danser-go/framework/math/curves"
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

func TestSliderTrackRendering(t *testing.T) {
	if os.Getenv("DANSER_TEST_OPENGL") != "1" {
		t.Skip("set DANSER_TEST_OPENGL=1 and DANSER_MACOS_DEPS_DIR to run the native OpenGL test")
	}

	var err error
	goroutines.CallMain(func() { err = checkSliderTrackRendering() })
	if err != nil {
		t.Fatal(err)
	}
}

func checkSliderTrackRendering() error {
	env.Init("danser-slider-test")
	sourceAssets, err := filepath.Abs("../../../assets")
	if err != nil {
		return err
	}
	linkedAssets := filepath.Join(env.LibDir(), "assets")
	if _, err = os.Stat(linkedAssets); os.IsNotExist(err) {
		if err = os.Symlink(sourceAssets, linkedAssets); err != nil {
			return err
		}
		defer os.Remove(linkedAssets)
	}
	assets.Init(true)

	if err = gcontext.Initialize(true); err != nil {
		return err
	}
	gcontext.SDLCreateWindow(128, 128, "slider track test", gcontext.OptionalProps{Hidden: true})
	if err = gcontext.GLInit(false); err != nil {
		return err
	}

	settings.Graphics.Width, settings.Graphics.Height = 128, 128
	settings.Graphics.Fullscreen = true
	projection := mgl32.Ortho(0, 128, 128, 0, 1, -1)
	output := buffer.NewFrame(128, 128, false, false)
	defer output.Dispose()

	for _, test := range []struct {
		name   string
		points []vector.Vector2f
		probe  vector.Vector2f
	}{
		{"straight", []vector.Vector2f{{X: 32, Y: 64}, {X: 96, Y: 64}}, vector.NewVec2f(64, 64)},
		{"bent", []vector.Vector2f{{X: 32, Y: 64}, {X: 64, Y: 32}, {X: 96, Y: 64}}, vector.NewVec2f(64, 32)},
	} {
		curve := curves.NewMultiCurve([]curves.CurveDef{{CurveType: curves.CLine, Points: test.points}})
		body := NewBody(curve, false, false, 8)
		body.DrawBase(0, 1, projection)
		if glErr := gl.GetError(); glErr != gl.NO_ERROR {
			return fmt.Errorf("%s slider depth drawing: OpenGL error 0x%x", test.name, glErr)
		}

		depth := make([]float32, body.framebuffer.GetWidth()*body.framebuffer.GetHeight())
		texture.ReadPixels(body.framebuffer.Texture(), gl.DEPTH_COMPONENT, gl.FLOAT, int32(len(depth)*4), gl.Ptr(depth))
		minimum := float32(1)
		for _, d := range depth {
			minimum = min(minimum, d)
		}
		if minimum >= 1 {
			return fmt.Errorf("%s slider did not write its depth texture", test.name)
		}

		output.Bind()
		viewport.Push(128, 128)
		output.ClearColor(0, 0, 0, 0)
		BeginRenderer()
		white := color.NewRGBA(1, 1, 1, 1)
		body.DrawNormal(projection, vector.NewVec2f(0, 0), 1, white, white, white, white)
		EndRenderer()
		viewport.Pop()
		output.Unbind()

		pixels := make([]byte, 128*128*4)
		texture.ReadPixels(output.Texture(), gl.RGBA, gl.UNSIGNED_BYTE, int32(len(pixels)), gl.Ptr(pixels))
		center := (int(test.probe.X) + (127-int(test.probe.Y))*128) * 4
		if pixels[center+3] < 200 || pixels[center] < 200 {
			return fmt.Errorf("%s slider track is invisible at its center: %v", test.name, pixels[center:center+4])
		}
		if pixels[3] != 0 {
			return fmt.Errorf("%s slider drew outside its bounds", test.name)
		}
		if glErr := gl.GetError(); glErr != gl.NO_ERROR {
			return fmt.Errorf("%s slider color drawing: OpenGL error 0x%x", test.name, glErr)
		}
		body.Dispose()
	}
	return nil
}
