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
            return 0;
        }

        try
        {
            ReplayRequest request = ReplayRequest.Parse(args);
            Logger.Enabled = false;

            var game = new ReplayAnalysisGame(request, getOsuSourceRevision());
            TextWriter standardOutput = Console.Out;

            try
            {
                Console.SetOut(TextWriter.Null);
                using var host = new TestRunHeadlessGameHost("danser-lazer-rules", realtime: false);
                host.Run(game);
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
            Console.Error.WriteLine($"lazer rejudgement failed: {error.Message}");
            return 1;
        }
    }

    private static string getOsuSourceRevision() =>
        Assembly.GetExecutingAssembly()
                .GetCustomAttributes<AssemblyMetadataAttribute>()
                .Single(attribute => attribute.Key == "OsuSourceRevision")
                .Value ?? "unknown";
}
