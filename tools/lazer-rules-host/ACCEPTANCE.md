# Manual osu!lazer acceptance

[简体中文](ACCEPTANCE.zh-CN.md)

Run commands from the danser repository root. Use the newly built `danser-acceptance` and its adjacent `lazer-rules-host` directory.

## Prepare a comparable score

- [ ] Record the official client's version and release stream. Read the host source pin with `git -C third_party/osu rev-parse HEAD`. For exact source parity, use a client built from that revision; a release is suitable when its intervening changes do not affect the tested rules.
- [ ] Play an osu!standard map in the official client and export its replay as `.osr`. Use the identical `.osu` file in danser. Compare the same replay, rather than two independently played attempts.
- [ ] Preserve the replay's mods and all mod settings. Use the client's standardised score display, not classic score display. Record the client's judgement counts, accuracy, maximum combo, score, rank, and locally calculated PP.

## Single replay

```bash
./danser-acceptance -noupdatecheck -replay=/path/to/score.osr \
  -sPatch='{"Gameplay":{"LazerRulesEngine":"official"},"Graphics":{"VSync":false,"FPSCap":120}}'

./lazer-rules-host/danser-lazer-rules rejudge \
  --beatmap /path/to/map.osu --replay /path/to/score.osr > /tmp/danser-score.json
jq '{engine, recorded, rejudged}' /tmp/danser-score.json
```

- [ ] The danser log contains `Using official osu!lazer rules from` with the expected source revision.
- [ ] Final score, maximum combo, rank and judgement counts match the official client exactly. Accuracy and PP agree to the displayed precision; use JSON values when investigating rounding.
- [ ] Compare danser with `rejudged`; `recorded` is the historical result saved in the replay and is not recalculated. Website PP may use a different calculation version. Full-combo and perfect-play PP are hypothetical estimates, not the actual score's PP.
- [ ] At a suspect object, inspect `judgements` in the JSON for its object index, part, result, timing, combo and score snapshot. Check slider heads, ticks, repeats and tails separately; some nested counts are not exposed by danser's HUD.

Repeat with these samples; one replay may cover several rows:

| Sample | Check |
| --- | --- |
| No mods, circles, mixed 300/100/50/miss | Timing, counts, accuracy, score, combo |
| Sliders, missed head/tick/repeat/tail | Nested judgements, combo breaks, accuracy |
| Spinners | Completion and bonus scoring |
| Full combo and perfect accuracy | Maximum combo, rank, final PP |
| Hidden / Hard Rock | Visibility or geometry changes and their scoring |
| Double Time / Half Time with custom rate | Exact mod settings and clock rate |
| Difficulty Adjust | Matching difficulty settings |
| Classic | Slider accuracy and PP calculation |
| No Fail and a failing play | Failure state, score progression, final PP |
| Relax | Automated tapping and judgement results |

## Other entry points

```bash
./danser-acceptance -noupdatecheck -md5=<beatmap-md5> \
  -knockout2='["/path/to/first.osr","/path/to/second.osr"]' \
  -sPatch='{"Gameplay":{"LazerRulesEngine":"official"},"Graphics":{"VSync":false,"FPSCap":120}}'

./danser-acceptance -noupdatecheck -play -quickstart -mods=LZ \
  -md5=<beatmap-md5> \
  -sPatch='{"Gameplay":{"LazerRulesEngine":"official"},"Graphics":{"VSync":false,"FPSCap":120}}'
```

- [ ] `-knockout2`: use two lazer replays of the same map; each player's result matches their separate single-replay run.
- [ ] `-knockout`: place copies in `replays/`, then run with `-knockout -md5=<beatmap-md5>` and the same settings patch. This entry point moves replay files into map-specific subdirectories.
- [ ] `-play`: finish a full map, then test failure and exit. Check responsive input, judgement display, score, combo, health and PP, with no host or backwards-time error. `LZ` selects lazer gameplay; add other mods as needed.
- [ ] Official `-play` rejects `-start` / `-end`. With `Gameplay.LazerRulesEngine` set to `danser`, partial play still works.
- [ ] After exiting, `pgrep -af 'danser-lazer-rules|danser-acceptance'` shows no remaining gameplay or host process.

Manual live play checks the input and display path. It cannot prove exact timing equivalence between independently played attempts; that requires replaying identical input frames through both implementations.

For a mismatch, retain the `.osu`, `.osr`, client version, full launch command, `danser.log`, host JSON, and the first differing object/time or final field.
