package launcher

import (
	"github.com/wieku/danser-go/app/beatmap"
	"github.com/wieku/danser-go/app/beatmap/difficulty"
	"github.com/wieku/rplpa"
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
