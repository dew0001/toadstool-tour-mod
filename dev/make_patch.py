"""Turn a built mod tree into a patch file (format 2): only the mod's byte changes, never game data.

Usage: python -I make_patch.py <clean disc dir> <build dir> <out vN.json> <version>

Each changed disc file becomes an "edit" op: runs of new bytes (diffed in decoded form for
compressed files) plus the SHA-1 the patched file must have. publish.ps1 then adds the clean-game
hash list and the SHA-1 of the whole rebuilt disc, using the same C# code friends run.
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
]


def runs(old, new):
    """Byte-diff two equal-length buffers into {at, hex} runs (gaps under 8 bytes merged)."""
    if len(old) != len(new):
        raise SystemExit("decoded file changed size; use a 'replace' op for that")
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


def sha1(b):
    return hashlib.sha1(b).hexdigest()


def main():
    clean, build, out_path, version = sys.argv[1:5]
    patch = {"format": 2, "name": "Toadstool Tour Mod", "version": int(version), "game_id": "GFTE01",
             "new_game_id": "GFTEMD", "files": [], "clean_manifest": {}, "result_sha1": None}
    for rel, compressed in FILES:
        a = open(os.path.join(clean, *rel.split("/")), "rb").read()
        b = open(os.path.join(build, *rel.split("/")), "rb").read()
        if a == b:
            continue
        entry = {"path": rel, "op": "edit", "compressed": compressed, "result_sha1": sha1(b)}
        if compressed:
            if lz.pack(a[0], lz.decompress(b)[0]) != b:
                raise SystemExit(f"{rel}: build file is not our compressor's output")
            entry["type"] = a[0]
            entry["edits"] = runs(lz.decompress(a)[0], lz.decompress(b)[0])
        else:
            entry["edits"] = runs(a, b)
        patch["files"].append(entry)
        print(f"{rel}: {len(entry['edits'])} edit runs, {sum(len(e['hex']) // 2 for e in entry['edits'])} bytes")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\r\n") as f:
        json.dump(patch, f, indent=1)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
