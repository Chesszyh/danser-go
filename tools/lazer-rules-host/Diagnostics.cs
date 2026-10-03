namespace Danser.LazerRulesHost;

internal static class Diagnostics
{
    private static readonly bool enabled = Environment.GetEnvironmentVariable("DANSER_LAZER_DIAGNOSTICS") == "1";
    public static bool Enabled => enabled;

    public static void Log(string message)
    {
        if (enabled)
            Console.Error.WriteLine($"[{DateTime.UtcNow:O}] {message}");
    }
}
