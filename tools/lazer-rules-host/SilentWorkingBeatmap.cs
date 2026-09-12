using osu.Framework.Audio;
using osu.Framework.Audio.Track;
using osu.Framework.Graphics.Textures;
using osu.Game.Beatmaps;
using osu.Game.Skinning;

namespace Danser.LazerRulesHost;

internal sealed class SilentWorkingBeatmap : WorkingBeatmap
{
    private readonly IBeatmap beatmap;

    public SilentWorkingBeatmap(IBeatmap beatmap, AudioManager audio)
        : base(beatmap.BeatmapInfo, audio)
    {
        this.beatmap = beatmap;
        LoadTrack();
    }

    public override bool BeatmapLoaded => true;

    protected override IBeatmap GetBeatmap() => beatmap;

    public override Texture? GetBackground() => null;

    protected override Track GetBeatmapTrack() => GetVirtualTrack();

    protected override ISkin? GetSkin() => null;

    public override Stream? GetStream(string storagePath) => null;

    public override bool TryTransferTrack(WorkingBeatmap target) => false;
}
