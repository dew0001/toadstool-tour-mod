"""Turn a built mod tree into a patch file (format 2): only the mod's byte changes, never game data.

Usage: python -I make_patch.py <clean disc dir> <build dir> <out vN.json> <version>

Each changed disc file becomes an "edit" op: runs of new bytes (diffed in decoded form for
compressed files) plus the SHA-1 the patched file must have. A compressed file that changes size or
relocation table (Shy Guy's models) becomes a "rebuild" op instead: its new decoded size, runs of the
original moved elsewhere ("copies", so the patch carries no game data), edits on top, and the
relocation table's edits; "base" names another file of the game to start from instead (Shy Guy's files are
built from Koopa Troopa's). publish.ps1 then adds the clean-game hash list and the SHA-1 of the whole
rebuilt disc, using the same C# code friends run.
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import camelot_lz as lz  # noqa: E402

FILES = [  # (disc path, compressed?) - every file build_mod.py touches
    ("sys/boot.bin", False),
    ("sys/main.dol", False),
    ("files/opening.bnr", False),
    ("files/C/L/V", True),
    ("files/B/U/C", True),
    # Shy Guy, golfer 16 (build_mod.py --shyguy)
    ("files/C/W/A", True),
    ("files/C/W/B", True),
    ("files/C/W/C", True),
    ("files/C/W/D", True),
    ("files/C/W/E", True),
    ("files/B/V/K", True),
    ("files/B/U/P", True),
    ("files/B/U/M", True),
]
MIN_COPY = 64   # shorter matches with the original stay as edits
# Files the build makes from another file of the game: the patch starts from that one ("base"), so what they share
# goes in as copies. Shy Guy's golfer 16 files are built from Koopa Troopa's (dev/shyguy.py SOURCES).
BASE = {"files/C/W/B": "files/C/V/S", "files/C/W/E": "files/C/V/Z", "files/B/V/K": "files/B/V/D",
        "files/C/W/A": "files/C/V/R"}


def runs(old, new):
    """Byte-diff two equal-length buffers into {at, hex} runs (gaps under 8 bytes merged)."""
    if len(old) != len(new):
        raise SystemExit("decoded file changed size; use a 'rebuild' op for that")
    out, i, n = [], 0, len(old)
    while i < n:
        if old[i] == new[i]:
            i += 1
            continue
        j = i
        while j < n:
            if old[j] != new[j]:
                j += 1
                continue
            k = j
            while k < n and k - j < 8 and old[k] == new[k]:
                k += 1
            if k < n and k - j < 8:
                j = k
            else:
                break
        out.append({"at": i, "hex": new[i:j].hex()})
        i = j
    return out


def copies(old, new):
    """Runs of at least MIN_COPY bytes of `new` that are found in `old` at another place, where `new` differs from
    `old` resized: [(from, to, length)]."""
    base = old[:len(new)] + bytes(max(0, len(new) - len(old)))
    index = {}
    for o in range(0, len(old) - 16, 2):
        key = old[o:o + 16]
        if key.count(key[0]) == 16:   # one repeated byte: nothing worth copying
            continue
        slot = index.setdefault(key, [])
        if len(slot) < 8:
            slot.append(o)
    out, i = [], 0
    while i < len(new) - 16:
        if new[i] == base[i]:
            i += 1
            continue
        best = (0, 0)
        for o in index.get(new[i:i + 16], ()):
            n = 16
            while i + n < len(new) and o + n < len(old) and new[i + n] == old[o + n]:
                n += 1
            best = max(best, (n, o))
        if best[0] >= MIN_COPY:
            out.append((best[1], i, best[0]))
            i += best[0]
        else:
            i += 1
    return out


def relocation_table(raw):
    end = lz.decompress(raw)[1]
    at = (end + 7) & ~7
    table = bytearray()
    while raw[at] != 0xFF:
        table += raw[at:at + 8]
        at += 8
    return bytes(table)


def sha1(b):
    return hashlib.sha1(b).hexdigest()


def main():
    clean, build, out_path, version = sys.argv[1:5]
    patch = {"format": 2, "name": "Toadstool Tour Mod", "version": int(version), "game_id": "GFTE01",
             "new_game_id": "GFTEMD", "files": [], "clean_manifest": {}, "result_sha1": None}
    for rel, compressed in FILES:
        b = open(os.path.join(build, *rel.split("/")), "rb").read()
        if b == open(os.path.join(clean, *rel.split("/")), "rb").read():
            continue
        base = BASE.get(rel, rel)
        a = open(os.path.join(clean, *base.split("/")), "rb").read()
        entry = {"path": rel, "op": "edit", "compressed": compressed, "result_sha1": sha1(b)}
        if base != rel:
            entry["base"] = base
        if compressed:
            old, new = lz.decompress(a)[0], lz.decompress(b)[0]
            entry["type"] = a[0]
            if a[0] == 2:
                old_table, new_table = relocation_table(a), relocation_table(b)
                if lz.pack(2, new, new_table) != b:
                    raise SystemExit(f"{rel}: build file is not our compressor's output")
            elif lz.pack(a[0], new) != b:
                raise SystemExit(f"{rel}: build file is not our compressor's output")
            if a[0] == 2 or len(old) != len(new) or base != rel:
                moved = copies(old, new)
                work = bytearray(old[:len(new)] + bytes(max(0, len(new) - len(old))))
                for src, dst, n in moved:
                    work[dst:dst + n] = old[src:src + n]
                entry.update(op="rebuild", size=len(new), copies=[{"from": s, "to": d, "len": n} for s, d, n in moved],
                             edits=runs(bytes(work), new))
                if a[0] == 2:
                    padded = old_table[:len(new_table)] + bytes(max(0, len(new_table) - len(old_table)))
                    entry["relocs"] = {"count": len(new_table) // 8, "edits": runs(padded, new_table)}
            else:
                entry["edits"] = runs(old, new)
        else:
            entry["edits"] = runs(a, b)
        patch["files"].append(entry)
        moved = sum(c["len"] for c in entry.get("copies", []))
        print(f"{rel}: {entry['op']}, {len(entry['edits'])} edit runs, {sum(len(e['hex']) // 2 for e in entry['edits'])} bytes"
              + (f", {len(entry['copies'])} copies ({moved} bytes)" if "copies" in entry else ""))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\r\n") as f:
        json.dump(patch, f, indent=1)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
