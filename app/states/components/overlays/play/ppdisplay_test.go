package play

import (
	"testing"

	"github.com/wieku/danser-go/app/beatmap/difficulty"
	"github.com/wieku/danser-go/app/rulesets/osu/performance/api"
	"github.com/wieku/danser-go/app/settings"
)

func TestPPDisplayReadingComponents(t *testing.T) {
	previous := *settings.Gameplay.PPCounter
	defer func() { *settings.Gameplay.PPCounter = previous }()
	settings.Gameplay.PPCounter.Static = true
	settings.Gameplay.PPCounter.ShowPPComponents = true

	for _, test := range []struct {
		name     string
		results  api.PPv2Results
		builtIn  bool
		wantText string
		wantFL   string
	}{
		{"built-in cognition", api.PPv2Results{Cognition: 17, Flashlight: 5, Total: 100}, true, "17pp", ""},
		{"official reading and flashlight", api.PPv2Results{Reading: 23, Flashlight: 5, Total: 100}, false, "23pp", "5pp"},
	} {
		t.Run(test.name, func(t *testing.T) {
			display := NewPPDisplay(difficulty.Flashlight)
			display.hasReading = test.builtIn
			display.Add(test.results)
			display.Update(0)
			if display.readingText != test.wantText || display.flashlightText != test.wantFL || display.ppText != "100pp" {
				t.Fatalf("reading=%q flashlight=%q total=%q, want %q, %q, 100pp", display.readingText, display.flashlightText, display.ppText, test.wantText, test.wantFL)
			}
		})
	}
}
