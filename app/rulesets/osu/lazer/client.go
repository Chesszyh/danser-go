package lazer

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"strings"
	"sync"

	"github.com/wieku/danser-go/framework/files"
	"github.com/wieku/rplpa"
)

const (
	ProtocolVersion  = 2
	hostCommand      = "danser-lazer-rules"
	maxParallelHosts = 2
)

type ReplayRequest struct {
	ReplayPath string
	Mods       []rplpa.ModInfo
}

func Rejudge(ctx context.Context, beatmapPath string, requests []ReplayRequest) ([]*ReplayResponse, error) {
	if len(requests) == 0 {
		return []*ReplayResponse{}, nil
	}

	executable, err := files.GetCommandExec("lazer-rules-host", hostCommand)
	if err != nil {
		return nil, fmt.Errorf("official osu!lazer rules host was not found: install %s next to danser", hostCommand)
	}

	results := make([]*ReplayResponse, len(requests))
	workContext, cancel := context.WithCancel(ctx)
	defer cancel()

	jobs := make(chan int)
	var workers sync.WaitGroup
	var firstError error
	var errorOnce sync.Once

	for range min(maxParallelHosts, len(requests)) {
		workers.Add(1)
		go func() {
			defer workers.Done()

			for index := range jobs {
				response, rejudgeErr := rejudgeOne(workContext, executable, beatmapPath, requests[index])
				if rejudgeErr != nil {
					errorOnce.Do(func() {
						firstError = rejudgeErr
						cancel()
					})
					continue
				}

				results[index] = response
			}
		}()
	}

sendJobs:
	for index := range requests {
		select {
		case jobs <- index:
		case <-workContext.Done():
			break sendJobs
		}
	}

	close(jobs)
	workers.Wait()

	if firstError != nil {
		return nil, firstError
	}

	if err := workContext.Err(); err != nil {
		return nil, err
	}

	return results, nil
}

func rejudgeOne(ctx context.Context, executable, beatmapPath string, request ReplayRequest) (*ReplayResponse, error) {
	arguments, err := commandArguments(beatmapPath, request)
	if err != nil {
		return nil, err
	}

	command := exec.CommandContext(ctx, executable, arguments...)
	var standardError bytes.Buffer
	command.Stderr = &standardError

	output, err := command.Output()
	if err != nil {
		detail := strings.TrimSpace(standardError.String())
		if detail == "" {
			detail = err.Error()
		}

		return nil, fmt.Errorf("official osu!lazer rejudgement failed for %s: %s", request.ReplayPath, detail)
	}

	response, err := decodeResponse(output)
	if err != nil {
		return nil, fmt.Errorf("official osu!lazer rules host returned an invalid response: %w", err)
	}

	return response, nil
}

func commandArguments(beatmapPath string, request ReplayRequest) ([]string, error) {
	arguments := []string{"rejudge", "--beatmap", beatmapPath, "--replay", request.ReplayPath}
	if request.Mods == nil {
		return arguments, nil
	}

	modsJSON, err := json.Marshal(request.Mods)
	if err != nil {
		return nil, fmt.Errorf("encode mods override for %s: %w", request.ReplayPath, err)
	}

	return append(arguments, "--mods-json", string(modsJSON)), nil
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
