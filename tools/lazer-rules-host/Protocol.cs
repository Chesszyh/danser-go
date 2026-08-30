using osu.Game.Rulesets.Scoring;
using osu.Game.Rulesets.Difficulty;
using osu.Game.Rulesets.Osu.Difficulty;
using osu.Game.Scoring;

namespace Danser.LazerRulesHost;

internal static class Protocol
{
    public const int Version = 2;
}

internal sealed record ReplayRequest(string BeatmapPath, string ReplayPath, string? ModsJson)
{
    public static ReplayRequest Parse(string[] args)
    {
        if (args.Length < 5 || args.Length % 2 == 0 || args[0] != "rejudge")
            throw usageError();

        string? beatmap = null;
        string? replay = null;
        string? modsJson = null;

        for (int i = 1; i < args.Length; i += 2)
        {
            switch (args[i])
            {
                case "--beatmap":
                    beatmap = args[i + 1];
                    break;

                case "--replay":
                    replay = args[i + 1];
                    break;

                case "--mods-json":
                    modsJson = args[i + 1];
                    break;

                default:
                    throw usageError();
            }
        }

        if (string.IsNullOrWhiteSpace(beatmap) || string.IsNullOrWhiteSpace(replay))
            throw usageError();

        beatmap = Path.GetFullPath(beatmap);
        replay = Path.GetFullPath(replay);

        if (!File.Exists(beatmap))
            throw new ArgumentException($"Beatmap file not found: {beatmap}");

        if (!File.Exists(replay))
            throw new ArgumentException($"Replay file not found: {replay}");

        return new ReplayRequest(beatmap, replay, modsJson);
    }

    private static ArgumentException usageError() =>
        new("Expected: rejudge --beatmap <map.osu> --replay <score.osr> [--mods-json <json>]");
}

internal sealed record ReplayResponse(
    int ProtocolVersion,
    EngineInfo Engine,
    ReplayInfo Replay,
    ScoreSnapshot Recorded,
    ScoreSnapshot Rejudged,
    IReadOnlyList<JudgementEvent> Judgements);

internal sealed record EngineInfo(string Ruleset, string OsuSourceRevision);

internal sealed record ReplayInfo(string ClientVersion, IReadOnlyList<string> Mods, int FrameCount);

internal sealed record ScoreSnapshot(
    long TotalScore,
    double Accuracy,
    int CurrentCombo,
    int MaxCombo,
    string Rank,
    double? Health,
    bool Failed,
    PerformanceSnapshot? Performance,
    PerformanceSnapshot? FullComboPerformance,
    PerformanceSnapshot? PerfectPerformance,
    IReadOnlyDictionary<string, int> Statistics)
{
    public static ScoreSnapshot From(
        ScoreInfo score,
        PerformanceAttributes? performance = null,
        PerformanceAttributes? fullComboPerformance = null,
        PerformanceAttributes? perfectPerformance = null,
        double? health = null,
        bool failed = false) =>
        new(
            score.TotalScore,
            score.Accuracy,
            score.Combo,
            score.MaxCombo,
            score.Rank.ToString(),
            health,
            failed,
            performance == null ? null : PerformanceSnapshot.From(performance),
            fullComboPerformance == null ? null : PerformanceSnapshot.From(fullComboPerformance),
            perfectPerformance == null ? null : PerformanceSnapshot.From(perfectPerformance),
            score.Statistics.Where(pair => pair.Value != 0)
                 .ToDictionary(pair => pair.Key.ToString(), pair => pair.Value));
}

internal sealed record PerformanceSnapshot(
    double Total,
    double Aim,
    double Speed,
    double Accuracy,
    double Flashlight,
    double Reading)
{
    public static PerformanceSnapshot From(PerformanceAttributes attributes)
    {
        var osu = (OsuPerformanceAttributes)attributes;
        return new PerformanceSnapshot(osu.Total, osu.Aim, osu.Speed, osu.Accuracy, osu.Flashlight, osu.Reading);
    }
}

internal sealed record JudgementEvent(
    int ObjectIndex,
    string ObjectPart,
    double ObjectStartTime,
    double ObjectEndTime,
    string Result,
    string MaxResult,
    double JudgedAt,
    double HitError,
    bool AffectsScore,
    int ComboBefore,
    int ComboAfter,
    float? CursorX,
    float? CursorY,
    ScoreSnapshot Score);
