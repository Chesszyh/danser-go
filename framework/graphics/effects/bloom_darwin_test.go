package effects

import (
	"fmt"
	"testing"

	"github.com/go-gl/gl/v3.3-core/gl"
	"github.com/wieku/danser-go/app/settings"
	"github.com/wieku/danser-go/framework/graphics/attribute"
	"github.com/wieku/danser-go/framework/graphics/buffer"
	"github.com/wieku/danser-go/framework/graphics/shader"
	"github.com/wieku/danser-go/framework/graphics/texture"
	"github.com/wieku/danser-go/framework/graphics/viewport"
	"github.com/wieku/danser-go/internal/gltest"
)

func TestMain(m *testing.M) { gltest.Run(m) }

func TestBloomBackingScale(t *testing.T) {
	gltest.Do(t, func() error {
		settings.Graphics.MSAA = 4
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
		bloom := NewBloomEffect(64, 64)
		bloom.SetPower(0)
		for _, scale := range []int{1, 2, 1} {
			size := 64 * scale
			output := buffer.NewFrame(size, size, false, false)
			defer output.Dispose()
			output.Bind()
			viewport.Push(size, size)
			gl.Enable(gl.SCISSOR_TEST)
			output.ClearColor(0, 0, 0, 0)
			bloom.Begin()
			s.Bind()
			v.Bind()
			v.Draw()
			v.Unbind()
			s.Unbind()
			bloom.EndAndRender()
			var vp, scissor [4]int32
			gl.GetIntegerv(gl.VIEWPORT, &vp[0])
			gl.GetIntegerv(gl.SCISSOR_BOX, &scissor[0])
			if vp != [4]int32{0, 0, int32(size), int32(size)} || scissor != vp {
				return fmt.Errorf("scale %d: output viewport/scissor was not restored: %v %v", scale, vp, scissor)
			}
			viewport.Pop()
			output.Unbind()
			pixels := make([]byte, size*size*4)
			texture.ReadPixels(output.Texture(), gl.RGBA, gl.UNSIGNED_BYTE, int32(len(pixels)), gl.Ptr(pixels))
			center := (size*4/5 + size*4/5*size) * 4
			if pixels[center] < 200 || pixels[center+3] < 200 || pixels[0] != 0 {
				return fmt.Errorf("scale %d: bloom moved or clipped the input shape: %v", scale, pixels[center:center+4])
			}
		}
		if e := gl.GetError(); e != gl.NO_ERROR {
			return fmt.Errorf("OpenGL error 0x%x", e)
		}
		return nil
	})
}
