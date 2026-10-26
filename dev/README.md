# Maintainer tools

Everything here runs on the maintainer's PC against a clean, extracted GFTE01 disc. Nothing in this folder contains game data.

| Tool | What it does |
|---|---|
| `camelot_lz.py` | Camelot LZSS codec (decode, encode, relocation tables), reimplemented from `main.dol` (`FUN_8000b134`, `FUN_8000a16c`, `FUN_80009fc8`) |
| `unpack_all.py` / `repack_all.py` / `roundtrip_test.py` | Decode every file to `unpacked\` plus a manifest; re-encode and verify |
| `build_mod.py` | Applies every mod change to a copy of the clean tree, checking each original instruction first |
| `make_patch.py` | Diffs the build into `mod/patches/vN.json` (format 2: decoded-level edits plus result hashes) |
| `publish.ps1` | Builds, writes the patch, does a reference build with the friends' C# code, and updates `mod/latest.json` |
| `ppc.py` | Tiny PowerPC encoder for patch stubs, self-tested against known machine code |
| `find_dead_code.py` | Confirms a `main.dol` function is referenced nowhere on the disc, so it's safe to reuse for patch code |
| `dol2elf.py`, `ghidra_export.ps1`, `ghidra_scripts/` | Ghidra headless analysis: `main.dol` plus overlays as one ELF, then exported C and disassembly helpers |
| `find_func.py`, `scan_code.py`, `survey_headers.py`, `patch_text.py` | Investigation helpers |
| `tools/` | Live testing against a running Dolphin (read/write game RAM, trace cameras and power, find values and strings, log draws and messages with `debug_patch.py`) and Ghidra disassembly (`dumpasm.ps1`). See [`RE-NOTES.md`](RE-NOTES.md#testing-workflow). |

**[`RE-NOTES.md`](RE-NOTES.md) is the reference for everything learned about the game's code:** addresses, structures, the hooks each version adds, and the free memory used for patch code. Read it before changing a hook, and add to it when you find something.

## Key facts

- **Game code:** the golf overlay `C/L/V` is a flat image loaded at 0x80400000. `B/U/C` is a second overlay at the same address. Small-data bases are r2 = 0x802DF480 and r13 = 0x802DFA60.
- **Patch code location:** the stubs live over dead functions in `main.dol` (six so far; list in `RE-NOTES.md`). Don't put code at 0x80001800; it gets wiped before the first frame is drawn.
- **Disc layout:** files sit at the outer end of the disc, aligned to 32 bytes. Everything between the file table and 0x1032F9A0 (about 271 MB) is free. `TTMod.Build` moves any file that grows into that space.
- **Game ID:** keep GFTEMD across versions so saves carry over. The version number goes in the banner title.

## Publishing version N

```
powershell -ExecutionPolicy Bypass -File dev\publish.ps1 -Version N -CleanGame <clean .ciso> -CleanDisc <extracted clean disc> -BuildDir <scratch dir>
git add -A
git commit -m "Mod vN"
git push
```

If you change anything in `app\`, bump `app\version.txt` before publishing. `Play.bat` then updates its own scripts on everyone's PC before installing the new mod.
