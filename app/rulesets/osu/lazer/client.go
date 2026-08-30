package lazer

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"strings"

	"github.com/wieku/danser-go/framework/files"
)

const (
	ProtocolVersion = 1
	hostCommand     = "danser-lazer-rules"
)

func Rejudge(ctx context.Context, beatmapPath, replayPath string) (*ReplayResponse, error) {
	executable, err := files.GetCommandExec("lazer-rules-host", hostCommand)
	if err != nil {
		return nil, fmt.Errorf("official osu!lazer rules host was not found: install %s next to danser", hostCommand)
	}

	command := exec.CommandContext(ctx, executable, "rejudge", "--beatmap", beatmapPath, "--replay", replayPath)
	var standardError bytes.Buffer
	command.Stderr = &standardError

	output, err := command.Output()
	if err != nil {
		detail := strings.TrimSpace(standardError.String())
		if detail == "" {
			detail = err.Error()
		}

		return nil, fmt.Errorf("official osu!lazer rejudgement failed for %s: %s", replayPath, detail)
	}

	response, err := decodeResponse(output)
	if err != nil {
		return nil, fmt.Errorf("official osu!lazer rules host returned an invalid response: %w", err)
	}

	return response, nil
}

func decodeResponse(data []byte) (*ReplayResponse, error) {
	var response ReplayResponse
	if err := json.Unmarshal(data, &response); err != nil {
		return nil, err
	}

	if response.ProtocolVersion != ProtocolVersion {
		return nil, fmt.Errorf("protocol version %d is unsupported; expected %d", response.ProtocolVersion, ProtocolVersion)
	}

	if response.Engine.Ruleset != "osu.Game.Rulesets.Osu.OsuRuleset" {
		return nil, fmt.Errorf("ruleset %q is not osu!standard", response.Engine.Ruleset)
	}

	if response.Engine.OsuSourceRevision == "" {
		return nil, fmt.Errorf("osu! source revision is missing")
	}

	return &response, nil
}
