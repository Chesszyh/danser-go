package osu

import (
	"fmt"
	"math"

	"github.com/wieku/danser-go/app/graphics"
	"github.com/wieku/danser-go/app/rulesets/osu/lazer"
	"github.com/wieku/danser-go/app/rulesets/osu/performance/api"
)

type officialReplayState struct {
	trace         *lazer.ReplayResponse
	next          int
	finalApplied  bool
	health        float64
	failed        bool
	sliderBreaks  uint
	maxTicks      uint
	sliderEnds    uint
	maxSliderEnds uint
}

func (set *OsuRuleSet) UseOfficialLazerReplay(cursor *graphics.Cursor, trace *lazer.ReplayResponse) error {
	if _, exists := set.cursors[cursor]; !exists {
		return fmt.Errorf("official lazer replay cursor is not part of this ruleset")
	}

	if trace.Rejudged.Performance == nil {
		return fmt.Errorf("official lazer replay has no final performance result")
	}

	for index, event := range trace.Judgements {
		if event.ObjectIndex < 0 || event.ObjectIndex >= len(set.beatMap.HitObjects) {
			return fmt.Errorf("official judgement %d references beatmap object %d", index, event.ObjectIndex)
		}

		if _, err := mapOfficialResult(event.Result, event.ObjectPart); err != nil {
			return fmt.Errorf("official judgement %d: %w", index, err)
		}

		if _, err := mapOfficialResult(event.MaxResult, event.ObjectPart); err != nil {
			return fmt.Errorf("official judgement %d max result: %w", index, err)
		}
	}

	set.officialReplays[cursor] = &officialReplayState{trace: trace, health: 1}
	return nil
}

func (set *OsuRuleSet) updateOfficialReplays(time int64) {
	for cursor, state := range set.officialReplays {
		for state.next < len(state.trace.Judgements) {
			event := state.trace.Judgements[state.next]
			if event.JudgedAt > float64(time) {
				break
			}

			state.applyEvent(event)
			set.applyOfficialSnapshot(cursor, event.Score, state)

			result, _ := mapOfficialResult(event.Result, event.ObjectPart)
			maxResult, _ := mapOfficialResult(event.MaxResult, event.ObjectPart)
			combo := Hold
			if event.ComboAfter > event.ComboBefore {
				combo = Increase
			} else if event.ComboAfter == 0 && event.ComboBefore > 0 {
				combo = Reset
			}

			position := set.beatMap.HitObjects[event.ObjectIndex].GetStackedStartPositionMod(set.cursors[cursor].player.diff)
			if event.CursorX != nil && event.CursorY != nil {
				position.X = *event.CursorX
				position.Y = *event.CursorY
			}

			judgement := JudgementResult{
				HitResult:   result,
				MaxResult:   maxResult,
				ComboResult: combo,
				Time:        int64(math.Round(event.JudgedAt)),
				Position:    position,
				Number:      int64(event.ObjectIndex),
			}

			if set.hitListener != nil {
				set.hitListener(cursor, judgement, *set.cursors[cursor].score)
			}

			state.next++
		}

		if state.next == len(state.trace.Judgements) && !state.finalApplied {
			set.applyOfficialSnapshot(cursor, state.trace.Rejudged, state)
			state.finalApplied = true
		}
	}
}

func (state *officialReplayState) applyEvent(event lazer.JudgementEvent) {
	if !event.AffectsScore {
		return
	}

	if event.MaxResult == "LargeTickHit" {
		state.maxTicks++
	}

	if event.MaxResult == "SliderTailHit" {
		state.maxSliderEnds++
	}

	if event.Result == "SliderTailHit" {
		state.sliderEnds++
	}

	if event.ComboBefore > 0 && event.ComboAfter == 0 && event.Result != "Miss" {
		state.sliderBreaks++
	}
}

func (set *OsuRuleSet) applyOfficialSnapshot(cursor *graphics.Cursor, snapshot lazer.ScoreSnapshot, state *officialReplayState) {
	score := set.cursors[cursor].score
	score.Score = snapshot.TotalScore
	score.Accuracy = snapshot.Accuracy
	score.CurrentCombo = uint(snapshot.CurrentCombo)
	score.Combo = uint(snapshot.MaxCombo)
	score.Count300 = uint(snapshot.Statistics["Great"])
	score.CountGeki = uint(snapshot.Statistics["Perfect"])
	score.Count100 = uint(snapshot.Statistics["Ok"])
	score.CountKatu = uint(snapshot.Statistics["Good"])
	score.Count50 = uint(snapshot.Statistics["Meh"])
	score.CountMiss = uint(snapshot.Statistics["Miss"])
	score.CountSB = state.sliderBreaks
	score.MaxTicks = state.maxTicks
	score.SliderEnd = state.sliderEnds
	score.MaxSliderEnd = state.maxSliderEnds
	score.scoredObjects = score.Count300 + score.Count100 + score.Count50 + score.CountMiss
	score.Grade = mapOfficialRank(snapshot.Rank)
	score.PerfectCombo = snapshot.Rank == "X" || snapshot.Rank == "XH"

	if snapshot.Performance != nil {
		score.PP = api.PPv2Results{
			Aim:        snapshot.Performance.Aim,
			Speed:      snapshot.Performance.Speed,
			Acc:        snapshot.Performance.Accuracy,
			Flashlight: snapshot.Performance.Flashlight,
			Reading:    snapshot.Performance.Reading,
			Total:      snapshot.Performance.Total,
		}
	}

	if snapshot.Health != nil {
		state.health = *snapshot.Health
	}

	if snapshot.Failed && !state.failed {
		state.failed = true
		if set.failListener != nil {
			set.failListener(cursor)
		}
	}
}

func mapOfficialResult(result, objectPart string) (HitResult, error) {
	switch result {
	case "Great", "Perfect":
		return Hit300, nil
	case "Ok", "Good":
		return Hit100, nil
	case "Meh":
		return Hit50, nil
	case "Miss":
		return Miss, nil
	case "LargeTickHit":
		if objectPart == "slider-repeat" {
			return SliderRepeat, nil
		}
		return SliderPoint, nil
	case "SmallTickHit":
		return LegacySliderEnd, nil
	case "SmallTickMiss", "LargeTickMiss":
		return SliderMiss, nil
	case "SliderTailHit":
		return SliderEnd, nil
	case "SmallBonus":
		return SpinnerPoints, nil
	case "LargeBonus":
		return SpinnerBonus, nil
	case "IgnoreHit", "IgnoreMiss", "ComboBreak", "LegacyComboIncrease", "None":
		return Ignore, nil
	default:
		return Ignore, fmt.Errorf("unsupported osu! hit result %q", result)
	}
}

func mapOfficialRank(rank string) Grade {
	switch rank {
	case "XH":
		return SSH
	case "X":
		return SS
	case "SH":
		return SH
	case "S":
		return S
	case "A":
		return A
	case "B":
		return B
	case "C":
		return C
	default:
		return D
	}
}
