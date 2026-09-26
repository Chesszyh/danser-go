package graphics

import (
	"fmt"
	"testing"

	"github.com/go-gl/gl/v3.3-core/gl"
	"github.com/wieku/danser-go/app/bmath/camera"
	"github.com/wieku/danser-go/app/settings"
	"github.com/wieku/danser-go/framework/graphics/attribute"
	"github.com/wieku/danser-go/framework/graphics/batch"
	"github.com/wieku/danser-go/framework/graphics/buffer"
	"github.com/wieku/danser-go/framework/graphics/shader"
	"github.com/wieku/danser-go/framework/graphics/sprite"
	"github.com/wieku/danser-go/framework/graphics/texture"
	"github.com/wieku/danser-go/framework/graphics/viewport"
	"github.com/wieku/danser-go/framework/math/animation"
	"github.com/wieku/danser-go/framework/math/color"
	"github.com/wieku/danser-go/framework/math/vector"
	"github.com/wieku/danser-go/internal/gltest"
)

func TestMain(m *testing.M) { gltest.Run(m) }

type testCursorRenderer struct{ draw func() }

func (*testCursorRenderer) SetPosition(vector.Vector2f) {}
func (*testCursorRenderer) Update(float64)              {}
func (*testCursorRenderer) UpdateRenderer()             {}
func (r *testCursorRenderer) DrawM(float64, float64, *batch.QuadBatch, color.Color, color.Color) {
	r.draw()
}

func TestAdditiveCursorBackingScale(t *testing.T) {
	gltest.Do(t, func() error {
		settings.Graphics.Fullscreen = true
		settings.Graphics.Width, settings.Graphics.Height = 64, 64
		settings.Cursor.AdditiveBlending = true
		settings.Skin.Cursor.UseSkinCursor = false
		settings.PLAYERS = 2
		Camera = camera.NewCamera()
		Camera.SetViewport(64, 64, false)
		initCursor()
		s := shader.NewRShader(
			shader.NewSource("#version 330\nin vec2 position; void main(){gl_Position=vec4(position,0,1);}", shader.Vertex),
			shader.NewSource("#version 330\nout vec4 color; void main(){color=vec4(1,0,0,1);}", shader.Fragment),
		)
		defer s.Dispose()
		v := buffer.NewVertexArrayObject()
		defer v.Dispose()
		v.AddVBO("position", 6, 0, attribute.Format{{Name: "position", Type: attribute.Vec2}})
		v.SetData("position", 0, []float32{.4, .4, .8, .4, .4, .8, .8, .4, .8, .8, .4, .8})
		v.Attach(s)
		c := &Cursor{scale: animation.NewGlider(1), rippleContainer: sprite.NewManager(), smokeContainer: sprite.NewManager(), renderer: &testCursorRenderer{draw: func() { s.Bind(); v.Bind(); v.Draw(); v.Unbind(); s.Unbind() }}}
		for _, scale := range []int{1, 2, 1} {
			size := 64 * scale
			output := buffer.NewFrame(size, size, false, false)
			defer output.Dispose()
			output.Bind()
			viewport.Push(size, size)
			gl.Enable(gl.SCISSOR_TEST)
			output.ClearColor(0, 0, 0, 0)
			BeginCursorRender()
			c.DrawM(1, nil, color.NewRGBA(1, 1, 1, 1), color.NewRGBA(1, 1, 1, 1))
			EndCursorRender()
			viewport.Pop()
			output.Unbind()
			pixels := make([]byte, size*size*4)
			texture.ReadPixels(output.Texture(), gl.RGBA, gl.UNSIGNED_BYTE, int32(len(pixels)), gl.Ptr(pixels))
			center := (size*4/5 + size*4/5*size) * 4
			if pixels[center] < 200 || pixels[center+3] < 200 || pixels[3] != 0 {
				return fmt.Errorf("scale %d: additive cursor was clipped or moved: %v", scale, pixels[center:center+4])
			}
		}
		if e := gl.GetError(); e != gl.NO_ERROR {
			return fmt.Errorf("OpenGL error 0x%x", e)
		}
		return nil
	})
}
