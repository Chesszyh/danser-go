package texture_test

import (
	"bytes"
	"fmt"
	"testing"

	"github.com/go-gl/gl/v3.3-core/gl"
	"github.com/wieku/danser-go/framework/graphics/texture"
	"github.com/wieku/danser-go/framework/math/color"
	"github.com/wieku/danser-go/internal/gltest"
)

func TestMain(m *testing.M) { gltest.Run(m) }

func TestTextureExpansionIgnoresDrawingState(t *testing.T) {
	gltest.Do(t, func() error {
		for _, clipped := range []bool{false, true} {
			gl.Disable(gl.SCISSOR_TEST)
			gl.ColorMask(true, true, true, true)
			tex := texture.NewTextureMultiLayerCC(4, 4, 1, 1, color.NewRGBA(0, 1, 0, 1))
			defer tex.Dispose()
			red := bytes.Repeat([]byte{255, 0, 0, 255}, 16)
			tex.SetData(0, 0, 4, 4, 0, red)
			if clipped {
				gl.Enable(gl.SCISSOR_TEST)
			}
			gl.Scissor(1, 1, 1, 1)
			gl.ColorMaski(0, false, false, false, false)
			tex.NewLayer()
			pixels := make([]byte, 128)
			texture.ReadPixels(tex, gl.RGBA, gl.UNSIGNED_BYTE, int32(len(pixels)), gl.Ptr(pixels))
			if !bytes.Equal(pixels[:64], red) || !bytes.Equal(pixels[64:], bytes.Repeat([]byte{0, 255, 0, 255}, 16)) {
				return fmt.Errorf("clipped=%t: expansion lost pixels or did not clear the new layer: %v", clipped, pixels)
			}
			var mask [4]bool
			var scissor [4]int32
			gl.GetBooleani_v(gl.COLOR_WRITEMASK, 0, &mask[0])
			gl.GetIntegerv(gl.SCISSOR_BOX, &scissor[0])
			if mask != [4]bool{} || gl.IsEnabled(gl.SCISSOR_TEST) != clipped || scissor != [4]int32{1, 1, 1, 1} {
				return fmt.Errorf("texture expansion changed drawing state")
			}
		}
		gl.Disable(gl.SCISSOR_TEST)
		gl.ColorMask(true, true, true, true)
		gl.DepthMask(false)
		depth := texture.NewTextureMultiLayerFormatCC(4, 4, texture.Depth, 1, 1, color.NewRGBA(1, 0, 0, 0))
		defer depth.Dispose()
		pixels := make([]float32, 16)
		texture.ReadPixels(depth, gl.DEPTH_COMPONENT, gl.FLOAT, 64, gl.Ptr(pixels))
		for _, value := range pixels {
			if value != 1 {
				return fmt.Errorf("depth write mask prevented clear: %v", pixels)
			}
		}
		var depthMask bool
		gl.GetBooleanv(gl.DEPTH_WRITEMASK, &depthMask)
		if depthMask {
			return fmt.Errorf("depth write mask was not restored")
		}
		if e := gl.GetError(); e != gl.NO_ERROR {
			return fmt.Errorf("OpenGL error 0x%x", e)
		}
		return nil
	})
}
