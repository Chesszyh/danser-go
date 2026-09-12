package schedulers

import (
	"testing"

	"github.com/wieku/danser-go/app/beatmap/difficulty"
	"github.com/wieku/danser-go/app/beatmap/objects"
	"github.com/wieku/danser-go/framework/math/vector"
)

func TestMergeOverlappingCircles(t *testing.T) {
	for _, test := range []struct {
		name       string
		times      []float64
		wantTimes  []float64
		wantDouble []bool
	}{
		{"pair before final circle", []float64{1000, 1002, 2000}, []float64{1001, 2000}, []bool{true, false}},
		{"successive pairs", []float64{1000, 1002, 2000, 2002}, []float64{1001, 2001}, []bool{true, true}},
		{"final pair", []float64{1000, 2000, 2002}, []float64{1000, 2001}, []bool{false, true}},
		{"separate circles", []float64{1000, 2000, 3000}, []float64{1000, 2000, 3000}, []bool{false, false, false}},
	} {
		t.Run(test.name, func(t *testing.T) {
			scheduler := &GenericScheduler{diff: difficulty.NewDifficulty(5, 4, 5, 5)}
			for _, time := range test.times {
				scheduler.queue = append(scheduler.queue, objects.DummyCircle(vector.NewVec2f(256, 192), time))
			}

			scheduler.mergeOverlappingCircles()

			if len(scheduler.queue) != len(test.wantTimes) {
				t.Fatalf("got %d objects, want %d", len(scheduler.queue), len(test.wantTimes))
			}
			for i, object := range scheduler.queue {
				circle := object.(*objects.Circle)
				if pos := circle.GetStackedStartPositionMod(scheduler.diff); pos != vector.NewVec2f(256, 192) {
					t.Errorf("object %d: position=%v, want (256, 192)", i, pos)
				}
				if circle.GetStartTime() != test.wantTimes[i] || circle.DoubleClick != test.wantDouble[i] {
					t.Errorf("object %d: time=%v doubleClick=%v, want time=%v doubleClick=%v", i, circle.GetStartTime(), circle.DoubleClick, test.wantTimes[i], test.wantDouble[i])
				}
			}
		})
	}
}
