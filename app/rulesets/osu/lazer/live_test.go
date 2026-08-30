package lazer

import (
	"bytes"
	"encoding/json"
	"math"
	"strings"
	"testing"
)

type testWriteCloser struct {
	bytes.Buffer
}

func (testWriteCloser) Close() error { return nil }

func TestLiveSessionSendsFrameAndAcceptsMatchingAcknowledgement(t *testing.T) {
	frameID := int64(0)
	input := &testWriteCloser{}
	session := &LiveSession{
		input:    input,
		encoder:  json.NewEncoder(input),
		decoder:  json.NewDecoder(strings.NewReader(`{"type":"frame","protocolVersion":3,"frameId":0,"judgements":[{"result":"Great"}]}`)),
		lastTime: math.Inf(-1),
	}

	events, err := session.SendFrame(LiveFrame{Time: 100, X: 256, Y: 192, Left: true})
	if err != nil {
		t.Fatalf("SendFrame() error = %v", err)
	}

	if len(events) != 1 || events[0].Result != "Great" {
		t.Fatalf("SendFrame() events = %#v", events)
	}

	var sent liveInput
	if err := json.Unmarshal(input.Bytes(), &sent); err != nil {
		t.Fatalf("decode sent frame: %v", err)
	}

	if sent.FrameID != frameID || sent.Time != 100 || sent.X != 256 || sent.Y != 192 || !sent.Left {
		t.Fatalf("sent frame = %#v", sent)
	}
}

func TestLiveSessionRejectsDecreasingFrameTime(t *testing.T) {
	session := &LiveSession{lastTime: 100}
	_, err := session.SendFrame(LiveFrame{Time: 99})
	if err == nil || !strings.Contains(err.Error(), "invalid after") {
		t.Fatalf("SendFrame() error = %v", err)
	}
}

func TestReadLiveMessageRejectsProtocolMismatch(t *testing.T) {
	session := &LiveSession{
		decoder: json.NewDecoder(strings.NewReader(`{"type":"ready","protocolVersion":2}`)),
	}

	_, err := session.readMessage()
	if err == nil || !strings.Contains(err.Error(), "protocol version 2") {
		t.Fatalf("readMessage() error = %v", err)
	}
}

func TestValidateEngineRequiresOfficialOsuStandard(t *testing.T) {
	valid := EngineInfo{
		Ruleset:           "osu.Game.Rulesets.Osu.OsuRuleset",
		OsuSourceRevision: "48c4800",
	}
	if err := validateEngine(valid); err != nil {
		t.Fatalf("validateEngine() error = %v", err)
	}

	invalid := valid
	invalid.Ruleset = "osu.Game.Rulesets.Mania.ManiaRuleset"
	if err := validateEngine(invalid); err == nil {
		t.Fatal("validateEngine() accepted a non-standard ruleset")
	}
}
