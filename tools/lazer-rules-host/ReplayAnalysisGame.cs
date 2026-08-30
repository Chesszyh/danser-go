using System.Security.Cryptography;
using Newtonsoft.Json;
using osu.Framework.Allocation;
using osu.Framework.Graphics;
using osu.Framework.Screens;
using osu.Game;
using osu.Game.Beatmaps;
using osu.Game.Database;
using osu.Game.Online.API;
using osu.Game.Rulesets;
using osu.Game.Rulesets.Difficulty;
using osu.Game.Rulesets.Judgements;
using osu.Game.Rulesets.Objects;
using osu.Game.Rulesets.Mods;
using osu.Game.Rulesets.Osu;
using osu.Game.Rulesets.Osu.Judgements;
using osu.Game.Rulesets.Osu.Objects;
using osu.Game.Rulesets.Osu.Replays;
using osu.Game.Rulesets.Scoring;
using osu.Game.Scoring;
using osu.Game.Scoring.Legacy;
using osu.Game.Screens;
using osu.Game.Screens.Play;
using osu.Game.Utils;

namespace Danser.LazerRulesHost;

internal sealed partial class ReplayAnalysisGame : OsuGameBase
{
    private readonly ReplayRequest request;
    private readonly string osuSourceRevision;
    private readonly DummyAPIAccess dummyApi = new();
    private readonly List<JudgementEvent> judgements = [];
    private readonly Dictionary<HitObject, (int Index, string Part)> objectLookup = new();
    private readonly Dictionary<HitResult, int> currentMaximumStatistics = new();

    private ReplayPlayer? player;
    private Score? recorded;
    private ScoreSnapshot? recordedSnapshot;
    private SilentWorkingBeatmap? workingBeatmap;
    private PerformanceCalculator? performanceCalculator;
    private DifficultyAttributes? finalDifficultyAttributes;
    private List<TimedDifficultyAttributes>? timedDifficultyAttributes;
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
        Content.Add(dummyApi);
        Scheduler.Add(startReplay);
    }

    protected override void Update()
    {
        base.Update();

        if (!finished && readyToSeek && !seekIssued && player?.IsCurrentScreen() == true)
        {
            player.GameplayState.ScoreProcessor.NewJudgement += captureJudgement;
            seekIssued = true;
            player.Seek(seekTarget);
        }

        if (!finished && seekIssued && player?.GameplayState.HasCompleted == true)
            finishReplay();
    }

    private void startReplay()
    {
        try
        {
            var flat = new FlatWorkingBeatmap(request.BeatmapPath);
            workingBeatmap = new SilentWorkingBeatmap(flat.Beatmap, Audio);

            string beatmapHash = Convert.ToHexString(MD5.HashData(File.ReadAllBytes(request.BeatmapPath))).ToLowerInvariant();
            using var replayStream = File.OpenRead(request.ReplayPath);
            recorded = new SuppliedBeatmapDecoder(workingBeatmap, beatmapHash).Parse(replayStream);
            recordedSnapshot = ScoreSnapshot.From(recorded.ScoreInfo);

            if (request.ModsJson != null)
                recorded.ScoreInfo.Mods = parseMods(request.ModsJson);

            Beatmap.Value = workingBeatmap;
            Ruleset.Value = recorded.ScoreInfo.Ruleset;
            SelectedMods.Value = recorded.ScoreInfo.Mods;

            var screens = new OsuScreenStack { RelativeSizeAxes = Axes.Both };
            Content.Add(screens);

            player = new ReplayPlayer(recorded);
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
            if (player == null || recorded == null)
                throw new InvalidOperationException("Replay player loaded without a decoded replay.");

            if (!player.LoadedBeatmapSuccessfully)
                throw new InvalidDataException("The replay could not create a playable osu!standard beatmap.");

            buildObjectLookup(player.GameplayState.Beatmap);

            var gameplayBeatmap = new GameplayWorkingBeatmap(player.GameplayState.Beatmap);
            var ruleset = new OsuRuleset();
            var difficultyCalculator = ruleset.CreateDifficultyCalculator(gameplayBeatmap);
            finalDifficultyAttributes = difficultyCalculator.Calculate(recorded.ScoreInfo.Mods);
            timedDifficultyAttributes = difficultyCalculator.CalculateTimed(recorded.ScoreInfo.Mods);
            performanceCalculator = ruleset.CreatePerformanceCalculator();

            double lastReplayFrame = recorded.Replay.Frames.LastOrDefault()?.Time ?? 0;
            double lastObject = player.GameplayState.Beatmap.HitObjects.LastOrDefault()?.GetEndTime() ?? 0;
            seekTarget = Math.Max(lastReplayFrame, lastObject) + 5000;
            readyToSeek = true;
        }
        catch (Exception error)
        {
            fail(error);
        }
    }

    private void captureJudgement(JudgementResult result)
    {
        if (player == null || recorded == null || performanceCalculator == null || timedDifficultyAttributes == null)
            return;

        var score = recorded.ScoreInfo.DeepClone();
        player.GameplayState.ScoreProcessor.PopulateScore(score);

        bool affectsScore = !result.FailedAtJudgement || player.GameplayState.ScoreProcessor.ApplyNewJudgementsWhenFailed;
        if (affectsScore)
        {
            HitResult maxResult = result.Judgement.MaxResult;
            currentMaximumStatistics[maxResult] = currentMaximumStatistics.GetValueOrDefault(maxResult) + 1;
        }

        DifficultyAttributes? difficulty = getTimedDifficulty(result.HitObject.GetEndTime());
        (PerformanceAttributes? performance, PerformanceAttributes? fullCombo, PerformanceAttributes? perfect) = calculatePerformance(score, difficulty);
        (int index, string part) = objectLookup.GetValueOrDefault(result.HitObject, (-1, result.HitObject.GetType().Name));
        var cursor = (result as OsuHitCircleJudgementResult)?.CursorPositionAtHit;

        judgements.Add(new JudgementEvent(
            index,
            part,
            result.HitObject.StartTime,
            result.HitObject.GetEndTime(),
            result.Type.ToString(),
            result.Judgement.MaxResult.ToString(),
            result.TimeAbsolute,
            result.TimeOffset,
            affectsScore,
            result.ComboAtJudgement,
            result.ComboAfterJudgement,
            cursor?.X,
            cursor?.Y,
            ScoreSnapshot.From(
                score,
                performance,
                fullCombo,
                perfect,
                health: player.GameplayState.HealthProcessor.Health.Value,
                failed: player.GameplayState.HealthProcessor.HasFailed)));
    }

    private DifficultyAttributes? getTimedDifficulty(double objectEndTime)
    {
        if (timedDifficultyAttributes == null || timedDifficultyAttributes.Count == 0)
            return null;

        int index = timedDifficultyAttributes.BinarySearch(new TimedDifficultyAttributes(objectEndTime, null!));
        if (index < 0)
            index = ~index - 1;

        return timedDifficultyAttributes[Math.Clamp(index, 0, timedDifficultyAttributes.Count - 1)].Attributes;
    }

    private void finishReplay()
    {
        if (finished || player == null || recorded == null || performanceCalculator == null || finalDifficultyAttributes == null)
            return;

        finished = true;

        try
        {
            var rejudged = recorded.ScoreInfo.DeepClone();
            player.GameplayState.ScoreProcessor.PopulateScore(rejudged);
            (PerformanceAttributes? performance, PerformanceAttributes? fullCombo, PerformanceAttributes? perfect) = calculatePerformance(rejudged, finalDifficultyAttributes);

            Response = new ReplayResponse(
                Protocol.Version,
                new EngineInfo(typeof(OsuRuleset).FullName!, osuSourceRevision),
                new ReplayInfo(
                    recorded.ScoreInfo.ClientVersion,
                    recorded.ScoreInfo.Mods.Select(mod => mod.Acronym).ToArray(),
                    recorded.Replay.Frames.Count),
                recordedSnapshot ?? throw new InvalidOperationException("The imported replay score was not captured."),
                ScoreSnapshot.From(
                    rejudged,
                    performance,
                    fullCombo,
                    perfect,
                    health: player.GameplayState.HealthProcessor.Health.Value,
                    failed: player.GameplayState.HealthProcessor.HasFailed),
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

    private Mod[] parseMods(string modsJson)
    {
        APIMod[] proposed = JsonConvert.DeserializeObject<APIMod[]>(modsJson)
                            ?? throw new InvalidDataException("The mods override is not a JSON array.");
        var ruleset = new OsuRuleset();

        if (!ModUtils.InstantiateValidModsForRuleset(ruleset, proposed, out List<Mod> mods))
            throw new InvalidDataException("The mods override contains a mod that osu!standard does not support.");

        if (!ModUtils.CheckValidForGameplay(mods, out List<Mod>? invalid))
            throw new InvalidDataException($"The mods override is not valid for gameplay: {string.Join(", ", invalid.Select(mod => mod.Acronym))}.");

        return mods.ToArray();
    }

    private (PerformanceAttributes? Actual, PerformanceAttributes? FullCombo, PerformanceAttributes? Perfect) calculatePerformance(
        ScoreInfo score,
        DifficultyAttributes? difficulty)
    {
        if (difficulty == null || performanceCalculator == null || player == null)
            return (null, null, null);

        PerformanceAttributes actual = performanceCalculator.Calculate(score, difficulty);
        ScoreInfo fullComboScore = score.DeepClone();
        fullComboScore.MaximumStatistics = new Dictionary<HitResult, int>(currentMaximumStatistics);
        replaceResult(fullComboScore, HitResult.Miss, HitResult.Great);
        replaceResult(fullComboScore, HitResult.SmallTickMiss, HitResult.SmallTickHit);
        replaceResult(fullComboScore, HitResult.LargeTickMiss, HitResult.LargeTickHit);
        fullComboScore.Combo = fullComboScore.MaxCombo = fullComboScore.GetMaximumAchievableCombo();
        fullComboScore.Accuracy = StandardisedScoreMigrationTools.ComputeAccuracy(fullComboScore, player.GameplayState.ScoreProcessor);
        fullComboScore.Passed = true;

        ScoreInfo perfectScore = score.DeepClone();
        perfectScore.MaximumStatistics = new Dictionary<HitResult, int>(currentMaximumStatistics);
        perfectScore.Statistics = new Dictionary<HitResult, int>(currentMaximumStatistics);
        perfectScore.Combo = perfectScore.MaxCombo = perfectScore.GetMaximumAchievableCombo();
        perfectScore.Accuracy = 1;
        perfectScore.Passed = true;

        return (
            actual,
            performanceCalculator.Calculate(fullComboScore, difficulty),
            performanceCalculator.Calculate(perfectScore, difficulty));
    }

    private static void replaceResult(ScoreInfo score, HitResult source, HitResult replacement)
    {
        int count = score.Statistics.GetValueOrDefault(source);
        if (count == 0)
            return;

        score.Statistics[source] = 0;
        score.Statistics[replacement] = score.Statistics.GetValueOrDefault(replacement) + count;
    }

    private void buildObjectLookup(IBeatmap beatmap)
    {
        for (int index = 0; index < beatmap.HitObjects.Count; index++)
        {
            HitObject hitObject = beatmap.HitObjects[index];
            addObject(hitObject, index, topLevelPart(hitObject));
        }
    }

    private void addObject(HitObject hitObject, int index, string part)
    {
        objectLookup[hitObject] = (index, part);

        foreach (HitObject nested in hitObject.NestedHitObjects)
            addObject(nested, index, nestedPart(nested));
    }

    private static string topLevelPart(HitObject hitObject) => hitObject switch
    {
        HitCircle => "circle",
        Slider => "slider",
        Spinner => "spinner",
        _ => hitObject.GetType().Name,
    };

    private static string nestedPart(HitObject hitObject) => hitObject switch
    {
        SliderHeadCircle => "slider-head",
        SliderTailCircle => "slider-tail",
        SliderRepeat => "slider-repeat",
        SliderTick => "slider-tick",
        _ => hitObject.GetType().Name,
    };

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

    private sealed class GameplayWorkingBeatmap(IBeatmap beatmap) : WorkingBeatmap(beatmap.BeatmapInfo, null)
    {
        public override IBeatmap GetPlayableBeatmap(IRulesetInfo ruleset, IReadOnlyList<osu.Game.Rulesets.Mods.Mod> mods, CancellationToken cancellationToken)
            => beatmap;

        protected override IBeatmap GetBeatmap() => beatmap;
        public override osu.Framework.Graphics.Textures.Texture GetBackground() => throw new NotImplementedException();
        protected override osu.Framework.Audio.Track.Track GetBeatmapTrack() => throw new NotImplementedException();
        protected override osu.Game.Skinning.ISkin GetSkin() => throw new NotImplementedException();
        public override Stream GetStream(string storagePath) => throw new NotImplementedException();
    }
}
