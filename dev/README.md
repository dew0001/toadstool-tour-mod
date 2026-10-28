# Maintainer tools

Everything here runs on the maintainer's PC against a clean, extracted GFTE01 disc. Nothing in this folder contains game data.

| Tool | What it does |
|---|---|
| `camelot_lz.py` | Camelot LZSS codec (decode, encode, relocation tables), reimplemented from `main.dol` (`FUN_8000b134`, `FUN_8000a16c`, `FUN_80009fc8`) |
| `unpack_all.py` / `repack_all.py` / `roundtrip_test.py` | Decode every file to `unpacked\` plus a manifest; re-encode and verify |
| `build_mod.py` | Applies every mod change to a copy of the clean tree, checking each original instruction first |
| `make_patch.py` | Diffs the build into `mod/patches/vN.json` (format 2: decoded-level edits plus result hashes; `rebuild` ops for files that grow or change relocations, with runs of the original moved by copy instructions so no game data goes in; from v11 `create` ops for the 8th course's files, whose own bytes go in `vN.data.gz` next to the patch, about 35 MB, instead of the JSON) |
| `publish.ps1` | Builds, writes the patch, does a reference build with the friends' C# code, and updates `mod/latest.json` |
| `ppc.py` | Tiny PowerPC encoder for patch stubs, self-tested against known machine code |
| `shyguy.py` | Shy Guy as a 17th golfer (`build_mod.py --shyguy <folder> --shyguy-voice <zip> --shyguy-mpt <disc>`): builds golfer 16's models from Koopa Troopa's around his model (Mario Power Tennis', or the OBJ without `--shyguy-mpt`), encodes its texture, renders the menu pictures and the "More" label, sets his stats, builds his voice set |
| `tony.py`, `glb.py` | Tony the Tiger as an 18th golfer (`build_mod.py --tony <folder>`, with `--shyguy`): reads his rigged Blender export (`source\untitled.glb`; `glb.py`), simplifies it to about 4,300 triangles with texture coordinates and bone weights sampled back from the original, fits it to Waluigi's skeleton, and builds golfer 17's models from Waluigi's with the game's own smooth skinning (`skinned_swap`; format in `RE-NOTES.md`), plus his texture, pictures and link record entry. Needs `pip install fast-simplification` (MIT) |
| `course8.py` | The 8th course (`build_mod.py --course8 <course folder>`): course code 8 and hole IDs 1101-1118, hooks for the hole tables, the course select list, name, icon, emblem, HUD card, sky, music and preview (caves 11-13) |
| `course/` | Generates the 8th course, Pebble Beach, from real data: `fetch_data.py` downloads OpenStreetMap and elevation data, `holegen.py <course folder>` builds each hole's model, collision and flyover camera, `coursejson.py <course folder>` writes the `course.json` the build reads. `collision.py`, `holedata.py` and `modlink.py` read and write the hole file formats; `notes/` has the full write-ups |
| `mpt.py` | Reads a Mario Power Tennis disc (GOME01, .iso or .ciso) and Shy Guy's model there (`B/G/P`) for `shyguy.py` |
| `musyx.py` | MusyX sound groups (pool, project, sample directory, samples) and a GameCube DSP ADPCM encoder and decoder |
| `model.py`, `textures.py` | Read character models (meshes, groups, display lists, bones) and texture files (decode RGB5A3, CMPR, I and IA formats; encode RGB5A3) |
| `find_dead_code.py` | Confirms a `main.dol` function is referenced nowhere on the disc, so it's safe to reuse for patch code |
| `dol2elf.py`, `ghidra_export.ps1`, `ghidra_scripts/` | Ghidra headless analysis: `main.dol` plus overlays as one ELF, then exported C and disassembly helpers |
| `find_func.py`, `scan_code.py`, `survey_headers.py`, `patch_text.py` | Investigation helpers |
| `tools/` | Live testing against a running Dolphin (read/write game RAM, trace cameras and power, find values and strings, log draws and messages with `debug_patch.py`) and Ghidra disassembly (`dumpasm.ps1`). See [`RE-NOTES.md`](RE-NOTES.md#testing-workflow). |

**[`RE-NOTES.md`](RE-NOTES.md) is the reference for everything learned about the game's code:** addresses, structures, the hooks each version adds, and the free memory used for patch code. Read it before changing a hook, and add to it when you find something.

## Key facts

- **Game code:** the golf overlay `C/L/V` is a flat image loaded at 0x80400000. `B/U/C` is a second overlay at the same address. Small-data bases are r2 = 0x802DF480 and r13 = 0x802DFA60.
- **Patch code location:** the stubs live over dead functions in `main.dol` (ten so far; list in `RE-NOTES.md`). Don't put code at 0x80001800; it gets wiped before the first frame is drawn.
- **Disc layout:** files sit at the outer end of the disc, aligned to 32 bytes. Everything between the file table and 0x1032F9A0 (about 271 MB) is free. `TTMod.Build` moves any file that grows into that space, and from v11 adds files the game doesn't have (the 8th course's, under a new top-level folder `E`) to the file table and that space.
- **Game ID:** keep GFTEMD across versions so saves carry over. The version number goes in the banner title.

## Publishing version N

```
powershell -ExecutionPolicy Bypass -File dev\publish.ps1 -Version N -CleanGame <clean .ciso> -CleanDisc <extracted clean disc> -BuildDir <scratch dir>
git add -A
git commit -m "Mod vN"
git push
```

If you change anything in `app\`, bump `app\version.txt` before publishing (v10 did: `Install-ModHotkeys` sets the fullscreen toggle and Esc; v11 did: `create` patch ops, the patch's data file and new disc files). `Play.bat` then updates its own scripts on everyone's PC before installing the new mod.

From v7 the build needs Shy Guy's source model: `Shy Guy.obj` and `heyho_body_alb.png` from the Sketchfab download, in `assets\shy-guy` next to the repo (or pass `-ShyGuy <folder>`). Only the converted model goes into the patch: golfer 16's files are built from Koopa's (named as each file's `base` in the patch), and Koopa's data in them goes in as copy instructions, never as bytes. From v8 it also needs his voice clips (`-ShyGuyVoice`, default `assets\shy-guy\mario-power-tennis-shy-guy-voice.zip`: the Sounds Resource's Mario Power Tennis "Shy Guy's Voice"); `shyguy.VOICE` says which clip plays for each of his lines, and the encoded samples go into the patch as a `replace` op. From v9 his model comes from Mario Power Tennis (`-ShyGuyMpt`, default `gamecube_games\Mario Power Tennis (USA) (Rev 1).ciso` two folders above the repo: the maintainer's own disc); the OBJ is then only a fallback, and the converted model and pictures go into the patch as before.

From v11 the build also needs the 8th course (`-Course8`, default `mod\course8` next to the repo). Make it once:

```
python -I dev\course\fetch_data.py
python -I dev\course\holegen.py ..\mod\course8
python -I dev\course\coursejson.py ..\mod\course8
```

`holegen.py` writes each hole's three files under `E\<hole letter>\` plus `A.prov.json`, the ranges its models copied from the game's own files (Cheep Cheep Falls' trees and textures, Blooper Bay's sea and rocks). `make_patch.py` turns those into copy instructions (and searches Cheep Cheep Falls' collision file for the tree meshes the collision files reuse), so only the course's own geometry goes into the patch.
