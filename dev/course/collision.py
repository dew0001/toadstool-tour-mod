"""Mario Golf: Toadstool Tour (GFTE01) hole collision files: the type-2 module at hole-table +4.

Format notes are in collision.md next to this script. Summary:

  module header   +0/+4 ADDR32 -> the 8 zero bytes at the end; +8/+C/+10 `b` to three stubs:
                  object count (li r3,N), object records (lis/addi), hole layout (lis/addi)
  object record   0x28: mesh root, instance BVH (or 0), instance array, bbox[6], name (or 0)
  mesh            vertices (quantised, root +0x2C format), triangles (12 bytes), BVH leaf lists (u16 ... FFFF),
                  BVH nodes (12 bytes), root (0x3C, magic = build date 0x0131A2B1 / 0x0131A313 / 0x0131A3CB)
  instance        0x2C: flags (1 move, 2 scale, 4 rotate), position, scale xyz, quaternion xyzw
  hole layout     0x1AA8 bytes: tees, pins, light direction, drop zones ... (collision units, x32 = feet)

Usage:
  python -I collision.py info <file>            summary (file = disc path like A/V/R, packed file, or unpacked .bin)
  python -I collision.py roundtrip <file>...    parse + rebuild, compare module and relocations byte for byte
  python -I collision.py roundtrip-all          every collision file in the hole table
  python -I collision.py obj <file> <out.obj>   dump all meshes (instanced) as an OBJ, one group per surface code
  python -I collision.py selftest [<file>...]   rebuild a hole with the writer and compare ground/surface queries

Library:
  coll = parse(module_bytes, relocs)   relocs = [(kind, offset, value)] (kind 0 ADDR32, 1 REL24, 2 HA16, 3 LO16)
  module, relocs = build(coll)         inverse of parse; byte-identical for all 118 retail files
  load(path) -> (module, relocs);  save_packed(path, module, relocs)  (camelot_lz type 2)

Writing a new hole (coordinates in collision units = feet / 32):
  course = make_mesh(points, [(i0, i1, i2, attr(0x01)), ...])   # ground: (p1-p0) x (p2-p0) must point DOWN
  tree = make_mesh(tree_points, tree_faces)
  coll = make_collision(course, [("mur_0101_tree", tree, [instance((x, y, z), yaw_degrees=30)])],
                        make_layout(tees=[(x, y, z)], pins=[(x, y, z)] * 4))     # tees/pins in feet
  save_packed("out/A/V/R", *build(coll))
"""
import math
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("TTMOD_ROOT", os.path.normpath(os.path.join(HERE, "..", "..", "..")))   # above the repo
DEV = os.path.normpath(os.path.join(HERE, ".."))
UNPACKED = os.path.join(ROOT, "unpacked")
DISC = os.path.join(ROOT, "disc", "files")
OVERLAY = os.path.join(UNPACKED, "C", "L", "V.bin")                 # golf overlay, loaded at 0x80400000
sys.path.insert(0, DEV)

VERSION_2B1 = 0x0131A2B1   # 2003-01-17: coordinates in 1/100 of the later unit (game scales by 3200, not 32)
VERSION_313 = 0x0131A313   # 2003-02-27: BVH pointers fixed by ADDR32 relocations
VERSION_3CB = 0x0131A3CB   # 2003-04-11: BVH offsets self-relative, fixed at load; first object -> "new" query path
FEET_PER_UNIT = 32.0       # world (feet) = collision unit * 32 for versions >= 0x0131A313
LAYOUT_SIZE = 0x1AA8
ROOT_SIZE = 0x3C
RECORD_SIZE = 0x28
INSTANCE_SIZE = 0x2C
NODE_SIZE = 0x0C
COMP_SIZE = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4}          # GX u8, s8, u16, s16, f32
COMP_CODE = {0: "B", 1: "b", 2: "H", 3: "h", 4: "f"}

# Surface codes (triangle attribute & 0xFF). Taken from the golf overlay's surface table at 0x804D93C0 (65 object
# pointers -> 39 classes, vtables 0x804CB138 ... 0x804CBBE8) and the lie names (message 0x834 + lie index).
# ob: out of bounds (vtable[0]); pen: ball lost / penalty (vtable[1]); lie: lie index or "sub" when it depends on
# the ball's sub-lie (0..3); bounce: vtable[5] restitution; pct: vtable[11] (drop/placement score); sfx: vtable[14].
SURFACES = {
    0x00: ("Tee Box", "tee box (lie 0)", dict(ob=0, pen=0, bounce=0.4, pct=70, sfx=413)),
    0x01: ("Fairway", "fairway (lies 4-7)", dict(ob=0, pen=0, bounce=0.4, pct=80, sfx=413)),
    0x02: ("Green", "green (lie 26); putting surface", dict(ob=0, pen=0, bounce=0.4, pct=100, sfx=413)),
    0x03: ("Bunker", "sand bunker (lies 16-19)", dict(ob=0, pen=0, bounce=0.1, pct=30, sfx=415)),
    0x04: ("Rough", "rough (lies 10-12)", dict(ob=0, pen=0, bounce=0.2, pct=50, sfx=416)),
    0x05: ("Water", "water hazard (message 'Water Hazard')", dict(ob=0, pen=1, bounce=1.0, pct=0, sfx=552)),
    0x06: ("OB", "out of bounds ground; also what the game assumes when nothing is hit", dict(ob=1, pen=1, bounce=0.2, pct=0, sfx=416)),
    0x07: ("Cart Path", "cart path (lie 25)", dict(ob=0, pen=0, bounce=1.0, pct=10, sfx=560)),
    0x08: ("Tee Box", "tee box, second variant (lie 1)", dict(ob=0, pen=0, bounce=0.4, pct=70, sfx=413)),
    0x09: ("Rock", "rock / cliff in play (lie 23)", dict(ob=0, pen=0, bounce=1.0, pct=10, sfx=560)),
    0x0A: ("Semi-Rough", "first cut (lies 8-9)", dict(ob=0, pen=0, bounce=0.4, pct=70, sfx=413)),
    0x0B: ("Fringe", "fringe / collar (lies 2-3)", dict(ob=0, pen=0, bounce=0.4, pct=80, sfx=413)),
    0x0C: ("Tree", "tree foliage: plays as rough, message 'Tree Hazard'", dict(ob=0, pen=0, bounce=0.2, pct=50, sfx=422)),
    0x0D: ("Tree (lost)", "tree, ball lost (penalty), message 'Tree Hazard'", dict(ob=0, pen=1, bounce=0.2, pct=0, sfx=586)),
    0x0E: ("OB", "out of bounds", dict(ob=1, pen=1)),
    0x0F: ("OB", "out of bounds", dict(ob=1, pen=1)),
    0x10: ("OB", "out of bounds", dict(ob=1, pen=1)),
    0x11: ("Fast Fairway", "fast fairway (lies 27-30)", dict(ob=0, pen=0, bounce=0.4, pct=80, sfx=413)),
    0x12: ("Heath", "heath; 'Flower Patch' on course 5 (lie 15 / 42)", dict(ob=0, pen=0, bounce=0.2, pct=20, sfx=537)),
    0x13: ("Tree", "tree: plays as rough, message 'Tree Hazard'", dict(ob=0, pen=0, bounce=0.2, pct=50, sfx=422)),
    0x14: ("Water", "water hazard", dict(ob=0, pen=1, bounce=1.0, pct=0, sfx=553)),
    0x15: ("Water", "water hazard", dict(ob=0, pen=1, bounce=1.0, pct=0, sfx=553)),
    0x16: ("Heavy Rough", "heavy rough (lies 13-14)", dict(ob=0, pen=0, bounce=0.2, pct=20, sfx=537)),
    0x17: ("Waste Area", "waste area (lie 22)", dict(ob=0, pen=0, bounce=0.2, pct=30, sfx=595)),
    0x18: ("Water", "water hazard", dict(ob=0, pen=1, bounce=1.0, pct=0, sfx=553)),
    0x19: ("Water", "water hazard", dict(ob=0, pen=1, bounce=1.0, pct=0, sfx=553)),
    0x1A: ("Mushroom", "bouncy mushroom (lie 40, restitution 2.0)", dict(ob=0, pen=0, bounce=2.0, pct=10, sfx=596)),
    0x1B: ("OB", "out of bounds, dead (restitution 0)", dict(ob=1, pen=1, bounce=0.0)),
    0x1C: ("Water", "water hazard (second kind: FUN_80417ac0 returns 2)", dict(ob=0, pen=1, bounce=1.0, pct=0, sfx=553)),
    0x1D: ("Pipe", "warp pipe (lie 35)", dict(ob=0, pen=0, bounce=1.0, pct=0, sfx=532)),
    0x1E: ("OB", "out of bounds", dict(ob=1, pen=1)),
    0x1F: ("Rock (OB)", "rock that is out of bounds", dict(ob=1, pen=1, bounce=0.97, pct=10, sfx=487)),
    0x20: ("Rock (OB)", "rock that is out of bounds", dict(ob=1, pen=1, bounce=0.97, pct=10, sfx=560)),
    0x21: ("Grass Bunker", "grass bunker (lie 20)", dict(ob=0, pen=0, bounce=0.2, pct=20, sfx=537)),
    0x22: ("Waste Area", "waste area (lie 22)", dict(ob=0, pen=0, bounce=0.2, pct=30, sfx=595)),
    0x23: ("Wood", "wood: bridges, fences (lie 24)", dict(ob=0, pen=0, bounce=0.9, pct=10, sfx=531)),
    0x24: ("Beach Bunker", "beach bunker (lies 31-34)", dict(ob=0, pen=0, bounce=0.1, pct=30, sfx=422)),
    0x25: ("Rock", "rock (lie 23)", dict(ob=0, pen=0, bounce=1.0, pct=10, sfx=560)),
    0x26: ("Wood", "wood (lie 24)", dict(ob=0, pen=0, bounce=0.9, pct=10, sfx=531)),
    0x27: ("Rock", "rock (lie 23)", dict(ob=0, pen=0, bounce=1.0, pct=10, sfx=560)),
    0x28: ("Rock", "rock (lie 23)", dict(ob=0, pen=0, bounce=1.0, pct=10, sfx=560)),
    0x29: ("Thwomp", "Thwomp (lie 41)", dict(ob=0, pen=0, bounce=0.8, pct=10, sfx=560)),
    0x2A: ("Tree (lost)", "lost-ball tree (penalty, 'Tree Hazard')", dict(ob=0, pen=1, bounce=0.8, pct=0, sfx=590)),
    0x2B: ("OB", "out of bounds", dict(ob=1, pen=1)),
    0x2C: ("OB", "out of bounds (own sound 491)", dict(ob=1, pen=1)),
    0x2D: ("OB", "out of bounds", dict(ob=1, pen=1)),
    0x2E: ("Special", "not OB/penalty but the end-of-shot message shows 'OB' (sfx 540)", dict(ob=0, pen=0, bounce=0.2, pct=0, sfx=540)),
    0x2F: ("Special", "plays as rough, restitution 0.5, sfx 487", dict(ob=0, pen=0, bounce=0.5, pct=0, sfx=487)),
    0x30: ("Rock (OB)", "rock flagged OB but not penalty", dict(ob=1, pen=0, bounce=1.0, pct=0, sfx=560)),
    0x31: ("Brick", "brick (lie 43)", dict(ob=0, pen=0, bounce=1.0, pct=10, sfx=417)),
    0x32: ("Rock", "rock, sound 554", dict(ob=0, pen=0, bounce=1.0, pct=0, sfx=554)),
    0x33: ("Rock", "rock, sound 585", dict(ob=0, pen=0, bounce=1.0, pct=0, sfx=585)),
    0x34: ("Rock", "rock, sound 525", dict(ob=0, pen=0, bounce=1.0, pct=0, sfx=525)),
    0x35: ("Tree (lost)", "lost-ball (penalty), restitution 0.8, sfx 590", dict(ob=0, pen=1, bounce=0.8, pct=0, sfx=590)),
}
for _c in range(0x36, 0x41):
    SURFACES[_c] = ("OB", "out of bounds", dict(ob=1, pen=1))

# Triangle attribute word (+0xA): bits 0-7 surface code, bits 13-14 zone, bit 15 two-sided.
ATTR_TWO_SIDED = 0x8000    # set: both faces collide (except in query mode 1); clear: only rays from the front side
ATTR_OTHER_HOLE = 0x0100   # bits 8-12 go unread by the game (it takes the low byte); v12 marks another hole's fairway,
                           # fringe and green with this one, and course 8's auto-aim stub (course8.py) skips them
ZONE_SHIFT = 13            # ball +0xC8 = (attr >> 13) & 3: 0 in play, 2 out of bounds, 3 hazard (penalty drop)
ZONE_IN_PLAY, ZONE_OB, ZONE_HAZARD = 0, 2, 3


def attr(code, zone=ZONE_IN_PLAY, two_sided=False):
    """Triangle attribute word."""
    return (code & 0xFF) | (zone << ZONE_SHIFT) | (ATTR_TWO_SIDED if two_sided else 0)
INSTANCE_MOVE, INSTANCE_SCALE, INSTANCE_ROTATE = 1, 2, 4


# ---------------------------------------------------------------- normal table (golf overlay 0x804CE58C)

def normal_table():
    """The 256 unit normals the triangles' corner bytes index (golf overlay 0x804CE58C, 12 bytes each)."""
    data = open(OVERLAY, "rb").read()
    o = 0x804CE58C - 0x80400000
    return [struct.unpack_from(">3f", data, o + 12 * i) for i in range(256)]


def nearest_normal(table, n):
    """Index of the table normal closest to unit vector n (what a writer stores per corner)."""
    return max(range(len(table)), key=lambda i: table[i][0] * n[0] + table[i][1] * n[1] + table[i][2] * n[2])


# ---------------------------------------------------------------- reading helpers

def u16(b, o): return struct.unpack_from(">H", b, o)[0]
def u32(b, o): return struct.unpack_from(">I", b, o)[0]
def s32(b, o): return struct.unpack_from(">i", b, o)[0]
def f32(b, o): return struct.unpack_from(">f", b, o)[0]


def load(path):
    """(module bytes, relocs) from a disc path ('A/V/R'), a packed disc file or an unpacked .bin (+ .rel)."""
    if not os.path.exists(path) and "/" in path and len(path) == 5:
        cand = os.path.join(UNPACKED, *path.split("/")) + ".bin"
        path = cand if os.path.exists(cand) else os.path.join(DISC, *path.split("/"))
    if path.endswith(".bin"):
        module = open(path, "rb").read()
        raw = open(path[:-4] + ".rel", "rb").read()
        relocs = []
        for i in range(0, len(raw), 8):
            w, v = struct.unpack_from(">II", raw, i)
            if w >> 24 == 0xFF:
                break
            relocs.append((w >> 24, w & 0xFFFFFF, v))
        return module, relocs
    import camelot_lz as lz
    data = open(path, "rb").read()
    module, end = lz.decompress(data)
    entries, _ = lz.relocations(data, end)
    return module, [(k | (4 if ext else 0), off, val) for k, ext, off, val in entries]


def reloc_table_bytes(relocs):
    """Raw relocation entries (no terminator), as unpack_all.py writes the .rel files."""
    return b"".join(struct.pack(">II", (k << 24) | off, val) for k, off, val in relocs)


def save_packed(path, module, relocs):
    import camelot_lz as lz
    open(path, "wb").write(lz.pack(2, module, reloc_table_bytes(relocs)))


class _Reader:
    def __init__(self, module, relocs):
        self.b = module
        self.addr = {}       # offset -> target (ADDR32)
        self.other = {}      # offset -> (kind, value)
        for k, off, val in relocs:
            if k == 0:
                self.addr[off] = val
            else:
                self.other[off] = (k, val)

    def ptr(self, o):
        """Relocated pointer at o (module offset of the target) or None if the word is not relocated."""
        return self.addr.get(o)


# ---------------------------------------------------------------- parse

def _parse_bvh(r, base, relocated, list_ok):
    """BVH at `base`: nodes are 12 bytes: u32 link, u8 q[6], u16 pad.
    link: internal node -> right child (left child = the next node); leaf -> u16 list (stored before the BVH).
    Stored link word = target - base (self-relative to the BVH root), except relocated leaf links, stored 0.
    Returns dict(nodes=[...], lists=[...]) with nodes in file order and lists in file order."""
    b = r.b
    node_offs, list_offs = set(), set()
    stack = [base]
    while stack:
        o = stack.pop()
        if o in node_offs:
            continue
        node_offs.add(o)
        if relocated:
            t = r.ptr(o)
        else:
            t = base + s32(b, o)
        if t is None:
            raise ValueError("BVH node at 0x%X has no relocation" % o)
        if t < o:          # leaf: list before the node
            list_offs.add(t)
        else:
            stack.append(o + NODE_SIZE)
            stack.append(t)
    nodes_sorted = sorted(node_offs)
    first, last = nodes_sorted[0], nodes_sorted[-1]
    if first != base or (last - first) // NODE_SIZE + 1 != len(nodes_sorted):
        raise ValueError("BVH at 0x%X is not contiguous" % base)
    lists_sorted = sorted(list_offs)
    lists = []
    for lo in lists_sorted:
        items, o = [], lo
        while u16(b, o) != 0xFFFF:
            items.append(u16(b, o))
            o += 2
        lists.append(items)
    lidx = {o: i for i, o in enumerate(lists_sorted)}
    nidx = {o: i for i, o in enumerate(nodes_sorted)}
    nodes = []
    for o in nodes_sorted:
        t = r.ptr(o) if relocated else base + s32(b, o)
        q = list(b[o + 4:o + 10])
        pad = u16(b, o + 10)
        if t < o:
            node = {"leaf": lidx[t], "q": q}
            if relocated and u32(b, o) != 0:
                node["raw"] = u32(b, o)
        else:
            node = {"right": nidx[t], "q": q}
            if relocated and u32(b, o) != t - base:
                node["raw"] = u32(b, o)
        if pad:
            node["pad"] = pad
        nodes.append(node)
    return {"nodes": nodes, "lists": lists, "relocated": relocated,
            "_lists_at": lists_sorted[0] if lists_sorted else base, "_end": last + NODE_SIZE}


def _parse_mesh(r, root):
    b = r.b
    m = {
        "version": u32(b, root),
        "fmt": u32(b, root + 0x2C),
        "bbox": list(struct.unpack_from(">6f", b, root + 0x14)),
        "ntri_field": u32(b, root + 0x30),
        "nvert_field": u32(b, root + 0x34),
        "grid": u32(b, root + 0x0C),
        "fixed": u32(b, root + 0x38),
    }
    vo, to, bo = r.ptr(root + 4), r.ptr(root + 8), r.ptr(root + 0x10)
    comp = (m["fmt"] >> 8) & 7 if m["version"] else 4
    csize = COMP_SIZE[comp]
    nvert = (to - vo) // (3 * csize)
    m["vertices"] = [struct.unpack_from(">3" + COMP_CODE[comp], b, vo + 3 * csize * i) for i in range(nvert)]
    tail = b[vo + 3 * csize * nvert:to]
    if tail:
        m["vertex_tail"] = tail
    m["triangles"] = [struct.unpack_from(">3H4BH", b, to + 12 * i) for i in range(m["ntri_field"])]
    relocated = m["version"] <= VERSION_313
    m["bvh"] = _parse_bvh(r, bo, relocated, True)
    m["_at"] = vo
    m["_root"] = root
    return m


def parse(module, relocs):
    """Decoded collision module + relocation list -> plain dict (see collision.md)."""
    r = _Reader(module, relocs)
    b = module
    stub_n, stub_rec, stub_lay = r.other[8][1], r.other[0xC][1], r.other[0x10][1]
    count = u32(b, stub_n) & 0xFFFF
    rec_at = r.other[stub_rec][1]
    lay_at = r.other[stub_lay][1]
    coll = {"objects": [], "layout": b[lay_at:lay_at + LAYOUT_SIZE]}
    meshes = {}
    for i in range(count):
        o = rec_at + RECORD_SIZE * i
        root = r.ptr(o)
        name_at = r.ptr(o + 0x24)
        obj = {
            "name": b[name_at:b.index(b"\0", name_at)].decode("ascii") if name_at is not None else None,
            "bbox": list(struct.unpack_from(">6f", b, o + 0xC)),
            "mesh": None, "instances": None, "inst_bvh": None,
        }
        if root not in meshes:
            meshes[root] = _parse_mesh(r, root)
            obj["mesh"] = meshes[root]
        else:
            obj["mesh_of"] = [k for k, ob in enumerate(coll["objects"]) if ob.get("mesh") is meshes[root]][0]
        ib = r.ptr(o + 4)
        if ib is None and u32(b, o + 4):
            obj["inst_bvh_raw"] = u32(b, o + 4)
        if ib is not None:
            # record 0's single-leaf BVH is relocated; the global BVH (record 1, new format) is self-relative
            relocated = r.ptr(ib) is not None
            obj["inst_bvh"] = _parse_bvh(r, ib, relocated, True)
            obj["_ibvh_at"] = ib
        obj["_inst_at"] = r.ptr(o + 8)
        coll["objects"].append(obj)
    # instance counts are implicit: arrays are contiguous, in file order; split by the next array/structure
    starts = sorted((ob["_inst_at"], k) for k, ob in enumerate(coll["objects"]))
    bounds = sorted(set([ob["_inst_at"] for ob in coll["objects"]] +
                        [ob["inst_bvh"]["_lists_at"] for ob in coll["objects"] if ob["inst_bvh"]] +
                        [ob["_ibvh_at"] for ob in coll["objects"] if ob["inst_bvh"]] + [rec_at]))
    for at, k in starts:
        nxt = min(x for x in bounds if x > at)
        n = (nxt - at) // INSTANCE_SIZE
        insts = []
        for j in range(n):
            q = at + INSTANCE_SIZE * j
            v = struct.unpack_from(">I10f", b, q)
            insts.append({"flags": v[0], "pos": list(v[1:4]), "scale": list(v[4:7]), "quat": list(v[7:11])})
        coll["objects"][k]["instances"] = insts
    coll["_rec_at"] = rec_at
    return coll


# ---------------------------------------------------------------- build

class _Writer:
    def __init__(self):
        self.b = bytearray()
        self.relocs = []          # (kind, offset, value)

    def align(self, n):
        while len(self.b) % n:
            self.b.append(0)

    def here(self):
        return len(self.b)

    def put(self, data):
        o = len(self.b)
        self.b += data
        return o

    def addr32(self, at, target, stored=0):
        struct.pack_into(">I", self.b, at, stored & 0xFFFFFFFF)
        self.relocs.append((0, at, target))


def _put_bvh(w, bvh):
    """Write leaf lists then nodes; returns the BVH root offset. Links are fixed after both are placed."""
    list_at = []
    for items in bvh["lists"]:
        if not bvh["relocated"]:
            w.align(4)             # self-relative BVHs: every list starts on a 4-byte boundary (zero padding)
        list_at.append(w.put(struct.pack(">%dH" % (len(items) + 1), *items, 0xFFFF)))
    w.align(4)
    base = w.here()
    node_at = [base + NODE_SIZE * i for i in range(len(bvh["nodes"]))]
    w.put(bytes(NODE_SIZE * len(bvh["nodes"])))
    for i, nd in enumerate(bvh["nodes"]):
        o = node_at[i]
        target = list_at[nd["leaf"]] if "leaf" in nd else node_at[nd["right"]]
        w.b[o + 4:o + 10] = bytes(nd["q"])
        struct.pack_into(">H", w.b, o + 10, nd.get("pad", 0))
        if bvh["relocated"]:
            stored = nd.get("raw", 0 if "leaf" in nd else target - base)
            w.addr32(o, target, stored)
        else:
            struct.pack_into(">i", w.b, o, target - base)
    return base


def _put_mesh(w, m):
    comp = (m["fmt"] >> 8) & 7 if m["version"] else 4
    vo = w.here()
    for v in m["vertices"]:
        w.put(struct.pack(">3" + COMP_CODE[comp], *v))
    w.put(m.get("vertex_tail", b""))
    to = w.here()
    for t in m["triangles"]:
        w.put(struct.pack(">3H4BH", *t))
    bo = _put_bvh(w, m["bvh"])
    w.align(4)
    root = w.put(bytes(ROOT_SIZE))
    struct.pack_into(">I", w.b, root, m["version"])
    w.addr32(root + 4, vo)
    w.addr32(root + 8, to)
    struct.pack_into(">I", w.b, root + 0xC, m["grid"])
    w.addr32(root + 0x10, bo)
    struct.pack_into(">6f", w.b, root + 0x14, *m["bbox"])
    struct.pack_into(">4I", w.b, root + 0x2C, m["fmt"], m["ntri_field"], m["nvert_field"], m["fixed"])
    return root


def build(coll):
    """Plain dict -> (module bytes, relocs). Layout: header, meshes (objects 1..n-1, then 0), the global instance
    BVH, instance arrays (1..n-1, then 0), the other instance BVHs, records, hole layout, names, 8 zero bytes."""
    w = _Writer()
    objs = coll["objects"]
    n = len(objs)
    order = list(range(1, n)) + [0]
    w.put(bytes(0x40))
    # header stubs
    w.b[0x14:0x34] = bytes.fromhex("386000004E8000203C600000386300004E8000203C600000386300004E800020")
    struct.pack_into(">H", w.b, 0x16, n)
    for at, tgt in ((8, 0x14), (0xC, 0x1C), (0x10, 0x28)):
        struct.pack_into(">I", w.b, at, 0x48000000)
        w.relocs.append((1, at, tgt))
    root_at = {}
    for k in order:
        if objs[k]["mesh"] is not None:
            root_at[k] = _put_mesh(w, objs[k]["mesh"])
    for k in range(n):
        if objs[k]["mesh"] is None:
            root_at[k] = root_at[objs[k]["mesh_of"]]
    ibvh_at = {}
    late = []
    for k in order:
        ob = objs[k]
        if ob["inst_bvh"] is not None and not ob["inst_bvh"]["relocated"]:
            ibvh_at[k] = _put_bvh(w, ob["inst_bvh"])
    inst_at = {}
    for k in order:
        inst_at[k] = w.here()
        for it in objs[k]["instances"]:
            w.put(struct.pack(">I10f", it["flags"], *it["pos"], *it["scale"], *it["quat"]))
    for k in order:
        ob = objs[k]
        if ob["inst_bvh"] is not None and ob["inst_bvh"]["relocated"]:
            ibvh_at[k] = _put_bvh(w, ob["inst_bvh"])
    w.align(4)
    rec_at = w.put(bytes(RECORD_SIZE * n))
    lay_at = w.put(coll["layout"])
    name_at = {}
    for k in range(n):
        nm = objs[k]["name"]
        if nm is not None:
            name_at[k] = w.put(nm.encode("ascii") + b"\0")
            w.align(4)
    w.align(4)
    tail = w.put(bytes(8))
    for k in range(n):
        o = rec_at + RECORD_SIZE * k
        ob = objs[k]
        w.addr32(o, root_at[k])
        if k in ibvh_at:
            w.addr32(o + 4, ibvh_at[k])
        elif "inst_bvh_raw" in ob:
            struct.pack_into(">I", w.b, o + 4, ob["inst_bvh_raw"])
        w.addr32(o + 8, inst_at[k])
        struct.pack_into(">6f", w.b, o + 0xC, *ob["bbox"])
        if k in name_at:
            # the stored word is the name's offset in the name block (the relocation makes it absolute)
            w.addr32(o + 0x24, name_at[k], name_at[k] - min(name_at.values()))
    w.addr32(0, tail)
    w.addr32(4, tail + 4)
    w.relocs.append((2, 0x1C, rec_at))
    w.relocs.append((3, 0x20, rec_at))
    w.relocs.append((2, 0x28, lay_at))
    w.relocs.append((3, 0x2C, lay_at))
    w.relocs.sort(key=lambda e: e[1])
    return bytes(w.b), w.relocs


# ---------------------------------------------------------------- writing new files

def f32r(x):
    """Round to single precision (the game does all box math in float32)."""
    return struct.unpack(">f", struct.pack(">f", x))[0]


def decode_box(parent, q):
    """Child box from the parent box and a node's 6 bytes, as FUN_80437168 does (GQR5 = u8 / 256):
    min += extent * q[0..2] / 256, max -= extent * q[3..5] / 256 (fmadds / fnmsubs, one float32 rounding)."""
    ext = [f32r(parent[3 + k] - parent[k]) for k in range(3)]
    return ([f32r(parent[k] + ext[k] * (q[k] / 256.0)) for k in range(3)] +
            [f32r(parent[3 + k] - ext[k] * (q[3 + k] / 256.0)) for k in range(3)])


def quantize_box(parent, child):
    """Largest q (conservative) whose decoded box still contains `child`. Returns (q, decoded box)."""
    q = [0] * 6
    ext = [f32r(parent[3 + k] - parent[k]) for k in range(3)]
    for k in range(3):
        if ext[k] > 0:
            q[k] = max(0, min(255, int(math.floor((child[k] - parent[k]) / ext[k] * 256.0))))
            q[3 + k] = max(0, min(255, int(math.floor((parent[3 + k] - child[3 + k]) / ext[k] * 256.0))))
    while True:
        box = decode_box(parent, q)
        bad = False
        for k in range(3):
            if box[k] > child[k] and q[k] > 0:
                q[k] -= 1
                bad = True
            if box[3 + k] < child[3 + k] and q[3 + k] > 0:
                q[3 + k] -= 1
                bad = True
        if not bad:
            return q, box


def build_bvh(item_boxes, root_box, leaf_size=12, relocated=False, items=None):
    """Object-partition BVH in the game's layout: nodes in depth-first order (left child = next node), one u16 list
    per leaf, lists in leaf order. item_boxes[i] = [minx,miny,minz,maxx,maxy,maxz]; items[i] = the u16 stored for
    item i (triangle index, or obj << 8 | instance). Every node box contains its items entirely, which is what the
    traversal needs (the original tool also listed triangles in several leaves, kd-tree style; both work)."""
    if items is None:
        items = list(range(len(item_boxes)))
    nodes, lists = [], []
    cent = [[(b[k] + b[3 + k]) * 0.5 for k in range(3)] for b in item_boxes]

    def bounds(ids):
        return ([min(item_boxes[i][k] for i in ids) for k in range(3)] +
                [max(item_boxes[i][3 + k] for i in ids) for k in range(3)])

    def rec(ids, parent):
        q, box = quantize_box(parent, bounds(ids))
        me = len(nodes)
        nodes.append(None)
        if len(ids) <= leaf_size:
            lists.append(sorted(items[i] for i in ids))
            nodes[me] = {"leaf": len(lists) - 1, "q": q}
            return me
        lo = [min(cent[i][k] for i in ids) for k in range(3)]
        hi = [max(cent[i][k] for i in ids) for k in range(3)]
        axis = max(range(3), key=lambda k: hi[k] - lo[k])
        ids = sorted(ids, key=lambda i: cent[i][axis])
        half = len(ids) // 2
        rec(ids[:half], box)
        right = rec(ids[half:], box)
        nodes[me] = {"right": right, "q": q}
        return me

    if item_boxes:
        rec(list(range(len(item_boxes))), root_box)
    else:
        lists.append([])
        nodes.append({"leaf": 0, "q": [0] * 6})
    return {"nodes": nodes, "lists": lists, "relocated": relocated}


def vertex_format(points, comp=3):
    """(fmt word, scale) for s16 vertices: as many fraction bits as the largest coordinate allows."""
    biggest = max([abs(c) for p in points for c in p] + [1e-6])
    frac = 0
    while frac < 31 and biggest * (1 << (frac + 1)) <= 32767:
        frac += 1
    return (comp << 8) | frac, float(1 << frac)


def make_mesh(points, faces, normals=None, leaf_size=12, margin=0.01):
    """New mesh (version 0x0131A3CB) from float vertices in collision units (feet / 32) and faces
    [(i0, i1, i2, attr)]; front face = the side normalize((p2 - p1) x (p1 - p0)) points to, so for ground
    (p1 - p0) x (p2 - p0) must point down (clockwise on a map with x right, z down). attr = attr(code, zone,
    two_sided). normals: optional per-vertex unit normals for the corner bytes (default: face normal)."""
    fmt, scale = vertex_format(points)
    verts = [tuple(int(round(c * scale)) for c in p) for p in points]
    q = [[c / scale for c in v] for v in verts]
    table = normal_table()
    tris, boxes = [], []
    for f in faces:
        a, b, c, attr = f
        p0, p1, p2 = q[a], q[b], q[c]
        e1 = [p2[k] - p1[k] for k in range(3)]
        e0 = [p1[k] - p0[k] for k in range(3)]
        n = [e1[1] * e0[2] - e1[2] * e0[1], e1[2] * e0[0] - e1[0] * e0[2], e1[0] * e0[1] - e1[1] * e0[0]]
        ln = math.sqrt(sum(x * x for x in n)) or 1.0
        n = [x / ln for x in n]
        if normals is not None:
            idx = [nearest_normal(table, normals[i]) for i in (a, b, c)]
        else:
            idx = [nearest_normal(table, n)] * 3
        tris.append((a, b, c, idx[0], idx[1], idx[2], 0, attr))
        boxes.append([min(p0[k], p1[k], p2[k]) for k in range(3)] + [max(p0[k], p1[k], p2[k]) for k in range(3)])
    lo = [min(v[k] for v in q) for k in range(3)]
    hi = [max(v[k] for v in q) for k in range(3)]
    bbox = [f32r(lo[k] - margin) for k in range(3)] + [f32r(hi[k] + margin) for k in range(3)]
    return {"version": VERSION_3CB, "fmt": fmt, "bbox": bbox, "ntri_field": len(tris), "nvert_field": len(verts),
            "grid": 0, "fixed": 0, "vertices": verts, "triangles": tris,
            "bvh": build_bvh(boxes, bbox, leaf_size)}


def mesh_scale(m):
    """Vertex value -> collision units. Meshes older than 0x0131A313 are in hundredths of a foot (the game scales
    the ray by 3200 = 32 x 100 for them and multiplies their instance translations by 3200)."""
    s = 1.0 / (1 << (m["fmt"] & 0x3F))
    return s / 3200.0 if m["version"] < VERSION_313 else s


def _instance_box(mesh_bbox, it, unit_scale=1.0):
    xs = []
    for cx in (0, 3):
        for cy in (1, 4):
            for cz in (2, 5):
                x, y, z = mesh_bbox[cx] * unit_scale, mesh_bbox[cy] * unit_scale, mesh_bbox[cz] * unit_scale
                if it["flags"] & INSTANCE_SCALE:
                    s = it["scale"][0]
                    x, y, z = x * s, y * s, z * s
                if it["flags"] & INSTANCE_ROTATE:
                    qx, qy, qz, qw = it["quat"]
                    x, y, z = (
                        (1 - 2 * (qy * qy + qz * qz)) * x + 2 * (qx * qy - qz * qw) * y + 2 * (qx * qz + qy * qw) * z,
                        2 * (qx * qy + qz * qw) * x + (1 - 2 * (qx * qx + qz * qz)) * y + 2 * (qy * qz - qx * qw) * z,
                        2 * (qx * qz - qy * qw) * x + 2 * (qy * qz + qx * qw) * y + (1 - 2 * (qx * qx + qy * qy)) * z)
                if it["flags"] & INSTANCE_MOVE:
                    x, y, z = x + it["pos"][0], y + it["pos"][1], z + it["pos"][2]
                xs.append((x, y, z))
    return [min(p[k] for p in xs) for k in range(3)] + [max(p[k] for p in xs) for k in range(3)]


def instance(pos=(0, 0, 0), scale=1.0, yaw_degrees=None, quat=None):
    """Instance record; pos in collision units. Flags: 1 move, 2 scale, 4 rotate (game: scale, rotate, move)."""
    flags = 0
    if any(pos):
        flags |= INSTANCE_MOVE
    if scale != 1.0:
        flags |= INSTANCE_SCALE
    if yaw_degrees is not None:
        h = math.radians(yaw_degrees) / 2
        quat = (0.0, math.sin(h), 0.0, math.cos(h))
    if quat is not None:
        flags |= INSTANCE_ROTATE
    return {"flags": flags, "pos": [float(c) for c in pos], "scale": [float(scale)] * 3,
            "quat": list(quat) if quat is not None else [0.0, 0.0, 0.0, 1.0]}


def make_layout(tees, pins, light=(-0.7071, -0.5934, -0.3851), base=None):
    """Hole layout block (0x1AA8 bytes): tees (up to 3) at +0x000, pins (up to 4) at +0x024, light direction at
    +0x474; positions in feet (converted to collision units). `base` = an existing layout to start from."""
    lay = bytearray(base if base is not None else bytes(LAYOUT_SIZE))
    for i, p in enumerate(tees[:3]):
        struct.pack_into(">3f", lay, 12 * i, *[c / FEET_PER_UNIT for c in p])
    for i, p in enumerate(pins[:4]):
        struct.pack_into(">3f", lay, 0x24 + 12 * i, *[c / FEET_PER_UNIT for c in p])
    struct.pack_into(">3f", lay, 0x474, *light)
    return bytes(lay)


def make_collision(course_mesh, props=(), layout=None):
    """New collision file contents. course_mesh: make_mesh() result (object 0, "course", identity instance).
    props: [(name, mesh, [instance(...), ...])] for trees, tee markers ... (objects 1..n-1; at most 255,
    at most 256 instances each). Builds the record-0 one-leaf BVH and the record-1 global instance BVH the
    0x0131A3CB query path (FUN_804382d4) walks."""
    objs = [{"name": "course", "mesh": course_mesh, "bbox": list(course_mesh["bbox"]),
             "instances": [instance()],
             "inst_bvh": {"nodes": [{"leaf": 0, "q": [0] * 6}], "lists": [[0x0000]], "relocated": True}}]
    entries, boxes = [], []
    for k, (name, mesh, insts) in enumerate(props, start=1):
        objs.append({"name": name, "mesh": mesh, "bbox": [0.0] * 6, "instances": list(insts), "inst_bvh": None})
        for j, it in enumerate(insts):
            entries.append((k << 8) | j)
            boxes.append(_instance_box(mesh["bbox"], it, 1.0 / 3200 if mesh["version"] < VERSION_313 else 1.0))
    if len(objs) > 1:
        lo = [min(b[k] for b in boxes) for k in range(3)] if boxes else [0.0] * 3
        hi = [max(b[3 + k] for b in boxes) for k in range(3)] if boxes else [0.0] * 3
        bb = [f32r(lo[k] - 0.01) for k in range(3)] + [f32r(hi[k] + 0.01) for k in range(3)]
        objs[1]["bbox"] = bb
        objs[1]["inst_bvh"] = build_bvh(boxes, bb, leaf_size=4, items=entries)
    return {"objects": objs, "layout": layout if layout is not None else make_layout([], [])}


# ---------------------------------------------------------------- reference queries (for checking files offline)

def _seg_box(o, d, box):
    """Does the segment o + t d, t in [0, 1], touch the box (slab test)?"""
    t0, t1 = 0.0, 1.0
    for k in range(3):
        if abs(d[k]) < 1e-12:
            if o[k] < box[k] or o[k] > box[3 + k]:
                return False
        else:
            a, b = (box[k] - o[k]) / d[k], (box[3 + k] - o[k]) / d[k]
            if a > b:
                a, b = b, a
            t0, t1 = max(t0, a), min(t1, b)
            if t0 > t1:
                return False
    return True


def bvh_candidates(bvh, root_box, o, d):
    """Items the game's traversal (FUN_804372c0) would test for segment o + t d: box tests with each node's
    q applied to its parent's box; a leaf adds its whole list."""
    out = set()
    stack = [(0, decode_box(root_box, bvh["nodes"][0]["q"]))]
    while stack:
        i, box = stack.pop()
        if not _seg_box(o, d, box):
            continue
        nd = bvh["nodes"][i]
        if "leaf" in nd:
            out.update(bvh["lists"][nd["leaf"]])
            continue
        r = nd["right"]
        stack.append((r, decode_box(box, bvh["nodes"][r]["q"])))
        stack.append((i + 1, decode_box(box, bvh["nodes"][i + 1]["q"])))
    return out


def mesh_points(m):
    scale = mesh_scale(m)
    return [[c * scale for c in v] for v in m["vertices"]]


def seg_triangle(o, d, p0, p1, p2, two_sided):
    """t of the segment hit on the triangle's front face (or either face), or None. Thin segment."""
    e1 = [p2[k] - p1[k] for k in range(3)]
    e0 = [p1[k] - p0[k] for k in range(3)]
    n = [e1[1] * e0[2] - e1[2] * e0[1], e1[2] * e0[0] - e1[0] * e0[2], e1[0] * e0[1] - e1[1] * e0[0]]
    denom = sum(n[k] * d[k] for k in range(3))
    if abs(denom) < 1e-15 or (denom > 0 and not two_sided):
        return None
    t = sum(n[k] * (p0[k] - o[k]) for k in range(3)) / denom
    if t < 0 or t > 1:
        return None
    x = [o[k] + d[k] * t for k in range(3)]
    s = 1.0 if denom < 0 else -1.0
    for a, b in ((p0, p1), (p1, p2), (p2, p0)):
        ab = [b[k] - a[k] for k in range(3)]
        ax = [x[k] - a[k] for k in range(3)]
        c = [ab[1] * ax[2] - ab[2] * ax[1], ab[2] * ax[0] - ab[0] * ax[2], ab[0] * ax[1] - ab[1] * ax[0]]
        if s * sum(c[k] * n[k] for k in range(3)) > 1e-12:
            return None
    return t


def ground(m, x, z, top=200.0, bottom=-200.0, use_bvh=True):
    """Highest front-facing hit straight down at (x, z) on one mesh (collision units): (y, attr) or None."""
    o = (x, top, z)
    d = (0.0, bottom - top, 0.0)
    pts = mesh_points(m)
    cand = bvh_candidates(m["bvh"], m["bbox"], o, d) if use_bvh else range(len(m["triangles"]))
    best = None
    for i in cand:
        t = m["triangles"][i]
        h = seg_triangle(o, d, pts[t[0]], pts[t[1]], pts[t[2]], bool(t[7] & 0x8000))
        if h is not None and (best is None or h < best[0]):
            best = (h, t[7])
    return None if best is None else (top + (bottom - top) * best[0], best[1])


def _differs(a, b, tol):
    if a is None or b is None:
        return int((a is None) != (b is None))
    return int(abs(a[0] - b[0]) > tol or a[1] != b[1])


def selftest(path="A/V/R", samples=400, seed=1):
    """Rebuild a hole's course mesh with build_bvh / make_mesh / make_collision, write + re-read it, and compare
    ground height and surface at random points: original BVH vs brute force vs the new file."""
    import random
    module, relocs = load(path)
    c = parse(module, relocs)
    m0 = c["objects"][0]["mesh"]
    pts = mesh_points(m0)
    faces = [(t[0], t[1], t[2], t[7]) for t in m0["triangles"]]
    new = make_mesh(pts, faces)
    props = [(ob["name"], ob["mesh"], ob["instances"]) for ob in c["objects"][1:] if ob["mesh"] is not None]
    coll = make_collision(new, props, c["layout"])
    mod2, rel2 = build(coll)
    c2 = parse(mod2, rel2)
    again = build(c2)
    assert again == (mod2, rel2), "new file does not round-trip"
    m2 = c2["objects"][0]["mesh"]
    if len(c2["objects"]) > 1:      # every instance must be reachable through the global instance BVH
        g = c2["objects"][1]
        for k, ob in enumerate(c2["objects"][1:], start=1):
            for j, it in enumerate(ob["instances"]):
                b = _instance_box(ob["mesh"]["bbox"], it, 1.0 / 3200 if ob["mesh"]["version"] < VERSION_313 else 1.0)
                cx, cz = (b[0] + b[3]) / 2, (b[2] + b[5]) / 2
                got = bvh_candidates(g["inst_bvh"], g["bbox"], (cx, b[4] + 1, cz), (0.0, b[1] - b[4] - 2, 0.0))
                assert (k << 8) | j in got, "instance %d/%d missing from the instance BVH" % (k, j)
    rnd = random.Random(seed)
    bb = m0["bbox"]
    stats = {"bvh_vs_brute": 0, "new_vs_orig": 0, "hits": 0}
    for _ in range(samples):
        x = rnd.uniform(bb[0], bb[3])
        z = rnd.uniform(bb[2], bb[5])
        a = ground(m0, x, z)
        b = ground(m0, x, z, use_bvh=False)
        n = ground(m2, x, z)
        stats["hits"] += a is not None
        stats["bvh_vs_brute"] += _differs(a, b, 1e-4)
        stats["new_vs_orig"] += _differs(a, n, 1e-2)
    print("%s: %d samples, %d hits; original BVH vs brute force mismatches %d; new file vs original %d; "
          "new module 0x%X bytes, %d relocations (original 0x%X, %d)" % (
              path, samples, stats["hits"], stats["bvh_vs_brute"], stats["new_vs_orig"], len(mod2), len(rel2),
              len(module), len(relocs)))
    return stats["bvh_vs_brute"] == 0 and stats["new_vs_orig"] == 0


# ---------------------------------------------------------------- tools

def hole_files():
    """Unique collision files (hole table +4) in table order: [(hole id, internal name, path)]."""
    data = open(OVERLAY, "rb").read()
    out, seen = [], set()
    for i in range(145):
        e = struct.unpack_from(">8I", data, 0xDD138 + 0x20 * i)
        k = e[1] >> 1
        path = "%s/%s/%s" % (chr(65 + k // 676), chr(65 + (k // 26) % 26), chr(65 + k % 26))
        name = data[e[7] - 0x80400000:e[7] - 0x80400000 + 8].split(b"\0")[0].decode()
        if path not in seen:
            seen.add(path)
            out.append((e[6], name, path))
    return out


def roundtrip(path, verbose=True):
    module, relocs = load(path)
    coll = parse(module, relocs)
    m2, r2 = build(coll)
    ok_m = m2 == module
    ok_r = r2 == relocs
    if verbose:
        msg = "OK" if ok_m and ok_r else "MISMATCH"
        detail = ""
        if not ok_m:
            n = min(len(m2), len(module))
            first = next((i for i in range(n) if m2[i] != module[i]), n)
            detail += " module differs at 0x%X (sizes 0x%X/0x%X)" % (first, len(m2), len(module))
        if not ok_r:
            first = next((i for i in range(min(len(r2), len(relocs))) if r2[i] != relocs[i]), None)
            detail += " relocs differ at #%s (%d/%d)" % (first, len(r2), len(relocs))
        print("%-6s %s%s" % (path, msg, detail))
    return ok_m and ok_r


def world_triangles(coll, unit=FEET_PER_UNIT):
    """Yield (object index, instance index, [(x,y,z)]*3 in feet, attr, corner normal indices) for every
    triangle of every instance (instance transform applied: scale, then quaternion, then translation)."""
    for k, ob in enumerate(coll["objects"]):
        m = ob["mesh"] if ob["mesh"] is not None else coll["objects"][ob["mesh_of"]]["mesh"]
        if m["version"] == 0:
            continue
        scale = mesh_scale(m)
        verts = [[c * scale for c in v] for v in m["vertices"]]
        for j, it in enumerate(ob["instances"]):
            def xf(p):
                x, y, z = p
                if it["flags"] & INSTANCE_SCALE:
                    s = it["scale"][0]
                    x, y, z = x * s, y * s, z * s
                if it["flags"] & INSTANCE_ROTATE:
                    qx, qy, qz, qw = it["quat"]
                    x, y, z = (
                        (1 - 2 * (qy * qy + qz * qz)) * x + 2 * (qx * qy - qz * qw) * y + 2 * (qx * qz + qy * qw) * z,
                        2 * (qx * qy + qz * qw) * x + (1 - 2 * (qx * qx + qz * qz)) * y + 2 * (qy * qz - qx * qw) * z,
                        2 * (qx * qz - qy * qw) * x + 2 * (qy * qz + qx * qw) * y + (1 - 2 * (qx * qx + qy * qy)) * z)
                if it["flags"] & INSTANCE_MOVE:
                    x, y, z = x + it["pos"][0], y + it["pos"][1], z + it["pos"][2]
                return (x * unit, y * unit, z * unit)
            for t in m["triangles"]:
                yield k, j, [xf(verts[t[0]]), xf(verts[t[1]]), xf(verts[t[2]])], t[7], t[3:6]


def info(path):
    module, relocs = load(path)
    c = parse(module, relocs)
    print("%s: %d bytes, %d relocations, %d objects" % (path, len(module), len(relocs), len(c["objects"])))
    for k, ob in enumerate(c["objects"]):
        m = ob["mesh"] or c["objects"][ob["mesh_of"]]["mesh"]
        codes = {}
        for t in m["triangles"]:
            codes[t[7] & 0xFF] = codes.get(t[7] & 0xFF, 0) + 1
        print("  [%d] %-16s v%08X fmt %03X  %5d verts %5d tris %4d nodes %4d lists  %3d inst  bvh %s" % (
            k, ob["name"], m["version"], m["fmt"], len(m["vertices"]), len(m["triangles"]),
            len(m["bvh"]["nodes"]), len(m["bvh"]["lists"]), len(ob["instances"]),
            "-" if ob["inst_bvh"] is None else "%d nodes" % len(ob["inst_bvh"]["nodes"])))
        print("       surfaces: " + ", ".join("%02X %s x%d" % (s, SURFACES.get(s, ("?",))[0], n)
                                               for s, n in sorted(codes.items())))
    lay = c["layout"]
    print("  tees:", [tuple(round(x * FEET_PER_UNIT, 1) for x in struct.unpack_from(">3f", lay, 12 * i))
                      for i in range(3)])
    print("  pins:", [tuple(round(x * FEET_PER_UNIT, 1) for x in struct.unpack_from(">3f", lay, 0x24 + 12 * i))
                      for i in range(4)])
    print("  light direction:", [round(x, 3) for x in struct.unpack_from(">3f", lay, 0x474)])


def dump_obj(path, out):
    module, relocs = load(path)
    c = parse(module, relocs)
    groups = {}
    for k, j, tri, attr, nrm in world_triangles(c):
        groups.setdefault(attr & 0xFF, []).append(tri)
    with open(out, "w") as f:
        n = 0
        for code, tris in sorted(groups.items()):
            f.write("g s%02X_%s\n" % (code, SURFACES.get(code, ("unknown",))[0].replace(" ", "_")))
            for t in tris:
                for p in t:
                    f.write("v %.4f %.4f %.4f\n" % p)
                # game front face = clockwise seen from the normal side; OBJ wants counter-clockwise
                f.write("f %d %d %d\n" % (n + 1, n + 3, n + 2))
                n += 3


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "roundtrip-all"
    if cmd == "info":
        for p in sys.argv[2:]:
            info(p)
    elif cmd == "roundtrip":
        bad = sum(not roundtrip(p) for p in sys.argv[2:])
        sys.exit(1 if bad else 0)
    elif cmd == "roundtrip-all":
        files = [f for f in hole_files() if f[2] != "B/R/P"]   # TEST1 (ID 1001): pre-release version-0 format
        bad = [p for _, _, p in files if not roundtrip(p)]
        print("%d of %d files rebuilt byte-identically (B/R/P, the unused TEST1 hole, is skipped: version 0 has "
              "0x20-byte float BVH nodes)" % (len(files) - len(bad), len(files)))
        sys.exit(1 if bad else 0)
    elif cmd == "obj":
        dump_obj(sys.argv[2], sys.argv[3])
    elif cmd == "selftest":
        ok = all([selftest(p) for p in (sys.argv[2:] or ["A/V/R"])])
        sys.exit(0 if ok else 1)
    else:
        print(__doc__)
