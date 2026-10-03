using System.Collections.Concurrent;
using System.Text.Json;
using osu.Framework.Allocation;
using osu.Framework.Graphics;
using osu.Framework.Screens;
using osu.Game;
using osu.Game.Beatmaps;
using osu.Game.Online.API;
using osu.Game.Online.API.Requests.Responses;
using osu.Game.Replays;
using osu.Game.Rulesets.Judgements;
using osu.Game.Rulesets.Mods;
using osu.Game.Rulesets.Osu;
using osu.Game.Rulesets.Osu.Replays;
using osu.Game.Scoring;
using osu.Game.Screens;
using osu.Game.Screens.Play;
using osuTK;

namespace Danser.LazerRulesHost;

internal sealed partial class LiveAnalysisGame : OsuGameBase
{
    protected override int UnhandledExceptionsBeforeCrash => 0;

    private static readonly JsonSerializerOptions jsonOptions = new(JsonSerializerDefaults.Web);
    private const double bootstrap_frame_time = -10_000;

    private readonly LiveRequest request;
    private readonly string osuSourceRevision;
    private readonly TextReader input;
    private readonly TextWriter output;
    private readonly DummyAPIAccess dummyApi = new();
    private readonly ConcurrentQueue<LiveInput> inputs = new();
    private readonly Queue<(long Id, double Time)> pendingFrames = new();
    private readonly List<JudgementEvent> pendingJudgements = [];

    private StreamingReplayPlayer? player;
    private Score? score;
    private ScoreAnalysis? analysis;
    private double lastFrameTime = bootstrap_frame_time;
    private volatile bool inputEnded;
    private bool finishing;
    private bool finished;

    public Exception? Failure { get; private set; }

    public LiveAnalysisGame(LiveRequest request, string osuSourceRevision, TextReader input, TextWriter output)
    {
        this.request = request;
        this.osuSourceRevision = osuSourceRevision;
        this.input = input;
        this.output = output;
        API = dummyApi;
    }

    protected override void LoadComplete()
    {
        base.LoadComplete();
        Content.Add(dummyApi);
        Scheduler.Add(startReplay);
        _ = Task.Run(readInput);
    }

    protected override void Update()
    {
        drainInputs();
        base.Update();

        if (finished || player == null)
            return;

        while (pendingFrames.TryPeek(out var pending) && player.CurrentReplayTime >= pending.Time)
        {
            pendingFrames.Dequeue();
            send(new LiveServerMessage(
                "frame",
                Protocol.Version,
                FrameId: pending.Id,
                Judgements: pendingJudgements.ToArray()));
            pendingJudgements.Clear();
        }

        if (finishing && (player.GameplayState.HasCompleted || player.GameplayState.HealthProcessor.HasFailed))
            finish();
    }

    private async Task readInput()
    {
        try
        {
            while (await input.ReadLineAsync() is { } line)
            {
                if (string.IsNullOrWhiteSpace(line))
                    continue;

                LiveInput command = JsonSerializer.Deserialize<LiveInput>(line, jsonOptions)
                                    ?? throw new InvalidDataException("Live input was empty.");
                inputs.Enqueue(command);
            }

            inputEnded = true;
        }
        catch (Exception error)
        {
            inputs.Enqueue(new LiveInput("error", -1, 0, 0, 0, false, false, false));
            Failure = error;
        }
    }

    private void startReplay()
    {
        try
        {
            var flat = new FlatWorkingBeatmap(request.BeatmapPath);
            var workingBeatmap = new SilentWorkingBeatmap(flat.Beatmap, Audio);
            var ruleset = new OsuRuleset();
            Mod[] mods = ModParser.Parse(request.ModsJson);

            score = new Score
            {
                ScoreInfo = new ScoreInfo(workingBeatmap.BeatmapInfo, ruleset.RulesetInfo)
                {
                    ClientVersion = "danser-live",
                    Mods = mods,
                    User = new APIUser { Username = "danser" },
                },
                Replay = new Replay { HasReceivedAllFrames = false },
            };
            score.Replay.Frames.Add(new OsuReplayFrame(bootstrap_frame_time, new Vector2(256, -500)));

            Beatmap.Value = workingBeatmap;
            Ruleset.Value = ruleset.RulesetInfo;
            SelectedMods.Value = mods;

            var screens = new OsuScreenStack { RelativeSizeAxes = Axes.Both };
            Content.Add(screens);

            player = new StreamingReplayPlayer(score);
            player.OnLoadComplete += _ => onPlayerLoaded();
            screens.Push(player);
        }
        catch (Exception error)
        {
            fail(error);
        }
    }

    private void onPlayerLoaded()
    {
        try
        {
            if (player == null || score == null)
                throw new InvalidOperationException("Live replay player loaded without a score.");

            if (!player.LoadedBeatmapSuccessfully)
                throw new InvalidDataException("The live replay could not create a playable osu!standard beatmap.");

            analysis = new ScoreAnalysis(player.GameplayState.Beatmap, score.ScoreInfo.Mods, player.GameplayState.ScoreProcessor);
            player.GameplayState.ScoreProcessor.NewJudgement += captureJudgement;
            send(new LiveServerMessage(
                "ready",
                Protocol.Version,
                new EngineInfo(typeof(OsuRuleset).FullName!, osuSourceRevision)));
        }
        catch (Exception error)
        {
            fail(error);
        }
    }

    private void drainInputs()
    {
        while (!finished && inputs.TryDequeue(out LiveInput? command))
        {
            try
            {
                switch (command.Type)
                {
                    case "frame":
                        appendFrame(command);
                        break;

                    case "finish":
                        beginFinish();
                        break;

                    case "error":
                        throw Failure ?? new InvalidDataException("Live input failed.");

                    default:
                        throw new InvalidDataException($"Unsupported live input type: {command.Type}");
                }
            }
            catch (Exception error)
            {
                fail(error);
            }
        }

        if (!finished && inputEnded && !finishing && inputs.IsEmpty)
            beginFinish();
    }

    private void appendFrame(LiveInput frame)
    {
        if (score == null || player == null || analysis == null)
            throw new InvalidOperationException("Live frame arrived before the rules engine was ready.");

        if (finishing)
            throw new InvalidOperationException("Live frame arrived after finish.");

        if (!double.IsFinite(frame.Time) || !float.IsFinite(frame.X) || !float.IsFinite(frame.Y))
            throw new InvalidDataException("Live frame contains a non-finite value.");

        if (frame.Time < lastFrameTime)
            throw new InvalidDataException($"Live frame time {frame.Time} is before {lastFrameTime}.");

        var actions = new List<OsuAction>(3);
        if (frame.Left) actions.Add(OsuAction.LeftButton);
        if (frame.Right) actions.Add(OsuAction.RightButton);
        if (frame.Smoke) actions.Add(OsuAction.Smoke);

        score.Replay.Frames.Add(new OsuReplayFrame(frame.Time, new Vector2(frame.X, frame.Y), actions.ToArray()));
        pendingFrames.Enqueue((frame.FrameId, frame.Time));
        lastFrameTime = frame.Time;
    }

    private void beginFinish()
    {
        if (score == null)
            throw new InvalidOperationException("Finish arrived before the rules engine was ready.");

        finishing = true;
        score.Replay.HasReceivedAllFrames = true;
    }

    private void captureJudgement(JudgementResult result)
    {
        if (player == null || score == null || analysis == null)
            return;

        pendingJudgements.Add(analysis.Capture(
            result,
            score.ScoreInfo,
            player.GameplayState.HealthProcessor.Health.Value,
            player.GameplayState.HealthProcessor.HasFailed));
    }

    private void finish()
    {
        if (finished || player == null || score == null || analysis == null)
            return;

        finished = true;
        send(new LiveServerMessage(
            "complete",
            Protocol.Version,
            Judgements: pendingJudgements.ToArray(),
            Score: analysis.FinalSnapshot(
                score.ScoreInfo,
                player.GameplayState.HealthProcessor.Health.Value,
                player.GameplayState.HealthProcessor.HasFailed)));
        Exit();
    }

    private void fail(Exception error)
    {
        if (finished)
            return;

        finished = true;
        Failure = error;
        send(new LiveServerMessage("error", Protocol.Version, Message: error.Message));
        Exit();
    }

    private void send(LiveServerMessage message)
    {
        output.WriteLine(JsonSerializer.Serialize(message, jsonOptions));
        output.Flush();
    }

    private sealed partial class StreamingReplayPlayer : ReplayPlayer
    {
        public double CurrentReplayTime => DrawableRuleset.FrameStableClock.CurrentTime;
        public StreamingReplayPlayer(Score score)
            : base(score, new PlayerConfiguration
            {
                AllowUserInteraction = false,
                ShowLeaderboard = false,
                AllowRestart = false,
            })
        {
        }

        protected override bool CheckModsAllowFailure() =>
            GameplayState.Mods.OfType<IApplicableFailOverride>().All(mod => mod.PerformFail());
    }
}
