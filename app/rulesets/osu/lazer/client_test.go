package lazer

import (
	"context"
	"reflect"
	"strings"
	"testing"

	"github.com/wieku/rplpa"
)

func TestDecodeResponse(t *testing.T) {
	response, err := decodeResponse([]byte(`{
		"protocolVersion": 3,
		"engine": {
			"ruleset": "osu.Game.Rulesets.Osu.OsuRuleset",
			"osuSourceRevision": "48c4800"
		},
		"replay": {"clientVersion": "2026.730.0-lazer", "mods": ["HD"], "frameCount": 3},
		"recorded": {"totalScore": 1, "accuracy": 1, "currentCombo": 1, "maxCombo": 1, "rank": "X", "performance": null, "statistics": {}},
		"rejudged": {"totalScore": 1, "accuracy": 1, "currentCombo": 1, "maxCombo": 1, "rank": "X", "performance": {"total": 2.5}, "fullComboPerformance": {"total": 3.5}, "perfectPerformance": {"total": 4.5}, "statistics": {"Great": 1}},
		"judgements": []
	}`))
	if err != nil {
		t.Fatalf("decodeResponse() error = %v", err)
	}

	if response.Engine.OsuSourceRevision != "48c4800" {
		t.Fatalf("source revision = %q", response.Engine.OsuSourceRevision)
	}

	if response.Rejudged.Performance == nil || response.Rejudged.Performance.Total != 2.5 {
		t.Fatalf("performance = %v", response.Rejudged.Performance)
	}

	if response.Rejudged.FullComboPerformance == nil || response.Rejudged.FullComboPerformance.Total != 3.5 {
		t.Fatalf("full combo performance = %v", response.Rejudged.FullComboPerformance)
	}

	if response.Rejudged.PerfectPerformance == nil || response.Rejudged.PerfectPerformance.Total != 4.5 {
		t.Fatalf("perfect performance = %v", response.Rejudged.PerfectPerformance)
	}
}

func TestDecodeResponseRejectsProtocolMismatch(t *testing.T) {
	_, err := decodeResponse([]byte(`{
		"protocolVersion": 4,
		"engine": {
			"ruleset": "osu.Game.Rulesets.Osu.OsuRuleset",
			"osuSourceRevision": "48c4800"
		}
	}`))
	if err == nil || !strings.Contains(err.Error(), "protocol version 4") {
		t.Fatalf("decodeResponse() error = %v", err)
	}
}

func TestCommandArgumentsIncludesEmptyModsOverride(t *testing.T) {
	arguments, err := commandArguments("map.osu", ReplayRequest{ReplayPath: "score.osr", Mods: []rplpa.ModInfo{}})
	if err != nil {
		t.Fatalf("commandArguments() error = %v", err)
	}

	expected := []string{"rejudge", "--beatmap", "map.osu", "--replay", "score.osr", "--mods-json", "[]"}
	if !reflect.DeepEqual(arguments, expected) {
		t.Fatalf("commandArguments() = %q, expected %q", arguments, expected)
	}
}

func TestRejudgeAcceptsEmptyBatch(t *testing.T) {
	responses, err := Rejudge(context.Background(), "map.osu", nil)
	if err != nil {
		t.Fatalf("Rejudge() error = %v", err)
	}

	if len(responses) != 0 {
		t.Fatalf("Rejudge() returned %d responses", len(responses))
	}
}
