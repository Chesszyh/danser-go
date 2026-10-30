package launcher

import (
	"encoding/json"
	"github.com/wieku/danser-go/app/beatmap"
	"github.com/wieku/danser-go/app/beatmap/difficulty"
	"github.com/wieku/rplpa"
	"os"
	"slices"
	"testing"
)

func TestDefaultLazerAndReplayScoring(t *testing.T) {
	b := newBuilder()
	if !b.diff.CheckModActive(difficulty.Lazer) {
		t.Fatal("new gameplay must default to lazer")
	}
	b.setReplay(&rplpa.Replay{OsuVersion: 20260101})
	if b.diff.CheckModActive(difficulty.Lazer) {
		t.Fatal("stable replay was converted to lazer")
	}
	b.removeReplay()
	if !b.diff.CheckModActive(difficulty.Lazer) {
		t.Fatal("new gameplay after a replay must default to lazer")
	}
	b.setReplay(&rplpa.Replay{OsuVersion: 30000000})
	if !b.diff.CheckModActive(difficulty.Lazer) {
		t.Fatal("lazer replay lost lazer scoring")
	}
}

func TestStableGameplayOverridesCLIDefault(t *testing.T) {
	previous := launcherConfig.CurrentMode
	t.Cleanup(func() { launcherConfig.CurrentMode = previous })
	launcherConfig.CurrentMode = Play
	b := newBuilder()
	b.currentMap = &beatmap.BeatMap{MD5: "test"}
	b.diff.SetMods(difficulty.None)
	args := b.getArguments()
	i := slices.Index(args, "-mods2")
	if i < 0 || args[i+1] != "[]" {
		t.Fatalf("stable selection did not override CLI defaults: %v", args)
	}
}

func TestKnockoutDoesNotForceLazer(t *testing.T) {
	previous := launcherConfig.CurrentMode
	t.Cleanup(func() { launcherConfig.CurrentMode = previous })
	launcherConfig.CurrentMode = Knockout
	b := newBuilder()
	b.currentMap = &beatmap.BeatMap{MD5: "test"}
	args := b.getArguments()
	i := slices.Index(args, "-mods2")
	if i < 0 || args[i+1] != "[]" {
		t.Fatalf("knockout forced lazer on stable replays: %v", args)
	}
}

func TestLauncherPlaybackArguments(t *testing.T) {
	previousMode, previousPMode := launcherConfig.CurrentMode, launcherConfig.CurrentPMode
	t.Cleanup(func() { launcherConfig.CurrentMode, launcherConfig.CurrentPMode = previousMode, previousPMode })
	type playbackCase struct {
		Name string
		Args []string
	}
	var cases []playbackCase
	for _, tc := range []struct {
		name string
		mode Mode
		mods difficulty.Modifier
	}{
		{"cursor-stable", CursorDance, difficulty.None},
		{"cursor-lazer", CursorDance, difficulty.Lazer},
		{"autoplay-HR", DanserReplay, difficulty.HardRock},
		{"autoplay-HD-lazer", DanserReplay, difficulty.Hidden | difficulty.Lazer},
	} {
		t.Run(tc.name, func(t *testing.T) {
			launcherConfig.CurrentMode, launcherConfig.CurrentPMode = tc.mode, Screenshot
			b := newBuilder()
			b.currentMap = &beatmap.BeatMap{MD5: os.Getenv("DANSER_SMOKE_MAP_MD5")}
			b.diff.SetMods(tc.mods)
			b.ssTime = 20
			b.outputName = "launcher-" + tc.name
			args := b.getArguments()
			if slices.Contains(args, "-mods") {
				t.Fatalf("launcher must use the JSON mod argument: %v", args)
			}
			cases = append(cases, playbackCase{Name: tc.name, Args: args})
		})
	}
	if path := os.Getenv("DANSER_LAUNCHER_SMOKE_ARGUMENTS"); path != "" {
		data, err := json.Marshal(cases)
		if err != nil {
			t.Fatal(err)
		}
		if err = os.WriteFile(path, data, 0600); err != nil {
			t.Fatal(err)
		}
	}
}
