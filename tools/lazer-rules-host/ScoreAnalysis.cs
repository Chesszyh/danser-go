using osu.Game.Beatmaps;
using osu.Game.Database;
using osu.Game.Rulesets;
using osu.Game.Rulesets.Difficulty;
using osu.Game.Rulesets.Judgements;
using osu.Game.Rulesets.Mods;
using osu.Game.Rulesets.Objects;
using osu.Game.Rulesets.Osu;
using osu.Game.Rulesets.Osu.Judgements;
using osu.Game.Rulesets.Osu.Objects;
using osu.Game.Rulesets.Scoring;
using osu.Game.Scoring;
using osu.Game.Utils;

namespace Danser.LazerRulesHost;

internal sealed class ScoreAnalysis
{
    private readonly Dictionary<HitObject, (int Index, string Part)> objectLookup = new();
    private readonly Dictionary<HitResult, int> currentMaximumStatistics = new();
    private readonly ScoreProcessor scoreProcessor;
    private readonly PerformanceCalculator performanceCalculator;
    private readonly DifficultyAttributes finalDifficultyAttributes;
    private readonly List<TimedDifficultyAttributes> timedDifficultyAttributes;

    public ScoreAnalysis(IBeatmap beatmap, IReadOnlyList<Mod> mods, ScoreProcessor scoreProcessor)
    {
        this.scoreProcessor = scoreProcessor;
        buildObjectLookup(beatmap);

        var gameplayBeatmap = new GameplayWorkingBeatmap(beatmap);
        var ruleset = new OsuRuleset();
        var difficultyCalculator = ruleset.CreateDifficultyCalculator(gameplayBeatmap);
        finalDifficultyAttributes = difficultyCalculator.Calculate(mods);
        timedDifficultyAttributes = difficultyCalculator.CalculateTimed(mods);
        performanceCalculator = ruleset.CreatePerformanceCalculator();
    }

    public JudgementEvent Capture(JudgementResult result, ScoreInfo scoreTemplate, double health, bool failed)
    {
        var score = scoreTemplate.DeepClone();
        scoreProcessor.PopulateScore(score);

        bool affectsScore = !result.FailedAtJudgement || scoreProcessor.ApplyNewJudgementsWhenFailed;
        if (affectsScore)
        {
            HitResult maxResult = result.Judgement.MaxResult;
            currentMaximumStatistics[maxResult] = currentMaximumStatistics.GetValueOrDefault(maxResult) + 1;
        }

        DifficultyAttributes? difficulty = getTimedDifficulty(result.HitObject.GetEndTime());
        (PerformanceAttributes? performance, PerformanceAttributes? fullCombo, PerformanceAttributes? perfect) = calculatePerformance(score, difficulty);
        (int index, string part) = objectLookup.GetValueOrDefault(result.HitObject, (-1, result.HitObject.GetType().Name));
        var cursor = (result as OsuHitCircleJudgementResult)?.CursorPositionAtHit;

        return new JudgementEvent(
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
            ScoreSnapshot.From(score, performance, fullCombo, perfect, health, failed));
    }

    public ScoreSnapshot FinalSnapshot(ScoreInfo scoreTemplate, double health, bool failed)
    {
        var score = scoreTemplate.DeepClone();
        scoreProcessor.PopulateScore(score);
        (PerformanceAttributes? performance, PerformanceAttributes? fullCombo, PerformanceAttributes? perfect) = calculatePerformance(score, finalDifficultyAttributes);
        return ScoreSnapshot.From(score, performance, fullCombo, perfect, health, failed);
    }

    private DifficultyAttributes? getTimedDifficulty(double objectEndTime)
    {
        if (timedDifficultyAttributes.Count == 0)
            return null;

        int index = timedDifficultyAttributes.BinarySearch(new TimedDifficultyAttributes(objectEndTime, null!));
        if (index < 0)
            index = ~index - 1;

        return timedDifficultyAttributes[Math.Clamp(index, 0, timedDifficultyAttributes.Count - 1)].Attributes;
    }

    private (PerformanceAttributes? Actual, PerformanceAttributes? FullCombo, PerformanceAttributes? Perfect) calculatePerformance(
        ScoreInfo score,
        DifficultyAttributes? difficulty)
    {
        if (difficulty == null)
            return (null, null, null);

        PerformanceAttributes actual = performanceCalculator.Calculate(score, difficulty);
        ScoreInfo fullComboScore = score.DeepClone();
        fullComboScore.MaximumStatistics = new Dictionary<HitResult, int>(currentMaximumStatistics);
        replaceResult(fullComboScore, HitResult.Miss, HitResult.Great);
        replaceResult(fullComboScore, HitResult.SmallTickMiss, HitResult.SmallTickHit);
        replaceResult(fullComboScore, HitResult.LargeTickMiss, HitResult.LargeTickHit);
        fullComboScore.Combo = fullComboScore.MaxCombo = fullComboScore.GetMaximumAchievableCombo();
        fullComboScore.Accuracy = StandardisedScoreMigrationTools.ComputeAccuracy(fullComboScore, scoreProcessor);
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

    private sealed class GameplayWorkingBeatmap(IBeatmap beatmap) : WorkingBeatmap(beatmap.BeatmapInfo, null)
    {
        public override IBeatmap GetPlayableBeatmap(IRulesetInfo ruleset, IReadOnlyList<Mod> mods, CancellationToken cancellationToken)
            => beatmap;

        protected override IBeatmap GetBeatmap() => beatmap;
        public override osu.Framework.Graphics.Textures.Texture GetBackground() => throw new NotImplementedException();
        protected override osu.Framework.Audio.Track.Track GetBeatmapTrack() => throw new NotImplementedException();
        protected override osu.Game.Skinning.ISkin GetSkin() => throw new NotImplementedException();
        public override Stream GetStream(string storagePath) => throw new NotImplementedException();
    }
}
