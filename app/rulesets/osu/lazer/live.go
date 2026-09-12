package lazer

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"os/exec"
	"strings"
	"sync"

	"github.com/wieku/danser-go/framework/files"
	"github.com/wieku/rplpa"
)

type LiveSession struct {
	command *exec.Cmd
	cancel  context.CancelFunc
	input   io.WriteCloser
	encoder *json.Encoder
	decoder *json.Decoder
	stderr  bytes.Buffer

	mutex       sync.Mutex
	nextFrameID int64
	lastTime    float64
	finished    bool
	waitOnce    sync.Once
	waitError   error
}

func StartLive(ctx context.Context, beatmapPath string, mods []rplpa.ModInfo) (*LiveSession, EngineInfo, error) {
	executable, err := files.GetCommandExec("lazer-rules-host", hostCommand)
	if err != nil {
		return nil, EngineInfo{}, fmt.Errorf("official osu!lazer rules host was not found: install %s next to danser", hostCommand)
	}

	modsJSON, err := json.Marshal(mods)
	if err != nil {
		return nil, EngineInfo{}, fmt.Errorf("encode live mods: %w", err)
	}

	workContext, cancel := context.WithCancel(ctx)
	command := exec.CommandContext(workContext, executable, "live", "--beatmap", beatmapPath, "--mods-json", string(modsJSON))
	input, err := command.StdinPipe()
	if err != nil {
		cancel()
		return nil, EngineInfo{}, fmt.Errorf("open official live input: %w", err)
	}

	output, err := command.StdoutPipe()
	if err != nil {
		cancel()
		return nil, EngineInfo{}, fmt.Errorf("open official live output: %w", err)
	}

	session := &LiveSession{
		command:  command,
		cancel:   cancel,
		input:    input,
		encoder:  json.NewEncoder(input),
		decoder:  json.NewDecoder(output),
		lastTime: math.Inf(-1),
	}
	command.Stderr = &session.stderr

	if err := command.Start(); err != nil {
		cancel()
		return nil, EngineInfo{}, fmt.Errorf("start official live rules host: %w", err)
	}

	message, err := session.readMessage()
	if err != nil {
		session.abort()
		return nil, EngineInfo{}, err
	}

	if message.Type != "ready" || message.Engine == nil {
		session.abort()
		return nil, EngineInfo{}, fmt.Errorf("official live rules host returned %q before ready", message.Type)
	}

	if err := validateEngine(*message.Engine); err != nil {
		session.abort()
		return nil, EngineInfo{}, err
	}

	return session, *message.Engine, nil
}

func (session *LiveSession) SendFrame(frame LiveFrame) ([]JudgementEvent, error) {
	session.mutex.Lock()
	defer session.mutex.Unlock()

	if session.finished {
		return nil, errors.New("official live rules session has finished")
	}

	if math.IsNaN(frame.Time) || math.IsInf(frame.Time, 0) || frame.Time < session.lastTime {
		return nil, fmt.Errorf("official live frame time %v is invalid after %v", frame.Time, session.lastTime)
	}

	frameID := session.nextFrameID
	if err := session.encoder.Encode(liveInput{
		Type:    "frame",
		FrameID: frameID,
		Time:    frame.Time,
		X:       frame.X,
		Y:       frame.Y,
		Left:    frame.Left,
		Right:   frame.Right,
		Smoke:   frame.Smoke,
	}); err != nil {
		session.abort()
		return nil, fmt.Errorf("send official live frame: %w", err)
	}

	message, err := session.readMessage()
	if err != nil {
		session.abort()
		return nil, err
	}

	if message.Type != "frame" || message.FrameID == nil || *message.FrameID != frameID {
		session.abort()
		return nil, fmt.Errorf("official live rules host acknowledged an unexpected frame")
	}

	session.nextFrameID++
	session.lastTime = frame.Time
	return message.Judgements, nil
}

func (session *LiveSession) Finish() (*LiveResult, error) {
	session.mutex.Lock()
	defer session.mutex.Unlock()

	if session.finished {
		return nil, errors.New("official live rules session has finished")
	}

	if err := session.encoder.Encode(liveInput{Type: "finish"}); err != nil {
		session.abort()
		return nil, fmt.Errorf("finish official live rules session: %w", err)
	}

	message, err := session.readMessage()
	if err != nil {
		session.abort()
		return nil, err
	}

	if message.Type != "complete" || message.Score == nil {
		session.abort()
		return nil, fmt.Errorf("official live rules host returned %q instead of completion", message.Type)
	}

	session.finished = true
	_ = session.input.Close()
	if err := session.wait(); err != nil {
		return nil, fmt.Errorf("official live rules host failed: %s", session.errorDetail(err))
	}

	session.cancel()
	return &LiveResult{Judgements: message.Judgements, Score: *message.Score}, nil
}

func (session *LiveSession) Close() error {
	session.mutex.Lock()
	defer session.mutex.Unlock()

	if session.finished {
		return nil
	}

	session.finished = true
	session.cancel()
	_ = session.input.Close()
	_ = session.wait()
	return nil
}

func (session *LiveSession) readMessage() (*liveServerMessage, error) {
	var message liveServerMessage
	if err := session.decoder.Decode(&message); err != nil {
		return nil, fmt.Errorf("read official live rules response: %s", session.errorDetail(err))
	}

	if message.ProtocolVersion != ProtocolVersion {
		return nil, fmt.Errorf("protocol version %d is unsupported; expected %d", message.ProtocolVersion, ProtocolVersion)
	}

	if message.Type == "error" {
		if message.Message == "" {
			message.Message = "unknown error"
		}
		return nil, fmt.Errorf("official live rules host failed: %s", message.Message)
	}

	return &message, nil
}

func (session *LiveSession) abort() {
	session.finished = true
	session.cancel()
	_ = session.input.Close()
	_ = session.wait()
}

func (session *LiveSession) wait() error {
	session.waitOnce.Do(func() {
		session.waitError = session.command.Wait()
	})
	return session.waitError
}

func (session *LiveSession) errorDetail(fallback error) string {
	detail := strings.TrimSpace(session.stderr.String())
	if detail != "" {
		return detail
	}

	return fallback.Error()
}

func validateEngine(engine EngineInfo) error {
	if engine.Ruleset != "osu.Game.Rulesets.Osu.OsuRuleset" {
		return fmt.Errorf("ruleset %q is not osu!standard", engine.Ruleset)
	}

	if engine.OsuSourceRevision == "" {
		return errors.New("osu! source revision is missing")
	}

	return nil
}
