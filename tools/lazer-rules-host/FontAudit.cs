using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using osu.Game.Resources;

namespace Danser.LazerRulesHost;

internal static class FontAudit
{
    private const string sourceRevision = "46d344264e5938e168cfbbd2c8fab5f572ebeda4";
    private const string lockHash = "042229e5527079d131e8ce4ce535906ea73f1ec7577d7c8f8398c5a1d30c58e7";

    public static int Run(string manifestPath, string lockPath)
    {
        using var compressed = File.OpenRead(lockPath);
        using var gzip = new GZipStream(compressed, CompressionMode.Decompress);
        using var raw = new MemoryStream();
        gzip.CopyTo(raw);
        byte[] lockedBytes = raw.ToArray();
        require(hex(SHA256.HashData(lockedBytes)) == lockHash, "Resource lock checksum differs");
        using var locked = JsonDocument.Parse(lockedBytes);
        using var manifest = JsonDocument.Parse(File.ReadAllBytes(manifestPath));
        var root = manifest.RootElement;
        require(root.GetProperty("source_commit").GetString() == sourceRevision, "Resource source differs");
        require(root.GetProperty("replacement_font").GetString() == "Inter", "Unexpected replacement font");
        require(root.GetProperty("font_license").GetString() == "OFL-1.1", "Unexpected font licence");
        require(root.GetProperty("pinned_resource_lock_sha256").GetString() == lockHash, "Manifest lock differs");

        Assembly assembly = OsuResources.ResourceAssembly;
        require(assembly.GetName().Name == "osu.Game.Resources", "Resource assembly name differs");
        require(assembly.GetName().Version == new Version(2026, 1021, 0, 0), "Resource assembly version differs");
        var expected = new Dictionary<string, string>();
        int aliases = 0;
        foreach (var mapping in root.GetProperty("mappings").EnumerateArray())
        {
            aliases++;
            expected.Add(resourceName(mapping.GetProperty("output").GetString()!), mapping.GetProperty("output_sha256").GetString()!);
            foreach (var page in mapping.GetProperty("pages").EnumerateArray())
                expected.Add(resourceName(page.GetProperty("output").GetString()!), page.GetProperty("sha256").GetString()!);
        }
        require(aliases == 11 && expected.Count == 50, "Incomplete font replacement manifest");

        var forbidden = new HashSet<string>();
        foreach (var file in locked.RootElement.GetProperty("files").EnumerateObject())
        {
            string path = file.Name;
            if ((path.StartsWith("osu.Game.Resources/Fonts/Torus/") || path.StartsWith("osu.Game.Resources/Fonts/Torus-Alternate/") || path.StartsWith("osu.Game.Resources/Fonts/Venera/"))
                && (path.EndsWith(".bin") || path.EndsWith(".fnt") || path.EndsWith(".png")))
                forbidden.Add(file.Value.GetProperty("git_blob_sha1").GetString()!);
        }
        int checkedResources = 0;
        foreach (string name in assembly.GetManifestResourceNames())
        {
            using Stream stream = assembly.GetManifestResourceStream(name) ?? throw new InvalidDataException(name);
            using var bytes = new MemoryStream();
            stream.CopyTo(bytes);
            byte[] payload = bytes.ToArray();
            using var gitHash = IncrementalHash.CreateHash(HashAlgorithmName.SHA1);
            gitHash.AppendData(Encoding.ASCII.GetBytes($"blob {payload.Length}\0"));
            gitHash.AppendData(payload);
            require(!forbidden.Contains(hex(gitHash.GetHashAndReset())), "Restricted original payload remains: " + name);
            if (expected.Remove(name, out string? digest))
                require(hex(SHA256.HashData(payload)) == digest, "Replacement payload differs: " + name);
            checkedResources++;
        }
        require(expected.Count == 0, "Missing replacement resources: " + string.Join(", ", expected.Keys));
        Console.WriteLine(JsonSerializer.Serialize(new {
            status = "passed", assembly = assembly.FullName, sourceRevision, replacementFont = "Inter",
            replacementDescriptors = aliases, replacementPages = 39, checkedResources,
            restrictedOriginalPayloads = 0, assemblySha256 = hex(SHA256.HashData(File.ReadAllBytes(assembly.Location)))
        }));
        return 0;
    }

    private static string resourceName(string path)
    {
        string[] parts = path.Split('/');
        for (int i = 0; i < parts.Length - 1; i++) parts[i] = parts[i].Replace('-', '_');
        return "osu.Game.Resources." + string.Join('.', parts);
    }
    private static string hex(byte[] value) => Convert.ToHexString(value).ToLowerInvariant();
    private static void require(bool condition, string message)
    {
        if (!condition) throw new InvalidDataException(message);
    }
}
