"""Per-hole data files of Mario Golf: Toadstool Tour (GFTE01): hole table +0xC, +0x10 and +0x14.

    +0x0C  hole-intro camera   type-2 module: up to 3 sets x 10 chained clips of position / rotation / fov keys
    +0x10  Ring Attack rings   raw, 452 bytes: count + 16 slots of (x, y, z, rot_x, rot_y, scale_x, scale_y)
    +0x14  Coin Attack coins   raw: count + count x (x, y, z, flags)

Also reads the two tables in the golf overlay (C/L/V at 0x80400000) that tie holes together:
the hole table at 0x804DCF18 (files per hole) and the hole info table at 0x804CCD60 (par, yardage,
course and hole number), plus its copy in the menu overlay (B/U/C) at 0x80444E60.
See holedata.md for the layouts and the code that reads them.

Usage (python -I holedata.py ...):
  tables                       print the hole table and the hole info table
  dump <hole id>               summary of one hole's three files (e.g. dump 106)
  export <hole id> <out.json>  the three files as JSON (plain lists and dicts)
  build <in.json> <out dir>    write camera (packed type 2 + .bin/.rel), rings and coins from JSON
  test                         parse + rebuild every hole's files and compare byte for byte
"""
import json
import math
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("TTMOD_ROOT", os.path.normpath(os.path.join(HERE, "..", "..", "..")))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..")))
import camelot_lz as lz  # noqa: E402

DISC_FILES = os.path.join(ROOT, "disc", "files")
UNPACKED = os.path.join(ROOT, "unpacked")

# ---------------------------------------------------------------------------------------------------------
# file IDs

def fid_to_path(fid):
    """Game file ID -> (disc path 'A/V/S', packed flag)."""
    k = fid >> 1
    return f"{chr(65 + k // 676)}/{chr(65 + k // 26 % 26)}/{chr(65 + k % 26)}", bool(fid & 1)


def path_to_fid(path, packed):
    a, b, c = (ord(x) - 65 for x in path.split("/"))
    return 2 * (676 * a + 26 * b + c) + (1 if packed else 0)


def read_disc_file(path):
    """Return (type, decoded bytes, relocations) for a disc file. Raw files: (0, bytes, [])."""
    with open(os.path.join(DISC_FILES, *path.split("/")), "rb") as f:
        data = f.read()
    kind, size = lz.header(data)
    if kind not in (1, 2):
        return 0, data, []
    blob, end = lz.decompress(data)
    relocs = lz.relocations(data, end)[0] if kind == 2 else []
    return kind, blob, relocs


# ---------------------------------------------------------------------------------------------------------
# tables in the golf overlay

OVERLAY_BASE = 0x80400000
HOLE_TABLE = 0x804DCF18        # 9 rows x 18 slots x 0x20; entry = row * 18 + slot; looked up by hole ID
HOLE_TABLE_ROWS = 9
HOLE_INFO = 0x804CCD60         # 141 x 0xC (loop bound 0x8D in FUN_80406f90 / FUN_80407048 / FUN_804070c8)
HOLE_INFO_COUNT = 141
MENU_HOLE_INFO = 0x80444E60    # identical copy in the menu overlay B/U/C
HOLE_FIELDS = ("model", "collision", "shared", "camera", "rings", "coins")


def read_hole_table(golf):
    """golf = decoded C/L/V. Returns one dict per entry (file fields are (path, packed) or None)."""
    out = []
    for i in range(HOLE_TABLE_ROWS * 18):
        o = HOLE_TABLE - OVERLAY_BASE + i * 0x20
        w = struct.unpack_from(">8I", golf, o)
        name = ""
        if w[7]:
            n = w[7] - OVERLAY_BASE
            name = golf[n:n + 8].split(b"\0")[0].decode("ascii")
        e = {"index": i, "row": i // 18, "slot": i % 18, "id": w[6], "name": name}
        for k, fid in zip(HOLE_FIELDS, w[:6]):
            e[k] = fid_to_path(fid) if fid else None
        out.append(e)
    return out


def read_hole_info(blob, addr=HOLE_INFO, base=OVERLAY_BASE, count=HOLE_INFO_COUNT):
    """Hole info table: hole ID, yards, Star yards, par, course, hole number, ring order (0 = none)."""
    out = []
    for i in range(count):
        hid, yards, star, par, course, number, order = struct.unpack_from(">IhhBBBB", blob, addr - base + 12 * i)
        out.append({"id": hid, "yards": yards, "star_yards": star, "par": par, "course": course,
                    "number": number, "ring_order": order})
    return out


def build_hole_info(entries):
    return b"".join(struct.pack(">IhhBBBB", e["id"], e["yards"], e["star_yards"], e["par"], e["course"],
                                e["number"], e["ring_order"]) for e in entries)


def hole_by_id(hole_id, golf=None):
    golf = golf if golf is not None else read_disc_file("C/L/V")[1]
    for e in read_hole_table(golf):
        if e["id"] == hole_id:
            return e
    raise KeyError(hole_id)


# ---------------------------------------------------------------------------------------------------------
# +0x0C hole-intro camera (type-2 module)
#
#   0x00 ADDR32 -> ctor list (one 0 word)      0x04 ADDR32 -> dtor list (one 0 word)
#   0x08 b 0x0C (REL24)   0x0C lis r3,root@ha (HA16)   0x10 addi r3,r3,root@l (LO16)   0x14 blr   0x18 0, 0
#   0x20 clips, each: position keys, rotation keys, fov keys, then the 0x1C clip header
#   root: 3 sets x 10 clip pointers (0x78 bytes); set 0 normal, 1 Ring Attack, 2 Coin Attack
#   then the two 0 words the module header points at.
#   clip header: length (frames), n_pos, -> pos, n_rot, -> rot, n_fov, -> fov
#   pos key (0x10): s32 frame, f32 x, y, z     (world = key * 32 * 0.97765)
#   rot key (0x14): s32 frame, f32 qx, qy, qz, qw   (camera looks down its -Z, up = +Y)
#   fov key (0x08): s32 frame, f32 fov (degrees, into camera +0x2C)

CAM_SETS, CAM_SLOTS = 3, 10
CAM_SET_NAMES = ("normal", "ring_attack", "coin_attack")
CAM_POS_SCALE = 0.97765     # 0x804E17B8, applied inside FUN_804ae88c
CAM_WORLD_SCALE = 32.0      # 0x804DA460, applied by the hole-intro state of FUN_80403b0c
STUB = (0x48000000, 0x3C600000, 0x38630000, 0x4E800020)
ADDR32, REL24, HA16, LO16 = 0, 1, 2, 3


def _relocs_from_rel(raw):
    """Raw .rel bytes (unpack_all.py output) -> camelot_lz-style entries."""
    out = []
    for i in range(0, len(raw), 8):
        word, value = struct.unpack_from(">II", raw, i)
        kind = word >> 24
        out.append((kind & ~4, bool(kind & 4), word & 0xFFFFFC, value))
    return out


def _rel_bytes(relocs):
    return b"".join(struct.pack(">II", ((k | (4 if e else 0)) << 24) | off, val) for k, e, off, val in relocs)


def parse_camera(blob, relocs):
    """Decoded +0xC module -> {'clips': [...], 'sets': [[clip index, ...] x 3]}."""
    ptr = {off: val for k, ext, off, val in relocs if k == ADDR32 and not ext}
    ha = [val for k, ext, off, val in relocs if k == HA16 and off == 0x0C]
    lo = [val for k, ext, off, val in relocs if k == LO16 and off == 0x10]
    if not ha or ha != lo:
        raise ValueError("no root stub")
    root = ha[0]
    words = struct.unpack_from(">8I", blob, 0)
    if words[2:6] != STUB or words[6:] != (0, 0):
        raise ValueError("unexpected module header")
    if ptr.get(0) != root + 0x78 or ptr.get(4) != root + 0x7C:
        raise ValueError("ctor/dtor pointers not right after the root")
    clips, order = [], {}
    sets = []
    for s in range(CAM_SETS):
        row = []
        for c in range(CAM_SLOTS):
            at = root + 4 * (s * CAM_SLOTS + c)
            if at not in ptr:
                if struct.unpack_from(">I", blob, at)[0]:
                    raise ValueError("root word without relocation")
                row.append(None)
                continue
            h = ptr[at]
            if h not in order:
                length, npos, _, nrot, _, nfov, _ = struct.unpack_from(">7I", blob, h)
                pp, rp, fp = ptr[h + 8], ptr[h + 16], ptr[h + 24]
                clip = {
                    "length": length,
                    "pos": [list(struct.unpack_from(">i3f", blob, pp + 16 * i)) for i in range(npos)],
                    "rot": [list(struct.unpack_from(">i4f", blob, rp + 20 * i)) for i in range(nrot)],
                    "fov": [list(struct.unpack_from(">if", blob, fp + 8 * i)) for i in range(nfov)],
                }
                order[h] = len(clips)
                clips.append(clip)
            row.append(order[h])
        while row and row[-1] is None:
            row.pop()
        sets.append(row)
    return {"clips": clips, "sets": sets}


def build_camera(cam):
    """Inverse of parse_camera: returns (decoded module bytes, relocation entries)."""
    sets = [list(s) + [None] * (CAM_SLOTS - len(s)) for s in cam["sets"]]
    sets += [[None] * CAM_SLOTS] * (CAM_SETS - len(sets))
    # clips are stored in order of first use (set-major); unused clips go last
    use = []
    for row in sets:
        for c in row:
            if c is not None and c not in use:
                use.append(c)
    use += [i for i in range(len(cam["clips"])) if i not in use]
    out = bytearray(struct.pack(">8I", 0, 0, *STUB, 0, 0))
    relocs = []
    header_at = {}
    for ci in use:
        clip = cam["clips"][ci]
        arrays = []
        for key, fmt, size in (("pos", ">i3f", 16), ("rot", ">i4f", 20), ("fov", ">if", 8)):
            arrays.append(len(out))
            for k in clip[key]:
                out += struct.pack(fmt, *k)
        h = len(out)
        header_at[ci] = h
        out += struct.pack(">7I", clip["length"], len(clip["pos"]), 0, len(clip["rot"]), 0, len(clip["fov"]), 0)
        relocs += [(ADDR32, False, h + 8, arrays[0]), (ADDR32, False, h + 16, arrays[1]),
                   (ADDR32, False, h + 24, arrays[2])]
    root = len(out)
    for s, row in enumerate(sets):
        for c, ci in enumerate(row):
            out += b"\0\0\0\0"
            if ci is not None:
                relocs.append((ADDR32, False, root + 4 * (s * CAM_SLOTS + c), header_at[ci]))
    out += b"\0" * 8
    relocs = [(ADDR32, False, 0, root + 0x78), (ADDR32, False, 4, root + 0x7C), (REL24, False, 8, 0x0C),
              (HA16, False, 0x0C, root), (LO16, False, 0x10, root)] + sorted(relocs, key=lambda r: r[2])
    return bytes(out), relocs


def pack_camera(cam):
    """Complete type-2 disc file for a camera dict (game file ID = 2k + 1)."""
    blob, relocs = build_camera(cam)
    return lz.pack(2, blob, _rel_bytes(relocs))


def check_camera(cam):
    """Problems the game would trip over (empty list = fine)."""
    bad = []
    if not cam["sets"] or not cam["sets"][0] or cam["sets"][0][0] is None:
        bad.append("set 0 slot 0 must be a clip (the game falls back to it)")
    for s, row in enumerate(cam["sets"]):
        if len(row) > CAM_SLOTS:
            bad.append(f"set {s}: more than {CAM_SLOTS} clips")
        if None in row and any(c is not None for c in row[row.index(None):]):
            bad.append(f"set {s}: a gap stops the chain; clips after it never play")
    for i, clip in enumerate(cam["clips"]):
        for key in ("pos", "rot", "fov"):
            keys = clip[key]
            frames = [k[0] for k in keys]
            if len(keys) < 2:
                bad.append(f"clip {i} {key}: needs at least 2 keys")
            elif frames[0] != 0:
                bad.append(f"clip {i} {key}: first key must be frame 0")
            if frames != sorted(set(frames)):
                bad.append(f"clip {i} {key}: frames must be strictly increasing")
            if frames and frames[-1] < clip["length"] - 1:
                bad.append(f"clip {i} {key}: last key before frame length-1 (the game extrapolates)")
    return bad


def _qrot(q, v):
    x, y, z, w = q
    # v' = v + 2w(q x v) + 2 q x (q x v)
    cx, cy, cz = y * v[2] - z * v[1], z * v[0] - x * v[2], x * v[1] - y * v[0]
    dx, dy, dz = y * cz - z * cy, z * cx - x * cz, x * cy - y * cx
    return (v[0] + 2 * (w * cx + dx), v[1] + 2 * (w * cy + dy), v[2] + 2 * (w * cz + dz))


def _sample(keys, t, width):
    """The game's lookup: first key with frame >= t (binary search), else lerp from the key before."""
    lo, hi = 0, len(keys) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if keys[mid][0] < t:
            lo = mid + 1
        else:
            hi = mid
    k = keys[lo]
    if k[0] == t:
        return list(k[1:1 + width]), None
    p = keys[lo - 1]
    return list(p[1:1 + width]), (list(k[1:1 + width]), (t - p[0]) / (k[0] - p[0]))


def camera_at(clip, t):
    """World-space (eye, look_at, up, fov) of a clip at frame t, as the hole intro computes it."""
    a, nxt = _sample(clip["pos"], t, 3)
    if nxt:
        a = [x + (y - x) * nxt[1] for x, y in zip(a, nxt[0])]
    q, nxt = _sample(clip["rot"], t, 4)
    if nxt:  # C_QUATSlerp
        b, s = nxt
        dot = sum(x * y for x, y in zip(q, b))
        if dot < 0:
            b, dot = [-x for x in b], -dot
        if dot > 0.9999:
            q = [x + (y - x) * s for x, y in zip(q, b)]
        else:
            th = math.acos(dot)
            k0, k1 = math.sin((1 - s) * th) / math.sin(th), math.sin(s * th) / math.sin(th)
            q = [k0 * x + k1 * y for x, y in zip(q, b)]
        n = math.sqrt(sum(x * x for x in q))
        q = [x / n for x in q]
    f, nxt = _sample(clip["fov"], t, 1)
    fov = f[0] + (nxt[0][0] - f[0]) * nxt[1] if nxt else f[0]
    pos = [x * CAM_POS_SCALE for x in a]
    fwd, up = _qrot(q, (0.0, 0.0, -1.0)), _qrot(q, (0.0, 1.0, 0.0))
    eye = [x * CAM_WORLD_SCALE for x in pos]
    look = [(p + d) * CAM_WORLD_SCALE for p, d in zip(pos, fwd)]
    return eye, look, list(up), fov


# ---------------------------------------------------------------------------------------------------------
# +0x10 Ring Attack rings (raw; read by FUN_80453020)

RING_SLOTS = 16
RING_FILE_SIZE = 4 + RING_SLOTS * 0x1C


def parse_rings(raw):
    """-> {'rings': [{'pos', 'rot_x', 'rot_y', 'scale_x', 'scale_y'}], 'slack': hex of the unused slots}."""
    n = struct.unpack_from(">I", raw, 0)[0]
    if n > RING_SLOTS:
        raise ValueError(f"{n} rings (max {RING_SLOTS})")
    rings = []
    for i in range(n):
        x, y, z, rx, ry, sx, sy = struct.unpack_from(">7f", raw, 4 + 0x1C * i)
        rings.append({"pos": [x, y, z], "rot_x": rx, "rot_y": ry, "scale_x": sx, "scale_y": sy})
    return {"rings": rings, "slack": raw[4 + 0x1C * n:].hex()}


def build_rings(r):
    out = bytearray(struct.pack(">I", len(r["rings"])))
    for g in r["rings"]:
        out += struct.pack(">7f", *g["pos"], g["rot_x"], g["rot_y"], g["scale_x"], g["scale_y"])
    slack = bytes.fromhex(r.get("slack", ""))
    out += slack if slack else b"\0" * (RING_FILE_SIZE - len(out))  # new files: zero-filled slots
    if len(r["rings"]) > RING_SLOTS:
        raise ValueError("too many rings")
    return bytes(out)


def ring_matrix(g):
    """3x4 world matrix the game builds: T(pos) * S(sx, sy, (sx+sy)/2) * RotY(rot_y) * RotX(rot_x).
    The ring is a torus in the local XY plane (radius 0.9, tube 0.1); it counts as passed when the ball
    crosses the local XY plane within |column 0| (about scale_x) of the centre."""
    sx, sy = g["scale_x"], g["scale_y"]
    sz = (sx + sy) * 0.5
    cy, sny, cx, snx = math.cos(g["rot_y"]), math.sin(g["rot_y"]), math.cos(g["rot_x"]), math.sin(g["rot_x"])
    ry = [[cy, 0, sny], [0, 1, 0], [-sny, 0, cy]]
    rx = [[1, 0, 0], [0, cx, -snx], [0, snx, cx]]
    r = [[sum(ry[i][k] * rx[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    s = (sx, sy, sz)
    return [[s[i] * r[i][j] for j in range(3)] + [g["pos"][i]] for i in range(3)]


# ---------------------------------------------------------------------------------------------------------
# +0x14 Coin Attack coins (raw; read by FUN_80454350)

COIN_SLOTS = 256
COIN_KINDS = {0: "none", 1: "coin", 2: "big"}


def split_coin_flags(f):
    return {"kind": f & 0xF, "stage": (f >> 4) & 7, "collect_group": bool(f & 0x80), "group": f >> 16,
            "extra": (f >> 8) & 0xFF}


def join_coin_flags(c):
    return ((c["group"] & 0xFFFF) << 16 | (c.get("extra", 0) & 0xFF) << 8 | (0x80 if c["collect_group"] else 0)
            | (c["stage"] & 7) << 4 | (c["kind"] & 0xF))


def parse_coins(raw):
    n = struct.unpack_from(">I", raw, 0)[0]
    coins = []
    for i in range(n):
        x, y, z, f = struct.unpack_from(">3fI", raw, 4 + 16 * i)
        c = {"pos": [x, y, z]}
        c.update(split_coin_flags(f))
        coins.append(c)
    tail = raw[4 + 16 * n:]
    out = {"coins": coins}
    if tail:
        out["tail"] = tail.hex()
    return out


def build_coins(c):
    if len(c["coins"]) > COIN_SLOTS:
        raise ValueError(f"more than {COIN_SLOTS} coins")
    out = bytearray(struct.pack(">I", len(c["coins"])))
    for k in c["coins"]:
        out += struct.pack(">3fI", *k["pos"], join_coin_flags(k))
    return bytes(out) + bytes.fromhex(c.get("tail", ""))


def coin_value(kind, stage_now):
    """FUN_80453bf0: points for one coin; stage_now is FUN_8040176c's value for the current hole."""
    if kind != 2:
        return 1
    return 1 if stage_now < 1 else {1: 10, 2: 20}.get(stage_now, 40)


def round_stage(holes_in_round, hole_index):
    """FUN_8040176c: 0..3, rises through the round; coins with stage > this are left out."""
    n = holes_in_round
    if n == 3:
        return hole_index + 1
    if hole_index == n - 1:
        return 3
    if (2 * n) // 3 <= hole_index:
        return 2
    if n // 3 <= hole_index:
        return 1
    return 0


# ---------------------------------------------------------------------------------------------------------
# whole holes

def load_hole(hole_id, golf=None):
    """{'id', 'camera', 'rings', 'coins'} (each None when the file is absent from the disc)."""
    e = hole_by_id(hole_id, golf)
    out = {"id": hole_id, "name": e["name"], "files": {k: e[k][0] if e[k] else None for k in HOLE_FIELDS}}
    out["camera"] = out["rings"] = out["coins"] = None
    path = e["camera"][0]
    if os.path.exists(os.path.join(DISC_FILES, *path.split("/"))):
        kind, blob, rel = read_disc_file(path)
        out["camera"] = parse_camera(blob, rel)
    for key, fn in (("rings", parse_rings), ("coins", parse_coins)):
        path = e[key][0]
        if os.path.exists(os.path.join(DISC_FILES, *path.split("/"))):
            out[key] = fn(read_disc_file(path)[1])
    return out


def cmd_tables():
    golf = read_disc_file("C/L/V")[1]
    print("hole table @0x804DCF18 (row, slot: id name  model collision shared camera rings coins)")
    for e in read_hole_table(golf):
        if e["id"] or e["model"]:
            files = " ".join((e[k][0] + ("*" if e[k][1] else " ")) if e[k] else "-     " for k in HOLE_FIELDS)
            print(f"  {e['row']},{e['slot']:2}: {e['id']:5} {e['name']:8} {files}")
    print("hole info @0x804CCD60 (id, yards, star yards, par, course, hole, ring order)")
    for e in read_hole_info(golf):
        print(f"  {e['id']:4} {e['yards']:4} {e['star_yards']:4}  par {e['par']}  course {e['course']:2}"
              f"  hole {e['number']:2}  ring order {e['ring_order']}")
    menu = read_disc_file("B/U/C")[1]
    same = build_hole_info(read_hole_info(menu, MENU_HOLE_INFO)) == build_hole_info(read_hole_info(golf))
    print("menu overlay copy @0x80444E60:", "identical" if same else "DIFFERENT")


def cmd_dump(hole_id):
    h = load_hole(hole_id)
    print(f"hole {hole_id} {h['name']}: files {h['files']}")
    cam = h["camera"]
    if cam:
        for s, row in enumerate(cam["sets"]):
            print(f"  camera set {s} ({CAM_SET_NAMES[s]}): clips {row}")
        for i, c in enumerate(cam["clips"]):
            eye0, look0, _, fov0 = camera_at(c, 0)
            eye1, look1, _, _ = camera_at(c, c["length"] - 1)
            print(f"  clip {i}: {c['length']} frames, keys pos {len(c['pos'])} rot {len(c['rot'])} fov {len(c['fov'])};"
                  f" eye {[round(v, 1) for v in eye0]} -> {[round(v, 1) for v in eye1]}, fov {fov0:.2f}")
        for p in check_camera(cam):
            print("  !", p)
    if h["rings"]:
        for i, g in enumerate(h["rings"]["rings"]):
            print(f"  ring {i}: pos {[round(v, 1) for v in g['pos']]} rot x {math.degrees(g['rot_x']):.1f}"
                  f" y {math.degrees(g['rot_y']):.1f} deg, scale {g['scale_x']:.2f} x {g['scale_y']:.2f}")
    if h["coins"]:
        groups = {}
        for c in h["coins"]["coins"]:
            groups.setdefault(c["group"], []).append(c)
        print(f"  coins: {len(h['coins']['coins'])} in {len(groups)} groups")
        for g, cs in sorted(groups.items()):
            kinds = sorted({(COIN_KINDS.get(c['kind'], c['kind']), c['stage'], c['collect_group']) for c in cs})
            mid = [round(sum(c["pos"][i] for c in cs) / len(cs), 1) for i in range(3)]
            print(f"    group {g}: {len(cs)} x {kinds} around {mid}")


def cmd_export(hole_id, out):
    h = load_hole(hole_id)
    with open(out, "w") as f:
        json.dump(h, f, indent=1)
    print("wrote", out)


def cmd_build(src, out_dir):
    with open(src) as f:
        h = json.load(f)
    os.makedirs(out_dir, exist_ok=True)
    if h.get("camera"):
        for p in check_camera(h["camera"]):
            print("warning:", p)
        blob, rel = build_camera(h["camera"])
        for name, data in (("camera.bin", blob), ("camera.rel", _rel_bytes(rel)), ("camera", pack_camera(h["camera"]))):
            with open(os.path.join(out_dir, name), "wb") as f:
                f.write(data)
    if h.get("rings"):
        with open(os.path.join(out_dir, "rings"), "wb") as f:
            f.write(build_rings(h["rings"]))
    if h.get("coins"):
        with open(os.path.join(out_dir, "coins"), "wb") as f:
            f.write(build_coins(h["coins"]))
    print("wrote", out_dir)


def cmd_test():
    golf = read_disc_file("C/L/V")[1]
    seen, ok, bad = set(), 0, 0
    for e in read_hole_table(golf):
        if not e["id"]:
            continue
        for key in ("camera", "rings", "coins"):
            path = e[key][0]
            if path in seen or not os.path.exists(os.path.join(DISC_FILES, *path.split("/"))):
                continue
            seen.add(path)
            kind, blob, rel = read_disc_file(path)
            if key == "camera":
                cam = parse_camera(blob, rel)
                cam = json.loads(json.dumps(cam))      # through plain JSON, as an editor would
                blob2, rel2 = build_camera(cam)
                same = blob2 == blob and rel2 == rel
                # and the container the game loads: decode our packed file again
                p = pack_camera(cam)
                b3, end = lz.decompress(p)
                same = same and b3 == blob and lz.relocations(p, end)[0] == rel
                notes = check_camera(cam)
            else:
                d = (parse_rings if key == "rings" else parse_coins)(blob)
                d = json.loads(json.dumps(d))
                same = (build_rings if key == "rings" else build_coins)(d) == blob
                notes = []
            ok += same
            bad += not same
            if not same or notes:
                print(f"{e['id']} {key} {path}: {'OK' if same else 'MISMATCH'} {notes}")
    print(f"{ok} files rebuilt byte-identically, {bad} mismatches ({len(seen)} distinct files)")
    return bad == 0


def main(argv):
    if not argv:
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd == "tables":
        cmd_tables()
    elif cmd == "dump":
        cmd_dump(int(argv[1]))
    elif cmd == "export":
        cmd_export(int(argv[1]), argv[2])
    elif cmd == "build":
        cmd_build(argv[1], argv[2])
    elif cmd == "test":
        return 0 if cmd_test() else 1
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
