package dance

import (
	"context"
	"log"
	"math"
	"path/filepath"
	"strings"
	"time"

	"github.com/wieku/danser-go/app/beatmap"
	"github.com/wieku/danser-go/app/beatmap/difficulty"
	"github.com/wieku/danser-go/app/dance/input"
	"github.com/wieku/danser-go/app/dance/movers"
	"github.com/wieku/danser-go/app/dance/schedulers"
	"github.com/wieku/danser-go/app/dance/spinners"
	"github.com/wieku/danser-go/app/graphics"
	"github.com/wieku/danser-go/app/rulesets/osu"
	"github.com/wieku/danser-go/app/rulesets/osu/lazer"
	"github.com/wieku/danser-go/app/settings"
	"github.com/wieku/danser-go/app/utils"
	"github.com/wieku/danser-go/framework/goroutines"
	"github.com/wieku/danser-go/framework/math/vector"
	"github.com/wieku/danser-go/framework/platform/gcontext"
	"github.com/wieku/rplpa"
)

type PlayerController struct {
	bMap     *beatmap.BeatMap
	cursors  []*graphics.Cursor
	ruleset  *osu.OsuRuleSet
	lastTime float64
	counter  float64

	relaxController *input.RelaxInputProcessor
	mouseController schedulers.Scheduler
	firstTime       bool
	position        vector.Vector2f

	rawInput bool
	inside   bool

	quickRestart     bool
	quickRestartTime float64

	officialLive      *lazer.LiveSession
	officialBeatmap   string
	officialMods      []rplpa.ModInfo
	officialFrameSent bool
	officialCompleted bool
	officialCounter   float64
	officialLastTime  float64
	officialLeft      bool
	officialRight     bool
	officialSmoke     bool
}

func NewPlayerController() Controller {
	return &PlayerController{firstTime: true}
}

func (controller *PlayerController) SetBeatMap(beatMap *beatmap.BeatMap) {
	controller.bMap = beatMap
}

func (controller *PlayerController) InitCursors() {
	controller.cursors = []*graphics.Cursor{graphics.NewCursor()}
	controller.cursors[0].IsPlayer = true
	controller.cursors[0].Name = settings.Gameplay.PlayUsername
	controller.cursors[0].ScoreTime = time.Now()
	controller.ruleset = osu.NewOsuRuleset(controller.bMap, controller.cursors, []*difficulty.Difficulty{controller.bMap.Diff.Clone()})
	controller.prepareOfficialLive()

	if !controller.bMap.Diff.CheckModActive(difficulty.Relax) {
		gcontext.RegisterListener(controller.KeyEvent)
	} else {
		controller.relaxController = input.NewRelaxInputProcessor(controller.ruleset, controller.cursors[0])
	}

	gcontext.SetCursorVisible(false)

	if controller.bMap.Diff.CheckModActive(difficulty.Relax2) {
		controller.mouseController = schedulers.NewGenericScheduler(movers.NewLinearMoverSimple, 0, 0)
		controller.mouseController.Init(controller.bMap.GetObjectsCopy(), controller.bMap.Diff, controller.cursors[0], spinners.GetMoverCtorByName("circle"), false)
	} else if settings.Input.MouseHighPrecision {
		controller.rawInput = true
	}
}

func (controller *PlayerController) KeyEvent(event gcontext.KeyEvent) {
	if event.Name == "" {
		return
	}

	processKey(&controller.cursors[0].LeftKey, settings.Input.LeftKey, event)
	processKey(&controller.cursors[0].RightKey, settings.Input.RightKey, event)
	processKey(&controller.cursors[0].SmokeKey, settings.Input.SmokeKey, event)

	if processKey(&controller.quickRestart, settings.Input.RestartKey, event) == gcontext.Press {
		controller.quickRestartTime = controller.lastTime
	}
}

func processKey(value *bool, expect string, event gcontext.KeyEvent) gcontext.Action {
	if strings.EqualFold(event.Name, expect) {
		if event.Action == gcontext.Press {
			*value = true
		} else if event.Action == gcontext.Release {
			*value = false
		}

		return event.Action
	}

	return gcontext.None
}

func (controller *PlayerController) Update(time float64, delta float64) {
	controller.bMap.Update(time)

	if !controller.bMap.Diff.CheckModActive(difficulty.Relax2) {
		mousePosition := vector.NewVec2f(gcontext.GetCursorPosition())

		if controller.rawInput {
			controller.updateRaw(mousePosition)
		} else {
			controller.position = mousePosition
		}

		controller.cursors[0].SetScreenPos(controller.position)
	} else {
		controller.mouseController.Update(time)
	}

	if !controller.bMap.Diff.CheckModActive(difficulty.Relax) {
		mouseEnabled := !settings.Input.MouseButtonsDisabled

		controller.cursors[0].LeftMouse = mouseEnabled && gcontext.GetLeftClick()
		controller.cursors[0].RightMouse = mouseEnabled && gcontext.GetRightClick()

		controller.cursors[0].LeftButton = controller.cursors[0].LeftKey || controller.cursors[0].LeftMouse
		controller.cursors[0].RightButton = controller.cursors[0].RightKey || controller.cursors[0].RightMouse
	} else {
		controller.relaxController.Update(time)
	}

	if controller.quickRestart && time-controller.quickRestartTime > 500 {
		controller.quickRestart = false

		utils.QuickRestart()
	}

	controller.counter += time - controller.lastTime

	if controller.counter >= 1000.0/60 {
		controller.cursors[0].IsReplayFrame = true
		controller.counter -= 1000.0 / 60
	} else {
		controller.cursors[0].IsReplayFrame = false
	}

	controller.updateOfficialLive(time, delta)

	controller.ruleset.UpdateClickFor(controller.cursors[0], int64(time))
	controller.ruleset.UpdateNormalFor(controller.cursors[0], int64(time), false)
	controller.ruleset.UpdatePostFor(controller.cursors[0], int64(time), false)
	controller.ruleset.Update(int64(time))

	controller.lastTime = time

	controller.cursors[0].Update(delta)
}

func (controller *PlayerController) GetRuleset() *osu.OsuRuleSet {
	return controller.ruleset
}

func (controller *PlayerController) GetCursors() []*graphics.Cursor {
	return controller.cursors
}

func (controller *PlayerController) Close() {
	if controller.officialLive != nil {
		_ = controller.officialLive.Close()
	}
}

func (controller *PlayerController) BeginOfficialLive() {
	if controller.officialBeatmap == "" || controller.officialLive != nil {
		return
	}

	session, engine, err := lazer.StartLive(context.Background(), controller.officialBeatmap, controller.officialMods)
	if err != nil {
		panic(err)
	}

	controller.officialLive = session
	log.Printf("Using official osu!lazer rules from %s for live play", engine.OsuSourceRevision)
}

func (controller *PlayerController) prepareOfficialLive() {
	if settings.Gameplay.LazerRulesEngine != "official" || !controller.bMap.Diff.CheckModActive(difficulty.Lazer) {
		return
	}
	if settings.START > 0.01 || !math.IsInf(settings.END, 1) {
		panic("official osu!lazer live rules require a full-map play without -start or -end")
	}

	mods := make([]rplpa.ModInfo, 0)
	for _, mod := range controller.bMap.Diff.ExportMods2() {
		if mod.Acronym != "LZ" {
			mods = append(mods, mod)
		}
	}

	if err := controller.ruleset.UseOfficialLazerLive(controller.cursors[0]); err != nil {
		panic(err)
	}

	controller.officialBeatmap = filepath.Join(settings.General.GetSongsDir(), controller.bMap.Dir, controller.bMap.File)
	controller.officialMods = mods
}

func (controller *PlayerController) updateOfficialLive(currentTime, delta float64) {
	if controller.officialLive == nil || controller.officialCompleted {
		return
	}

	controller.officialCounter += math.Abs(delta)
	cursor := controller.cursors[0]
	endTime := controller.bMap.HitObjects[len(controller.bMap.HitObjects)-1].GetEndTime() + float64(controller.bMap.Diff.Hit50) + 100
	completing := currentTime >= endTime
	sampleDue := controller.officialCounter >= 1000.0/60
	buttonsChanged := cursor.LeftButton != controller.officialLeft ||
		cursor.RightButton != controller.officialRight ||
		cursor.SmokeKey != controller.officialSmoke

	if !controller.officialFrameSent || sampleDue || buttonsChanged || completing {
		frameTime := currentTime
		// BASS can report small backward corrections while replay frame timestamps must remain monotonic.
		if controller.officialFrameSent {
			frameTime = max(frameTime, controller.officialLastTime)
		}

		events, err := controller.officialLive.SendFrame(lazer.LiveFrame{
			Time:  frameTime,
			X:     cursor.RawPosition.X,
			Y:     cursor.RawPosition.Y,
			Left:  cursor.LeftButton,
			Right: cursor.RightButton,
			Smoke: cursor.SmokeKey,
		})
		if err != nil {
			panic(err)
		}

		if err := controller.ruleset.AddOfficialLazerLiveJudgements(cursor, events); err != nil {
			panic(err)
		}

		controller.officialFrameSent = true
		controller.officialCounter = 0
		controller.officialLastTime = frameTime
		controller.officialLeft = cursor.LeftButton
		controller.officialRight = cursor.RightButton
		controller.officialSmoke = cursor.SmokeKey
	}

	if completing {
		result, err := controller.officialLive.Finish()
		if err != nil {
			panic(err)
		}

		if err := controller.ruleset.CompleteOfficialLazerLive(cursor, result); err != nil {
			panic(err)
		}

		controller.officialCompleted = true
	}
}

func (controller *PlayerController) updateRaw(mousePos vector.Vector2f) {
	hovered := gcontext.IsHovered()

	if controller.firstTime {
		controller.position = vector.NewVec2f(gcontext.GetCursorPosition())
		controller.firstTime = false

		if hovered && gcontext.IsFocused() {
			controller.setRawStatus(true)
		} else {
			controller.setRawStatus(false)
		}
	}

	if controller.inside {
		wHalf := vector.NewVec2d(settings.Graphics.GetSizeF()).Scl(0.5).Copy32()

		direction := mousePos.Sub(wHalf).Scl(float32(settings.Input.MouseSensitivity))

		gcontext.SetWindowCursorPosition(wHalf.X, wHalf.Y)

		controller.position = controller.position.Add(direction)
	} else {
		controller.position = mousePos
	}

	if controller.inside &&
		(controller.position.X < 0 || controller.position.X64() > settings.Graphics.GetWidthF() ||
			controller.position.Y < 0 || controller.position.Y64() > settings.Graphics.GetHeightF() || !hovered) {
		controller.setRawStatus(false)
	} else if gcontext.IsFocused() && hovered && !controller.inside {
		controller.setRawStatus(true)
	}
}

func (controller *PlayerController) setRawStatus(state bool) {
	goroutines.CallMain(func() {
		if state {
			log.Println("InputManager: Switching to raw input mode")

			controller.position = vector.NewVec2f(gcontext.GetCursorPosition())

			gcontext.SetRawInput(true)

			gcontext.SetWindowCursorPosition(float32(settings.Graphics.GetWidthF()/2), float32(settings.Graphics.GetHeightF()/2))
		} else {
			log.Println("InputManager: Switching to normal input mode")

			gcontext.SetRawInput(false)

			gcontext.SetCursorPosition(controller.position.X, controller.position.Y)
		}
	})

	controller.inside = state
}
