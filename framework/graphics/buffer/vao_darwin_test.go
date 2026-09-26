package buffer

import (
	"fmt"
	"testing"
	"unsafe"

	"github.com/go-gl/gl/v3.3-core/gl"
	"github.com/wieku/danser-go/framework/graphics/attribute"
	"github.com/wieku/danser-go/framework/graphics/glcaps"
	"github.com/wieku/danser-go/framework/graphics/shader"
	"github.com/wieku/danser-go/internal/gltest"
)

func TestMain(m *testing.M) { gltest.Run(m) }

func TestLegacyInstanceAttributeOffsets(t *testing.T) {
	gltest.Do(t, func() error {
		s := shader.NewRShader(
			shader.NewSource("#version 330\nin vec2 position; void main(){gl_Position=vec4(position,0,1);}", shader.Vertex),
			shader.NewSource("#version 330\nout vec4 color; void main(){color=vec4(1);}", shader.Fragment),
		)
		defer s.Dispose()
		original := glcaps.Current()
		defer glcaps.Set(original)
		for _, nativeBase := range []bool{false, true} {
			caps := original
			caps.DirectStateAccess, caps.VertexAttribBinding, caps.BaseInstance = false, false, nativeBase
			glcaps.Set(caps)
			vao := NewVertexArrayObject()
			defer vao.Dispose()
			vao.AddVBO("instances", 16, 1, attribute.Format{{Name: "position", Type: attribute.Vec2}})
			vao.Attach(s)
			vao.Bind()
			for _, base := range []int{0, 3, 7, 0} {
				vao.prepareBaseInstance(base)
				var pointer unsafe.Pointer
				gl.GetVertexAttribPointerv(uint32(s.GetAttributeInfo("position").Location), gl.VERTEX_ATTRIB_ARRAY_POINTER, &pointer)
				want := uintptr(base * 8)
				if nativeBase {
					want = 0
				}
				if uintptr(pointer) != want {
					return fmt.Errorf("nativeBase=%t base=%d: attribute offset %d, want %d", nativeBase, base, uintptr(pointer), want)
				}
			}
			vao.Unbind()
		}
		if e := gl.GetError(); e != gl.NO_ERROR {
			return fmt.Errorf("OpenGL error 0x%x", e)
		}
		return nil
	})
}
