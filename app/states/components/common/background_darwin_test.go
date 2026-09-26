package common

import (
	"fmt"
	"testing"

	"github.com/go-gl/mathgl/mgl32"
	"github.com/wieku/danser-go/framework/graphics/viewport"
	"github.com/wieku/danser-go/framework/math/vector"
	"github.com/wieku/danser-go/internal/gltest"
)

func TestMain(m *testing.M) { gltest.Run(m) }

func TestStoryboardClipUsesTargetPixels(t *testing.T) {
	gltest.Do(t, func() error {
		for _, scale := range []int{1, 2} {
			viewport.PushPos(10, 20, 800*scale, 600*scale)
			p := project(vector.NewVec2d(1, 1), mgl32.Ident4())
			viewport.Pop()
			if p.X != float64(10+800*scale) || p.Y != float64(20+600*scale) {
				return fmt.Errorf("scale %d: wrong clip corner %v", scale, p)
			}
		}
		return nil
	})
}
