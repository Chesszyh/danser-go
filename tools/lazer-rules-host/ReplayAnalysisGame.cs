using System.Security.Cryptography;
using osu.Framework.Allocation;
using osu.Framework.Graphics;
using osu.Framework.Screens;
using osu.Game;
using osu.Game.Beatmaps;
using osu.Game.Database;
using osu.Game.Online.API;
using osu.Game.Rulesets;
using osu.Game.Rulesets.Judgements;
using osu.Game.Rulesets.Objects;
using osu.Game.Rulesets.Osu;
using osu.Game.Scoring;
using osu.Game.Scoring.Legacy;
using osu.Game.Screens;
using osu.Game.Screens.Play;

namespace Danser.LazerRulesHost;

internal sealed partial class ReplayAnalysisGame : OsuGameBase
{
    protected override int UnhandledExceptionsBeforeCrash => 0;

    private readonly ReplayRequest request;
    private readonly string osuSourceRevision;
    private readonly DummyAPIAccess dummyApi = new();
    private readonly List<JudgementEvent> judgements = [];
    private readonly System.Diagnostics.Stopwatch diagnosticTimer = System.Diagnostics.Stopwatch.StartNew();

    private ReplayPlayer? player;
    private Score? recorded;
    private ScoreSnapshot? recordedSnapshot;
    private SilentWorkingBeatmap? workingBeatmap;
    private ScoreAnalysis? analysis;
    private double seekTarget;
    private bool readyToSeek;
    private bool seekIssued;
    private bool finished;

    public ReplayResponse? Response { get; private set; }
    public Exception? Failure { get; private set; }

    public ReplayAnalysisGame(ReplayRequest request, string osuSourceRevision)
    {
        this.request = request;
        this.osuSourceRevision = osuSourceRevision;
        API = dummyApi;
    }

    protected override void LoadComplete()
    {
        base.LoadComplete();
        Diagnostics.Log("Analysis game loaded");
        Content.Add(dummyApi);
        // RulesetConfigCache populates its entries in a child LoadComplete.
        // Do not let asynchronous player loading race that initialization.
        ScheduleAfterChildren(startReplay);
    }

    protected override void Update()
    {
        base.Update();

        if (Diagnostics.Enabled && readyToSeek && player != null && diagnosticTimer.Elapsed.TotalSeconds >= 10)
        {
            diagnosticTimer.Restart();
            Diagnostics.Log($"Replay state: seekIssued={seekIssued}, current={player.IsCurrentScreen()}, completed={player.GameplayState.HasCompleted}, failed={player.GameplayState.HealthProcessor.HasFailed}, judgements={judgements.Count}");
        }

        if (!finished && readyToSeek && !seekIssued && player?.IsCurrentScreen() == true)
        {
            player.GameplayState.ScoreProcessor.NewJudgement += captureJudgement;
            seekIssued = true;
            Diagnostics.Log($"Seeking replay to {seekTarget}");
            player.Seek(seekTarget);
            Diagnostics.Log("Replay seek returned");
        }

        if (!finished && seekIssued && player?.GameplayState.HasCompleted == true)
            finishReplay();
    }

    private void startReplay()
    {
        Diagnostics.Log($"Available rulesets after child initialization: {string.Join(", ", RulesetStore.AvailableRulesets.Select(r => r.ShortName))}");
        Diagnostics.Log("Loading beatmap and replay");
        try
        {
            var flat = new FlatWorkingBeatmap(request.BeatmapPath);
            workingBeatmap = new SilentWorkingBeatmap(flat.Beatmap, Audio);

            string beatmapHash = Convert.ToHexString(MD5.HashData(File.ReadAllBytes(request.BeatmapPath))).ToLowerInvariant();
            using var replayStream = File.OpenRead(request.ReplayPath);
            recorded = new SuppliedBeatmapDecoder(workingBeatmap, beatmapHash).Parse(replayStream);
            Diagnostics.Log($"Decoded {recorded.Replay.Frames.Count} replay frames");
            recordedSnapshot = ScoreSnapshot.From(recorded.ScoreInfo);

            if (request.ModsJson != null)
                recorded.ScoreInfo.Mods = ModParser.Parse(request.ModsJson);

            Beatmap.Value = workingBeatmap;
            Ruleset.Value = recorded.ScoreInfo.Ruleset;
            SelectedMods.Value = recorded.ScoreInfo.Mods;

            var screens = new OsuScreenStack { RelativeSizeAxes = Axes.Both };
            Content.Add(screens);

            player = new ReplayPlayer(recorded);
            player.OnLoadComplete += _ => onPlayerLoaded();
            screens.Push(player);
            Diagnostics.Log("Replay player pushed to screen stack");
        }
        catch (Exception error)
        {
            fail(error);
        }
    }

    private void onPlayerLoaded()
    {
        Diagnostics.Log("Replay player loaded");
        try
        {
            if (player == null || recorded == null)
                throw new InvalidOperationException("Replay player loaded without a decoded replay.");

            if (!player.LoadedBeatmapSuccessfully)
                throw new InvalidDataException("The replay could not create a playable osu!standard beatmap.");

            analysis = new ScoreAnalysis(player.GameplayState.Beatmap, recorded.ScoreInfo.Mods, player.GameplayState.ScoreProcessor);

            double lastReplayFrame = recorded.Replay.Frames.LastOrDefault()?.Time ?? 0;
            double lastObject = player.GameplayState.Beatmap.HitObjects.LastOrDefault()?.GetEndTime() ?? 0;
            seekTarget = Math.Max(lastReplayFrame, lastObject) + 5000;
            readyToSeek = true;
            Diagnostics.Log($"Replay ready; target {seekTarget}");
        }
        catch (Exception error)
        {
            fail(error);
        }
    }

    private void captureJudgement(JudgementResult result)
    {
        if (player == null || recorded == null || analysis == null)
            return;

        judgements.Add(analysis.Capture(
            result,
            recorded.ScoreInfo,
            player.GameplayState.HealthProcessor.Health.Value,
            player.GameplayState.HealthProcessor.HasFailed));
    }

    private void finishReplay()
    {
        if (finished || player == null || recorded == null || analysis == null)
            return;

        finished = true;
        Diagnostics.Log("Replay completed; calculating response");

        try
        {
            Response = new ReplayResponse(
                Protocol.Version,
                new EngineInfo(typeof(OsuRuleset).FullName!, osuSourceRevision),
                new ReplayInfo(
                    recorded.ScoreInfo.ClientVersion,
                    recorded.ScoreInfo.Mods.Select(mod => mod.Acronym).ToArray(),
                    recorded.Replay.Frames.Count),
                recordedSnapshot ?? throw new InvalidOperationException("The imported replay score was not captured."),
                analysis.FinalSnapshot(
                    recorded.ScoreInfo,
                    player.GameplayState.HealthProcessor.Health.Value,
                    player.GameplayState.HealthProcessor.HasFailed),
                judgements);
        }
        catch (Exception error)
        {
            Failure = error;
        }

        Exit();
    }

    private void fail(Exception error)
    {
        if (finished)
            return;

        finished = true;
        Failure = error;
        Exit();
    }

    private sealed class SuppliedBeatmapDecoder(WorkingBeatmap beatmap, string beatmapHash) : LegacyScoreDecoder
    {
        protected override Ruleset GetRuleset(int rulesetId) => rulesetId == 0
            ? new OsuRuleset()
            : throw new NotSupportedException($"Replay ruleset {rulesetId} is not osu!standard.");

        protected override WorkingBeatmap GetBeatmap(string replayBeatmapHash)
        {
            if (!string.Equals(replayBeatmapHash, beatmapHash, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException($"Replay beatmap hash {replayBeatmapHash} does not match {beatmapHash}.");

            return beatmap;
        }
    }

}
