package lazer

type ReplayResponse struct {
	ProtocolVersion int              `json:"protocolVersion"`
	Engine          EngineInfo       `json:"engine"`
	Replay          ReplayInfo       `json:"replay"`
	Recorded        ScoreSnapshot    `json:"recorded"`
	Rejudged        ScoreSnapshot    `json:"rejudged"`
	Judgements      []JudgementEvent `json:"judgements"`
}

type EngineInfo struct {
	Ruleset           string `json:"ruleset"`
	OsuSourceRevision string `json:"osuSourceRevision"`
}

type ReplayInfo struct {
	ClientVersion string   `json:"clientVersion"`
	Mods          []string `json:"mods"`
	FrameCount    int      `json:"frameCount"`
}

type ScoreSnapshot struct {
	TotalScore   int64          `json:"totalScore"`
	Accuracy     float64        `json:"accuracy"`
	CurrentCombo int            `json:"currentCombo"`
	MaxCombo     int            `json:"maxCombo"`
	Rank         string         `json:"rank"`
	Health       *float64       `json:"health"`
	Failed       bool           `json:"failed"`
	Performance  *Performance   `json:"performance"`
	Statistics   map[string]int `json:"statistics"`
}

type Performance struct {
	Total      float64 `json:"total"`
	Aim        float64 `json:"aim"`
	Speed      float64 `json:"speed"`
	Accuracy   float64 `json:"accuracy"`
	Flashlight float64 `json:"flashlight"`
	Reading    float64 `json:"reading"`
}

type JudgementEvent struct {
	ObjectIndex     int           `json:"objectIndex"`
	ObjectPart      string        `json:"objectPart"`
	ObjectStartTime float64       `json:"objectStartTime"`
	ObjectEndTime   float64       `json:"objectEndTime"`
	Result          string        `json:"result"`
	MaxResult       string        `json:"maxResult"`
	JudgedAt        float64       `json:"judgedAt"`
	HitError        float64       `json:"hitError"`
	AffectsScore    bool          `json:"affectsScore"`
	ComboBefore     int           `json:"comboBefore"`
	ComboAfter      int           `json:"comboAfter"`
	CursorX         *float32      `json:"cursorX"`
	CursorY         *float32      `json:"cursorY"`
	Score           ScoreSnapshot `json:"score"`
}
