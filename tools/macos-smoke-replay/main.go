package main

import (
	"crypto/md5"
	"fmt"
	"math"
	"os"
	"time"

	"github.com/wieku/rplpa"
)

const (
	replayDuration = 75_000
	frameTime      = 16
)

func main() {
	if len(os.Args) != 3 {
		fmt.Fprintln(os.Stderr, "usage: macos-smoke-replay <beatmap.osu> <replay.osr>")
		os.Exit(2)
	}

	beatmap, err := os.ReadFile(os.Args[1])
	if err != nil {
		panic(err)
	}

	replay := buildReplay(beatmap)
	data, err := rplpa.WriteReplay(replay)
	if err != nil {
		panic(err)
	}

	if err = os.WriteFile(os.Args[2], data, 0644); err != nil {
		panic(err)
	}
}

func buildReplay(beatmap []byte) *rplpa.Replay {
	frames := make([]*rplpa.ReplayData, 0, replayDuration/frameTime+1)
	for elapsed := frameTime; elapsed <= replayDuration; elapsed += frameTime {
		t := float64(elapsed)
		pressed := elapsed%500 < 96
		frames = append(frames, &rplpa.ReplayData{
			Time:   frameTime,
			MouseX: 256 + 160*math.Sin(2*math.Pi*t/5000),
			MouseY: 192 + 120*math.Sin(2*math.Pi*t/3500),
			KeyPressed: &rplpa.KeyPressed{
				LeftClick: pressed,
				Key1:      pressed,
			},
		})
	}

	return &rplpa.Replay{
		PlayMode:     0,
		OsuVersion:   20240101,
		BeatmapMD5:   fmt.Sprintf("%x", md5.Sum(beatmap)),
		Username:     "macOS Port Smoke Replay",
		ReplayMD5:    "danser-go-macos-port-smoke",
		Count300:     1,
		Score:        300,
		MaxCombo:     1,
		LifebarGraph: []rplpa.LifeBarGraph{{Time: 0, HP: 1}},
		Timestamp:    time.Date(2026, time.September, 4, 0, 0, 0, 0, time.UTC),
		ReplayData:   frames,
	}
}
