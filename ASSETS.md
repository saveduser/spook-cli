# Bundled Assets — Provenance & Licensing

SpookCLI ships its mascot, ghost, pumpkin, and sound effects inside the Python
package (`spookcli/assets/`). They are loaded at runtime and are covered by the
project's MIT license **only to the extent the maintainer holds the rights to
them**.

## Inventory

| File | Type | Size (bytes) | Used by | Notes |
|---|---|---:|---|---|
| `pumpkin.png` | PNG 640×640 RGBA | 356,850 | `gtop` header/icon, ghost overlay | Project mascot art |
| `blinking_ghost.gif` | GIF 640×640 | 8,512 | `gtop` mascot | AI-generated ghost loop |
| `ghost-kiro-blink.gif` | GIF 640×640 | 8,512 | ghost overlay | Byte-identical to `blinking_ghost.gif` |
| `ghost_scream.wav` | WAV PCM 16-bit stereo 44.1 kHz | 31,336 | ghost overlay | Failure scream |
| `collected.wav` | WAV PCM 16-bit stereo 44.1 kHz | 49,016 | `gtop` candy collection | Pickup cue |
| `exorcism1.wav` | WAV PCM 16-bit stereo 44.1 kHz | 25,304 | `gtop` exorcise | Kill cue A |
| `exorcism2.wav` | WAV PCM 16-bit stereo 44.1 kHz | 28,112 | `gtop` exorcise | Kill cue B |
| `Ghost_in_the_Cabinet.mp3` | MP3 192 kbps 44.1 kHz | 1,428,650 | `gtop` ambient loop | AI-generated music |
| `Possessed_High_Score.mp3` | MP3 192 kbps 44.1 kHz | 4,086,870 | `gtop` ambient loop | AI-generated music |

Total packaged payload: ≈ 5.75 MiB.

## Provenance

- All nine files were produced for this project; no third-party stock media,
  sample packs, or ripped game assets are bundled.
- The two MP3s retain embedded **C2PA content credentials** from Google's
  generative media services (`Google LLC`, certificate validity
  2026-02-25 → 2027-02-20). These manifests are metadata and do not restrict
  playback; they identify the generating service.
- The WAV files are uncompressed PCM with no embedded metadata.
- The two GIFs are byte-identical, so only one animated loop is effectively
  shipped twice under different names.

## Maintainer checklist before redistribution

1. Confirm you have the right to redistribute every file under the project's
   MIT license. Generative-tool output is governed by the terms accepted when
   the asset was created.
2. If any asset cannot be cleared, replace it with an original or
   permissively-licensed file and update this inventory.
3. Keep the C2PA manifests intact in the MP3s; stripping provenance metadata is
   unnecessary and makes the origin harder to audit.
4. Re-run `python -m build` and `python scripts/audit_dist.py` after changing
   assets so the wheel still contains exactly the nine expected files.
