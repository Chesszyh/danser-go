using Newtonsoft.Json;
using osu.Game.Online.API;
using osu.Game.Rulesets;
using osu.Game.Rulesets.Mods;
using osu.Game.Rulesets.Osu;
using osu.Game.Utils;

namespace Danser.LazerRulesHost;

internal static class ModParser
{
    public static Mod[] Parse(string modsJson)
    {
        APIMod[] proposed = JsonConvert.DeserializeObject<APIMod[]>(modsJson)
                            ?? throw new InvalidDataException("The mods override is not a JSON array.");
        var ruleset = new OsuRuleset();

        if (!ModUtils.InstantiateValidModsForRuleset(ruleset, proposed, out List<Mod> mods))
            throw new InvalidDataException("The mods override contains a mod that osu!standard does not support.");

        if (!ModUtils.CheckValidForGameplay(mods, out List<Mod>? invalid))
            throw new InvalidDataException($"The mods override is not valid for gameplay: {string.Join(", ", invalid?.Select(mod => mod.Acronym) ?? [])}.");

        return mods.ToArray();
    }
}
