package main

import (
	"testing"

	"github.com/wieku/rplpa"
)

func TestBuildReplayRoundTrip(t *testing.T) {
	replay := buildReplay([]byte("fixed beatmap"))
	encoded, err := rplpa.WriteReplay(replay)
	if err != nil {
		t.Fatal(err)
	}

	parsed, err := rplpa.ParseReplay(encoded)
	if err != nil {
		t.Fatal(err)
	}

	if parsed.BeatmapMD5 != "ccf7f455c66cdd475a7ace59ac50b988" {
		t.Fatalf("unexpected beatmap hash: %s", parsed.BeatmapMD5)
	}
	if len(parsed.ReplayData) != replayDuration/frameTime {
		t.Fatalf("unexpected frame count: %d", len(parsed.ReplayData))
	}
	if parsed.ReplayData[0].Time != frameTime {
		t.Fatalf("unexpected first frame time: %f", parsed.ReplayData[0].Time)
	}
}
