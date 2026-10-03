using System.Reflection;
using System.Text.Json;
using osu.Framework.Logging;
using osu.Framework.Testing;

namespace Danser.LazerRulesHost;

internal static class Program
{
    private static readonly JsonSerializerOptions json_options = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = false,
    };

    public static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] is "--help" or "-h")
        {
            Console.WriteLine("Usage: danser-lazer-rules rejudge --beatmap <map.osu> --replay <score.osr> [--mods-json <json>]");
            Console.WriteLine("       danser-lazer-rules live --beatmap <map.osu> --mods-json <json>");
            return 0;
        }

        try
        {
            Logger.Enabled = false;

            if (args.FirstOrDefault() == "live")
                return runLive(LiveRequest.Parse(args));

            ReplayRequest request = ReplayRequest.Parse(args);
            Diagnostics.Log("Replay request parsed; creating analysis game");

            var game = new ReplayAnalysisGame(request, getOsuSourceRevision());
            TextWriter standardOutput = Console.Out;

            try
            {
                Console.SetOut(TextWriter.Null);
                using var host = new TestRunHeadlessGameHost("danser-lazer-rules", realtime: false);
                Diagnostics.Log("Headless host created; starting run");
                host.Run(game);
                Diagnostics.Log("Headless host run returned");
            }
            finally
            {
                Console.SetOut(standardOutput);
            }

            if (game.Failure != null)
                throw game.Failure;

            if (game.Response == null)
                throw new InvalidOperationException("The osu! rules engine stopped before producing a result.");

            Console.WriteLine(JsonSerializer.Serialize(game.Response, json_options));
            return 0;
        }
        catch (ArgumentException error)
        {
            Console.Error.WriteLine(error.Message);
            return 2;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine($"lazer rejudgement failed: {error}");
            return 1;
        }
    }

    private static int runLive(LiveRequest request)
    {
        TextWriter standardOutput = Console.Out;
        var game = new LiveAnalysisGame(request, getOsuSourceRevision(), Console.In, standardOutput);

        try
        {
            Console.SetOut(TextWriter.Null);
            using var host = new TestRunHeadlessGameHost("danser-lazer-rules-live", realtime: false);
            host.Run(game);
        }
        finally
        {
            Console.SetOut(standardOutput);
        }

        return game.Failure == null ? 0 : 1;
    }

    private static string getOsuSourceRevision() =>
        Assembly.GetExecutingAssembly()
                .GetCustomAttributes<AssemblyMetadataAttribute>()
                .Single(attribute => attribute.Key == "OsuSourceRevision")
                .Value ?? "unknown";
}
