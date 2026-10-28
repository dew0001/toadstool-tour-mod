"""Turn a built mod tree into a patch file (format 2): only the mod's byte changes, never game data.

Usage: python -I make_patch.py <clean disc dir> <build dir> <out vN.json> <version> [--course8 <course folder>]

Each changed disc file becomes an "edit" op: runs of new bytes (diffed in decoded form for
compressed files) plus the SHA-1 the patched file must have. A compressed file that changes size or
relocation table (Shy Guy's models) becomes a "rebuild" op instead: its new decoded size, runs of the
original moved elsewhere ("copies", so the patch carries no game data), edits on top, and the
relocation table's edits; "base" names another file of the game to start from instead (Shy Guy's files are
built from Koopa Troopa's). An uncompressed file that changes size (Shy Guy's voice samples) becomes a "replace"
op with the new file in base64. A file the game doesn't have (the 8th course's, under files/E/) becomes a
"create" op: its decoded size, copies from "sources" (other files of the game, decoded) and the mod's own bytes as
edits over zeros; the course generator records which ranges it copied from which game file (<file>.prov.json in
the course folder), and "search" lists game files to look for longer matches in. The created files' own bytes
(tens of MB) go in <out>.data.gz, gzip, next to the patch: each create op lists (offset, length) runs into its
decoded file, filled in order from its "data" offset, and the patch's "data" names the file with its size and
SHA-256. publish.ps1 then adds the clean-game hash list and the SHA-1 of the whole rebuilt disc, using the same C#
code friends run.
"""
import base64
import gzip
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
    ("files/C/Y/S", False),   # golfer 16's voice set: sample directory and samples (--shyguy-voice)
    ("files/C/Y/T", False),
    ("files/B/T/O", False),   # the common sound set: his call on the select screen, one sample in place
    ("files/B/T/P", False),
    ("files/B/W/R", True),    # course select icons: the 8th course's (build_mod.py --course8)
    # Tony the Tiger, golfer 17 (build_mod.py --tony)
    ("files/C/W/F", True),
    ("files/C/W/G", True),
    ("files/C/W/H", True),
    ("files/C/W/I", True),
    ("files/C/W/J", True),
    ("files/B/V/L", True),
]
MIN_COPY = 64   # shorter matches with the original stay as edits
# Files the build makes from another file of the game: the patch starts from that one ("base"), so what they share
# goes in as copies. Shy Guy's golfer 16 files are built from Koopa Troopa's (dev/shyguy.py SOURCES), Tony's
# golfer 17 files from his base golfer's (dev/tony.py BASE and SOURCES: Waluigi's or Donkey Kong's).
BASE = {"files/C/W/B": "files/C/V/S", "files/C/W/E": "files/C/V/Z", "files/B/V/K": "files/B/V/D",
        "files/C/W/A": "files/C/V/R"}
import tony  # noqa: E402
BASE.update({f"files/{ours}": f"files/{theirs}" for ours, theirs in tony.SOURCES.items()})


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


def provenance_copies(sources, prov, new):
    """Copies from recorded (source path, source offset, offset in new, length) ranges, split where the bytes
    differ (the generator zeroes relocated words): [(source index, from, to, length)]."""
    out = []
    for path, so, do, ln in prov:
        src = sources[path]
        i = 0
        while i < ln:
            if src[so + i] != new[do + i]:
                i += 1
                continue
            j = i
            while j < ln and src[so + j] == new[do + j]:
                j += 1
            if j - i >= MIN_COPY:
                out.append((path, so + i, do + i, j - i))
            i = j
    return out


def create_entry(clean, rel, b, course):
    """A file the game doesn't have: its decoded bytes from copies of game files plus the mod's own edits."""
    import fnmatch
    kind = b[0]
    new, end = lz.decompress(b) if kind in (1, 2) else (b, None)
    spec = course.get("patch", {}) if course else {}
    prov, search = [], []
    for pattern, how in spec.items():
        if fnmatch.fnmatch(rel[len("files/"):], pattern):
            if how.get("prov"):
                pf = os.path.join(course["_folder"], rel[len("files/"):] + ".prov.json")
                if os.path.exists(pf):
                    prov = json.load(open(pf))["copies"]
            search += how.get("search", [])
    names = sorted({p for p, *_ in prov} | set(search))
    sources = {}
    for path in names:
        raw = open(os.path.join(clean, *path.split("/")), "rb").read()
        sources[path] = lz.decompress(raw)[0] if raw[0] in (1, 2) else raw
    moved = provenance_copies(sources, prov, new)
    work = bytearray(len(new))
    for path, so, do, ln in moved:
        work[do:do + ln] = sources[path][so:so + ln]
    for path in search:   # longer matches with game files the generator didn't record
        for so, do, ln in copies(sources[path], bytes(new)):
            if work[do:do + ln] != new[do:do + ln]:
                moved.append((path, so, do, ln))
                work[do:do + ln] = sources[path][so:so + ln]
    entry = {"path": rel, "op": "create", "compressed": kind in (1, 2), "result_sha1": sha1(b)}
    if kind in (1, 2):
        entry["type"] = kind
        if kind == 2:
            table = relocation_table(b)
            if lz.pack(2, new, table) != b:
                raise SystemExit(f"{rel}: build file is not our compressor's output")
            entry["relocs"] = {"count": len(table) // 8, "edits": runs(bytes(len(table)), table)}
        elif lz.pack(1, new) != b:
            raise SystemExit(f"{rel}: build file is not our compressor's output")
    entry["size"] = len(new)
    entry["sources"] = names
    entry["copies"] = [{"src": names.index(p), "from": so, "to": do, "len": ln} for p, so, do, ln in moved]
    entry["edits"] = runs(bytes(work), bytes(new))
    return entry


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
    course = None
    if "--course8" in sys.argv:
        folder = sys.argv[sys.argv.index("--course8") + 1]
        course = json.load(open(os.path.join(folder, "course.json")))
        course["_folder"] = folder
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
        elif len(a) != len(b):   # a new uncompressed file of the mod's own (Shy Guy's voice samples)
            entry.update(op="replace", data=base64.b64encode(b).decode("ascii"))
        else:
            entry["edits"] = runs(a, b)
        patch["files"].append(entry)
        moved = sum(c["len"] for c in entry.get("copies", []))
        if entry["op"] == "replace":
            print(f"{rel}: replace, {len(b)} bytes")
            continue
        print(f"{rel}: {entry['op']}, {len(entry['edits'])} edit runs, {sum(len(e['hex']) // 2 for e in entry['edits'])} bytes"
              + (f", {len(entry['copies'])} copies ({moved} bytes)" if "copies" in entry else ""))
    # files the game doesn't have (the 8th course: files/E/...)
    for top, dirs, names in sorted(os.walk(os.path.join(build, "files"))):
        dirs.sort()
        for name in sorted(names):
            path = os.path.join(top, name)
            rel = os.path.relpath(path, build).replace(os.sep, "/")
            if os.path.exists(os.path.join(clean, *rel.split("/"))):
                continue
            entry = create_entry(clean, rel, open(path, "rb").read(), course)
            patch["files"].append(entry)
            moved = sum(c["len"] for c in entry["copies"])
            print(f"{rel}: create, {entry['size']} bytes: {len(entry['copies'])} copies ({moved} bytes) from"
                  f" {len(entry['sources'])} game files, {sum(len(e['hex']) // 2 for e in entry['edits'])} bytes of"
                  f" our own")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    data = bytearray()   # the created files' own bytes go in a gzip file next to the patch (tens of MB as hex)
    for entry in patch["files"]:
        if entry["op"] == "create":
            spans = []
            entry["data"] = {"offset": len(data), "runs": spans}
            for e in entry.pop("edits"):
                b = bytes.fromhex(e["hex"])
                spans += [e["at"], len(b)]
                data += b
    if data:
        data_path = os.path.splitext(out_path)[0] + ".data.gz"
        gz = gzip.compress(bytes(data), 9, mtime=0)
        open(data_path, "wb").write(gz)
        patch["data"] = {"path": "mod/patches/" + os.path.basename(data_path), "size": len(data),
                         "sha256": hashlib.sha256(gz).hexdigest()}
        print(f"{data_path}: {len(data)} bytes of the course's own, {len(gz)} gzipped")
    with open(out_path, "w", encoding="utf-8", newline="\r\n") as f:
        json.dump(patch, f, indent=1)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
