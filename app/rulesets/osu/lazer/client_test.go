package lazer

import (
	"strings"
	"testing"
)

func TestDecodeResponse(t *testing.T) {
	response, err := decodeResponse([]byte(`{
		"protocolVersion": 1,
		"engine": {
			"ruleset": "osu.Game.Rulesets.Osu.OsuRuleset",
			"osuSourceRevision": "48c4800"
		},
		"replay": {"clientVersion": "2026.730.0-lazer", "mods": ["HD"], "frameCount": 3},
		"recorded": {"totalScore": 1, "accuracy": 1, "currentCombo": 1, "maxCombo": 1, "rank": "X", "performance": null, "statistics": {}},
		"rejudged": {"totalScore": 1, "accuracy": 1, "currentCombo": 1, "maxCombo": 1, "rank": "X", "performance": {"total": 2.5}, "statistics": {"Great": 1}},
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
}

func TestDecodeResponseRejectsProtocolMismatch(t *testing.T) {
	_, err := decodeResponse([]byte(`{
		"protocolVersion": 2,
		"engine": {
			"ruleset": "osu.Game.Rulesets.Osu.OsuRuleset",
			"osuSourceRevision": "48c4800"
		}
	}`))
	if err == nil || !strings.Contains(err.Error(), "protocol version 2") {
		t.Fatalf("decodeResponse() error = %v", err)
	}
}
