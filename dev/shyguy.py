"""Shy Guy as a 17th golfer.

Toadstool Tour has room for 8 golfers beyond its 16: the Game Boy Advance link golfers 16-23. The save data keeps 4
link records (0x80234040 + 0x284 * slot, two golfers each: golfer 16 + 2 * slot + body), and the character select
screen lists them on an extra page (Down from the grid's bottom row), each with its own files. Golfer 16 becomes
Shy Guy, built like Koopa Troopa so he keeps his own short-legged shape:

  - build_mod.py hooks the select screen (cave 9) to write a link record for him into slot 0 each time it opens
    (`RECORD`: his name, Koopa's drive and stats, Koopa's voice) and to hide that record's second golfer, and gives
    golfer 16 Koopa's golfer methods (the vtable in the golf overlay) apart from the three that name his files,
  - his files become Koopa's (`SOURCES`: C/W/B golfer <- C/V/S, C/W/E <- C/V/Z, bank C/W/A <- C/V/R, select-screen
    model B/V/K <- B/V/D) rebuilt around an OBJ mesh: every body mesh (part 1 at mesh +0x38) gets an empty display
    list, one body mesh draws the OBJ as rigid groups (model-space positions, one bone per vertex: robe, hood and mask
    on the pelvis, arms on the arm bones, legs and shoes on the leg bones, at most 10 bones per group), and the
    rigid arrays move to the end of the module (the clubs keep their indices),
  - the OBJ's texture (256x256 CMPR, 9 levels) replaces body texture 0 in his copies (the bank, and inside B/V/K),
  - his pictures are renders of the OBJ: the extra page's faces (B/U/P texture 1, B/U/M texture 39), the in-round face
    C/W/D and the emblem C/W/C.

The model layout is in model.py and RE-NOTES.md (Characters). build_mod.py --shyguy <folder> calls `build`, with a
folder holding the OBJ and its albedo texture (Sketchfab "Shy Guy" by Jakob Henerey, CC BY).
"""
import os
import struct
from collections import defaultdict

import numpy as np
from PIL import Image, ImageDraw

import camelot_lz as lz
import model as mdl
import textures as tx

OBJ, ALBEDO = "Shy Guy.obj", "heyho_body_alb.png"
# golfer 16's files <- the Koopa Troopa files they're built from (make_patch.py copies from these too)
SOURCES = {"C/W/B": "C/V/S", "C/W/E": "C/V/Z", "B/V/K": "B/V/D", "C/W/A": "C/V/R"}
GOLFER_MODEL, BANK = "C/W/B", "C/W/A"   # the golfer model whose bones the rig uses, and the bank its texture is in
FACE = "C/W/D"                          # the face beside the score in a round (64x64 RGB5A3)
PLATES = "C/W/C"                        # emblem (texture 0); the game writes the name on the plate (texture 1)
ROW, ROW_TEX = "B/U/P", 1               # extra page: 8 faces 58x58 on white in one 464x58 CMPR picture; his is 1st
FACES, FACES_TEX = "B/U/M", 39          # extra page: 8 faces 64x64 in a 512x64 CMPR row (the 1P badge); his is 1st
PORTRAIT = (20, -8, (0, 7.4, 0), 3.4)   # face pictures: turn, tilt, centre and half-size of the view (OBJ units)

# The link record the select screen hook writes (offset in the record -> word). Two golfers of 0x2C: +0x1A drive
# (yards), +0x1C body (0 = golfer 16), +0x1F..+0x24 the six stats (the order of the golf overlay's table at
# 0x804D2980: these are Koopa's), +0x28 voice (Koopa = 15); +0x268 the name (non-empty = the record is there).
NAME = b"Shy Guy\x00"
RECORD = {0x00: NAME[:4], 0x04: NAME[4:], 0x10: NAME[:4], 0x14: NAME[4:],
          0x18: bytes([0, 0, 0, 200]), 0x1C: bytes([0, 0, 0, 1]), 0x20: bytes([0, 1, 4, 4]),
          0x24: bytes([0xFE, 0, 0, 0]), 0x28: bytes([15, 0, 0, 0]),
          0x2C + 0x1C: bytes([1, 0, 0, 0]),                  # second golfer: body 1 (hidden by the hook)
          0x268: NAME[:4], 0x26C: NAME[4:]}

# Koopa's skeleton (C/V/S numbers; C/V/Z and B/V/D use the bone with the same parent nearest its bind position)
PELVIS = 17                                           # carries the shell; the arms hang off it too (43/101)
LEG = {-1: (19, 20, 21, 22), 1: (26, 27, 28, 29)}     # hip, knee, ankle, ball of the foot (by side of x)
ARM = {-1: (45, 46, 47, 48), 1: (103, 104, 105, 106)}  # upper arm, forearm, wrist, middle of the hand
BODY_PART = 1         # mesh +0x38 of body meshes (the clubs' parts are 3..11)
GROUP_BONES = 10      # matrix palette of a group
DL_TAIL = bytes.fromhex("081000000001" * 3)   # the game's display lists end with these

# Shy Guy's shape, in OBJ units (the same as Koopa's model units: Shy Guy is 10.3 tall, Koopa 11.9)
ARM_ROOT = 3.0        # |x| where the arms leave the robe
ARM_Y = (3.9, 5.8)    # height band of the arms (T-pose)
HAND_X = 4.6          # |x| beyond which it's the mitten
ARM_RAMP = 0.6        # the arms move onto Koopa's arm line over this much |x| past ARM_ROOT
UPPER, FORE = 3.3, 3.9   # |x| on Koopa's arm line where upper arm -> forearm -> wrist
# Koopa's swings bring his hands to about 2 units in front of his hips, which is inside Shy Guy's round robe, so
# everything but the shoes is made a little smaller and set back over the feet to let the mittens show.
BODY_SCALE = 0.9
BODY_BACK = 1.2


def u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


class Module:
    """A decoded type-2 module that can grow: blob, raw relocation entries, root."""

    def __init__(self, raw):
        blob, end = lz.decompress(raw)
        self.kind = raw[0]
        self.blob = bytearray(blob)
        self.relocs = []
        off = (end + 7) & ~7
        while True:
            word, value = struct.unpack_from(">II", raw, off)
            off += 8
            if word >> 24 == 0xFF:
                break
            self.relocs.append([word, value])
        self.root = mdl.root_offset(self.blob, lz.relocations(raw, end)[0])

    def _entry(self, off):
        for e in self.relocs:
            if e[0] == off:   # kind 0 (ADDR32), module-relative
                return e
        return None

    def ptr(self, off):
        e = self._entry(off)
        return None if e is None else e[1]

    def set_ptr(self, off, target):
        e = self._entry(off)
        if e is None:
            self.relocs.append([off, target])
        else:
            e[1] = target
        struct.pack_into(">I", self.blob, off, 0)

    def u32(self, off):
        return u32(self.blob, off)

    def put32(self, off, value):
        struct.pack_into(">I", self.blob, off, value)

    def alloc(self, data, align=4):
        self.blob += bytes((-len(self.blob)) % align)
        at = len(self.blob)
        self.blob += data
        return at

    def pack(self):
        self.blob += bytes((-len(self.blob)) % 8)
        table = b"".join(struct.pack(">II", w, v) for w, v in self.relocs)
        return lz.pack(self.kind, bytes(self.blob), table)


# ---------------------------------------------------------------- OBJ and rigging

def load_obj(path):
    """(positions, texcoords, normals, triangles of (v, vt, vn) corners)."""
    v, vt, vn, tris = [], [], [], []
    with open(path) as f:
        for line in f:
            p = line.split()
            if not p:
                continue
            if p[0] == "v":
                v.append([float(x) for x in p[1:4]])
            elif p[0] == "vt":
                vt.append([float(x) for x in p[1:3]])
            elif p[0] == "vn":
                vn.append([float(x) for x in p[1:4]])
            elif p[0] == "f":
                corners = [tuple(int(i) - 1 for i in q.split("/")) for q in p[1:]]
                for k in range(1, len(corners) - 1):
                    tris.append((corners[0], corners[k], corners[k + 1]))
    return np.array(v), np.array(vt), np.array(vn), tris


def components(nverts, tris):
    """Connected-component id of every position."""
    parent = list(range(nverts))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for tri in tris:
        for c in tri[1:]:
            parent[find(c[0])] = find(tri[0][0])
    return np.array([find(i) for i in range(nverts)])


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def rig(pos, tris, joints):
    """Fit Shy Guy to Koopa's skeleton: (new positions, C/V/S bone of every position).

    joints: C/V/S bone -> bind-pose position. The robe (with hood and arms), mask and buckle are one rigid body on
    the pelvis except the arms, which move onto Koopa's arm line (so the mittens sit on his hands) and ride the arm
    bones; the dark legs under the robe ride the hips and knees, the shoes the ankles and balls of the feet."""
    pos = pos.copy()
    bone = np.full(len(pos), PELVIS)
    comp = components(len(pos), tris)
    sizes = {c: int((comp == c).sum()) for c in set(comp)}
    robe = max(sizes, key=sizes.get)
    shoe = np.zeros(len(pos), bool)
    for c in sizes:
        idx = np.nonzero(comp == c)[0]
        p = pos[idx]
        lo, hi = p.min(0), p.max(0)
        side = 1 if p[:, 0].mean() > 0 else -1
        hip, knee, ankle, ball = LEG[side]
        if hi[1] < joints[knee][1] and abs(p[:, 0].mean()) > 0.3:           # shoe or sole
            bone[idx] = np.where(p[:, 2] > joints[ball][2], ball, ankle)
            shoe[idx] = True
        elif c != robe and hi[2] < 0 and lo[1] > 1.0 and hi[1] < 4.0:       # leg under the robe
            bone[idx] = np.where(p[:, 1] > joints[knee][1], hip, knee)
    pos[~shoe] *= BODY_SCALE
    pos[~shoe, 2] -= BODY_BACK
    arm_root, arm_y, hand_x = ARM_ROOT * BODY_SCALE, [y * BODY_SCALE for y in ARM_Y], HAND_X * BODY_SCALE
    for side in (-1, 1):
        upper, fore, wrist, middle = ARM[side]
        arm = (comp == robe) & (side * pos[:, 0] > arm_root) & (pos[:, 1] > arm_y[0]) & (pos[:, 1] < arm_y[1])
        mitten = arm & (side * pos[:, 0] > hand_x)
        shift = np.array(joints[middle]) - pos[mitten].mean(0)
        w = smoothstep((side * pos[arm, 0] - arm_root) / ARM_RAMP)
        pos[arm] += w[:, None] * shift
        ax = side * pos[arm, 0]
        bone[arm] = np.where(ax < UPPER, upper, np.where(ax < FORE, fore, wrist))
    return pos, bone


# ---------------------------------------------------------------- display lists

def strips(tris):
    """Greedy triangle strips over corners. tris: [(a, b, c)] in drawing order. Returns (strips, leftovers)."""
    edges = defaultdict(list)
    for t, (a, b, c) in enumerate(tris):
        for e in ((a, b), (b, c), (c, a)):
            edges[frozenset(e)].append(t)
    used = [False] * len(tris)

    def cycles(t):
        a, b, c = tris[t]
        return ((a, b, c), (b, c, a), (c, a, b))

    def grow(seq, taken):
        while True:
            p, q = seq[-2], seq[-1]
            want_odd = (len(seq) - 2) % 2 == 1
            for t in edges[frozenset((p, q))]:
                if used[t] or t in taken:
                    continue
                r = [x for x in tris[t] if x != p and x != q]
                if len(r) != 1:
                    continue
                want = (q, p, r[0]) if want_odd else (p, q, r[0])
                if want in cycles(t):
                    taken.add(t)
                    seq.append(r[0])
                    break
            else:
                return seq, taken

    out, single = [], []
    for t in range(len(tris)):
        if used[t]:
            continue
        best = None
        for start in cycles(t):
            seq, taken = grow(list(start), {t})
            if best is None or len(seq) > len(best[0]):
                best = (seq, taken)
        for k in best[1]:
            used[k] = True
        if len(best[0]) == 3:
            single.append(tuple(best[0]))
        else:
            out.append(best[0])
    return out, single


def display_list(tris, vertex):
    """GX display list (triangle strips, then the leftovers as triangles), padded to 32 bytes."""
    seqs, single = strips(tris)
    dl = bytearray()
    for seq in seqs:
        dl += struct.pack(">BH", 0x98, len(seq)) + b"".join(vertex(c) for c in seq)
    if single:
        dl += struct.pack(">BH", 0x90, 3 * len(single)) + b"".join(vertex(c) for t in single for c in t)
    dl += DL_TAIL
    dl += bytes((-len(dl)) % 32)
    return bytes(dl)


FORMAT = {1: ("b", -128, 127), 2: ("H", 0, 0xFFFF), 3: ("h", -0x8000, 0x7FFF)}   # GX S8, U16, S16


def pack_array(values, comp_frac, what):
    """Quantize and pack an array in the model's own vertex format."""
    comp, frac = comp_frac
    if comp not in FORMAT:
        raise SystemExit(f"Shy Guy: {what} in a format this doesn't write ({comp})")
    code, lo, hi = FORMAT[comp]
    q = np.round(np.asarray(values) * (1 << frac)).astype(np.int64)
    if q.min() < lo or q.max() > hi:
        raise SystemExit(f"Shy Guy: {what} out of range for the model's format")
    n = q.shape[1]
    return b"".join(struct.pack(f">{n}{code}", *v) for v in q)


# ---------------------------------------------------------------- the model

def bind_positions(m):
    """Bone -> bind-pose position (model space)."""
    return {i: (w[3], w[7], w[11]) for i, w in enumerate(mdl.world_bind(m))}


def bone_map(src, dst):
    """C/V/S bone -> the same bone in another of Koopa's models: among the unused bones whose parent is the match
    of its parent, the one nearest its bind-pose position (within 1.5; the select screen's Koopa holds his arms a
    little lower)."""
    ws, wd = mdl.world_bind(src), mdl.world_bind(dst)
    ps, pd = [p for p, _ in mdl.bones(src)], [p for p, _ in mdl.bones(dst)]
    out, used = {}, set()
    for i in range(len(ws)):
        best = None
        for j in range(len(wd)):
            if j in used or pd[j] != out.get(ps[i], -1):
                continue
            d = sum((ws[i][k] - wd[j][k]) ** 2 for k in (3, 7, 11)) ** 0.5
            if d < 1.5 and (best is None or d < best[0]):
                best = (d, j)
        if best:
            out[i] = best[1]
            used.add(best[1])
    return out


def array_end(mod, start):
    """Where the array at `start` ends: the next thing any pointer in the module points at."""
    targets = sorted(v for w, v in mod.relocs if w >> 24 == 0 and v > start)
    return targets[0] if targets else len(mod.blob)


def texture_header(m, texset, index):
    return texset + m.u32(texset + 0xC + 8 * index)


def free_texture_space(m, lo, hi, banked, body_meshes):
    """True if every texture whose data overlaps [lo, hi) (in the bank, or inside the module from the texture set)
    is used by body meshes only."""
    texset = m.p(m.root + 0x8C)
    meshes, count = m.p(m.root + 0x40), m.u32(m.root + 0x3C)
    users = defaultdict(set)
    for i in range(count):
        o = meshes + 0x3C * i
        for k in range(m.blob[o + 7]):
            users[m.blob[o + 10 + 4 * k]].add(i)
    for index, (h, w, ht, fmt, at, lod) in enumerate(tx.headers(m.blob, texset)):
        if bool(at & 0x80000000) != banked:
            continue
        start = at & 0x7FFFFFFF
        end = start + sum(tx.level_size(max(1, w >> k), max(1, ht >> k), fmt) for k in range(lod + 1))
        if start < hi and lo < end and not users[index] <= set(body_meshes):
            return False
    return True


def swap(raw, obj, tex, place):
    """Rebuild one of Koopa's models around Shy Guy. obj: (pos, uv, nrm, tris, this model's bone of each position).
    place: ("bank", offset) puts the texture's header on the bank (the data goes there separately); ("inline", None)
    writes `tex` over the chosen mesh's own texture inside the module. Returns (packed file, bone palettes)."""
    pos, uv, nrm, tris, bone = obj
    mod = Module(raw)
    root = mod.root
    meshes, count = mod.ptr(root + 0x40), mod.u32(root + 0x3C)
    body = [i for i in range(count) if mod.u32(meshes + 0x3C * i + 0x38) == BODY_PART]
    ours = next(i for i in body if mod.u32(meshes + 0x3C * i + 0x34) == 2 and mod.blob[meshes + 0x3C * i + 7] >= 1)

    # Koopa's body draws nothing
    nop = mod.alloc(bytes(32), 32)
    for i in body:
        mo = meshes + 0x3C * i
        groups = mod.ptr(mo + 0x2C)
        for g in range(mod.u32(mo + 0x28)):
            go = groups + 0x38 * g
            if mod.u32(go) & 2:
                entries = mod.ptr(go + 0x34)
                for d in range(mod.u32(go + 0x30)):
                    mod.set_ptr(entries + 0x20 * d, nop)
                    mod.put32(entries + 0x20 * d + 4, 32)
            else:
                mod.set_ptr(go + 0x34, nop)
                mod.put32(go + 0x30, 32)

    # arrays: the model's own, then Shy Guy's
    def grow_array(field, stride, data):
        old = mod.ptr(root + field)
        n = (array_end(mod, old) - old) // stride
        new = mod.alloc(bytes(mod.blob[old:old + n * stride]) + data, 32)
        mod.set_ptr(root + field, new)
        return n

    pf = mdl.fmt(mod.u32(root + 4), mod.blob[root + 7])
    nf = mdl.fmt(mod.u32(root + 0x18), mod.blob[root + 0x1B])
    tf = mdl.fmt(mod.u32(root + 0x2C), mod.blob[root + 0x2F])
    unit = nrm / np.linalg.norm(nrm, axis=1, keepdims=True)
    p0 = grow_array(0x08, 6, pack_array(pos, pf, "positions"))
    n0 = grow_array(0x1C, 3, pack_array(unit, nf, "normals"))
    t0 = grow_array(0x30, 2 * struct.calcsize(FORMAT[tf[0]][0]),
                    pack_array(np.stack([uv[:, 0], -uv[:, 1]], 1), tf, "texcoords"))
    if max(p0 + len(pos), n0 + len(nrm), t0 + len(uv)) > 0x10000:
        raise SystemExit("Shy Guy: too many vertices for 16-bit indices")

    # groups of at most GROUP_BONES bones, GX winding (clockwise: the OBJ's is the other way)
    gx = [(a, c, b) for a, b, c in tris if len({a, b, c}) == 3]
    gx.sort(key=lambda t: sorted({int(bone[c[0]]) for c in t}))
    palettes, members = [], []
    for t in gx:
        need = {int(bone[c[0]]) for c in t}
        for k, pal in enumerate(palettes):
            if len(pal | need) <= GROUP_BONES:
                pal |= need
                members[k].append(t)
                break
        else:
            palettes.append(set(need))
            members.append([t])

    group_recs = bytearray()
    entries = []
    for pal, ts in zip(palettes, members):
        order = sorted(pal)
        slot = {b: 3 * k for k, b in enumerate(order)}

        def vertex(c, slot=slot, many=len(order) > 1):
            head = bytes([slot[int(bone[c[0]])]]) if many else b""
            return head + struct.pack(">3H", p0 + c[0], n0 + c[2], t0 + c[1])

        dl = mod.alloc(display_list(ts, vertex), 32)
        pts = pos[[c[0] for t in ts for c in t]]
        entries.append((dl, len(mod.blob) - dl, pts.min(0), pts.max(0)))
        group_recs += struct.pack(">II", 3, len(order)) + b"".join(
            struct.pack(">I", order[k] if k < len(order) else 0) for k in range(10)) + struct.pack(">II", 1, 0)
    ent = mod.alloc(b"".join(struct.pack(">II6f", 0, size, *lo, *hi) for dl, size, lo, hi in entries), 32)
    for k, (dl, size, lo, hi) in enumerate(entries):
        mod.set_ptr(ent + 0x20 * k, dl)
    grp = mod.alloc(bytes(group_recs), 32)
    for k in range(len(entries)):
        mod.set_ptr(grp + 0x38 * k + 0x34, ent + 0x20 * k)
    # the draw only works out matrices for bones without bit 0 at +0x5C: ours need them
    bone_base = mod.ptr(root + 0x64)
    for b in set(int(x) for x in bone):
        mod.put32(bone_base + 0x60 * b + 0x5C, mod.u32(bone_base + 0x60 * b + 0x5C) & ~1)
    mo = meshes + 0x3C * ours
    mod.put32(mo + 0x28, len(entries))
    mod.set_ptr(mo + 0x2C, grp)
    mod.put32(mo + 4, mod.u32(mo + 4) & ~0x40000000 & ~0xFFFF | 0x0101)   # no colours, one texcoord set, one texture

    # the texture: its header becomes 256x256 CMPR with 9 levels, in the bank or over the model's own textures
    m = mdl.Model(raw)
    texset = m.p(m.root + 0x8C)
    head = texture_header(m, texset, mod.blob[mo + 10])
    if place[0] == "bank":
        at, data = place[1] | 0x80000000, None
    else:
        at = m.u32(head + 8)
        if at & 0x80000000 or not free_texture_space(m, at, at + len(tex), False, body):
            raise SystemExit("Shy Guy: no room for the texture inside the model")
        mod.blob[texset + at:texset + at + len(tex)] = tex
    for k, v in enumerate((256 << 16 | 256, 14, at, 1, 1, 5, 1, 0, 8 << 8)):
        mod.put32(head + 4 * k, v)
    mod.blob += bytes((-len(mod.blob)) % 32)
    return mod.pack(), [sorted(p) for p in palettes]


# ---------------------------------------------------------------- texture

def fill_background(img, mask):
    """Push-pull: give every pixel outside the UV islands the colour of the nearest island, so mipmaps and
    texture filtering don't pull the black background into the edges."""
    levels = [(img * mask[..., None], mask.astype(np.float64))]
    while levels[-1][1].shape[0] > 1:
        c, m = levels[-1]
        h, w = m.shape
        c = c.reshape(h // 2, 2, w // 2, 2, 3).sum((1, 3))
        m = m.reshape(h // 2, 2, w // 2, 2).sum((1, 3))
        levels.append((c, m))
    c, m = levels[-1]
    out = c / np.maximum(m, 1e-9)[..., None]
    for c, m in reversed(levels[:-1]):
        up = out.repeat(2, 0).repeat(2, 1)
        own = c / np.maximum(m, 1e-9)[..., None]
        out = np.where((m > 0)[..., None], own, up)
    return np.where(mask[..., None], img, out)


def uv_mask(size, uv, tris, grow=3):
    im = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(im)
    for t in tris:
        draw.polygon([(uv[c[1]][0] * size, -uv[c[1]][1] * size) for c in t], fill=255)
    m = np.array(im) > 0
    for _ in range(grow):
        g = m.copy()
        g[1:] |= m[:-1]
        g[:-1] |= m[1:]
        g[:, 1:] |= m[:, :-1]
        g[:, :-1] |= m[:, 1:]
        m = g
    return m


def rgb565(c):
    c = np.clip(np.round(c), 0, 255).astype(np.int64)
    return ((c[..., 0] >> 3) << 11) | ((c[..., 1] >> 2) << 5) | (c[..., 2] >> 3)


def expand565(v):
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    return np.stack([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)], -1).astype(np.float64)


def cmpr_blocks(px, alpha=None):
    """Encode 4x4 blocks (n, 16, 3) as CMPR/DXT1 (n, 8) bytes. Opaque blocks use 4-colour mode, with entries 2 and
    3 blended the way the GameCube does it (5/8 and 3/8, as Dolphin decodes them); blocks with clear pixels
    (alpha < 128) use 3-colour mode, entry 3 being clear."""
    clear = np.zeros(px.shape[:2], bool) if alpha is None else alpha < 128
    w = (~clear)[..., None].astype(np.float64)
    count = np.maximum(w.sum(1, keepdims=True), 1)
    mean = (px * w).sum(1, keepdims=True) / count
    d = (px - mean) * w
    cov = np.einsum("nki,nkj->nij", d, d)
    axis = np.linalg.eigh(cov)[1][..., -1]
    proj = np.einsum("nki,ni->nk", px - mean, axis)
    proj_hi = np.where(clear, -np.inf, proj).max(1, keepdims=True)
    proj_lo = np.where(clear, np.inf, proj).min(1, keepdims=True)
    proj_hi, proj_lo = np.where(np.isfinite(proj_hi), proj_hi, 0), np.where(np.isfinite(proj_lo), proj_lo, 0)
    hi, lo = mean[:, 0] + axis * proj_hi, mean[:, 0] + axis * proj_lo
    c0, c1 = rgb565(hi), rgb565(lo)
    holes = clear.any(1)
    swap = np.where(holes, c0 > c1, c0 < c1)        # 4-colour mode needs c0 > c1, 3-colour mode c0 <= c1
    c0, c1 = np.where(swap, c1, c0), np.where(swap, c0, c1)
    e0, e1 = expand565(c0), expand565(c1)
    four = np.stack([e0, e1, (5 * e0 + 3 * e1) / 8, (3 * e0 + 5 * e1) / 8], 1)
    three = np.stack([e0, e1, (e0 + e1) / 2, np.full_like(e0, 1e9)], 1)
    pal = np.where(holes[:, None, None], three, four)
    dist = ((px[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1)
    idx = dist.argmin(-1)
    idx[(c0 == c1) & ~holes] = 0
    idx[clear] = 3
    out = np.zeros((len(px), 8), np.uint8)
    out[:, 0], out[:, 1] = c0 >> 8, c0 & 0xFF
    out[:, 2], out[:, 3] = c1 >> 8, c1 & 0xFF
    for row in range(4):
        q = idx[:, 4 * row:4 * row + 4]
        out[:, 4 + row] = (q[:, 0] << 6) | (q[:, 1] << 4) | (q[:, 2] << 2) | q[:, 3]
    return out


def cmpr(img):
    """One CMPR level from RGB or RGBA: 8x8 tiles in rows, each four 4x4 blocks (top left, top right, bottom left,
    bottom right)."""
    h, w, ch = img.shape
    th, tw = max(8, h), max(8, w)
    if (th, tw) != (h, w):   # levels under 8 pixels still take a whole tile
        img = np.pad(img, ((0, th - h), (0, tw - w), (0, 0)), mode="edge")
    blocks = img.reshape(th // 8, 2, 4, tw // 8, 2, 4, ch).transpose(0, 3, 1, 4, 2, 5, 6).reshape(-1, 16, ch)
    return cmpr_blocks(blocks[..., :3], blocks[..., 3] if ch == 4 else None).tobytes()


def put_cmpr(blob, at, old, new):
    """Encode again only the 8x8 tiles of a one-level CMPR picture (data at `at`) whose pixels changed, so the
    rest keeps the game's own bytes. old and new are RGBA."""
    h, w = old.shape[:2]
    pad = lambda a: np.pad(a, ((0, (-h) % 8), (0, (-w) % 8), (0, 0)), mode="edge")
    old, new = pad(old.astype(np.float64)), pad(new.astype(np.float64))
    for ty in range(old.shape[0] // 8):
        for tx_ in range(old.shape[1] // 8):
            region = (slice(ty * 8, ty * 8 + 8), slice(tx_ * 8, tx_ * 8 + 8))
            if (old[region] != new[region]).any():
                o = at + (ty * (old.shape[1] // 8) + tx_) * 32
                blob[o:o + 32] = cmpr(new[region])


def albedo(folder, uv, tris):
    """The OBJ's texture with the background filled in (see fill_background)."""
    src = Image.open(os.path.join(folder, ALBEDO)).convert("RGB")
    img = fill_background(np.asarray(src, np.float64), uv_mask(src.size[0], uv, tris))
    return Image.fromarray(np.clip(np.round(img), 0, 255).astype(np.uint8))


def texture(full, size, levels):
    """The texture as CMPR with mipmaps (size x size down to 1)."""
    out = b""
    for k in range(levels):
        s = max(1, size >> k)
        out += cmpr(np.asarray(full.resize((s, s), Image.BOX), np.float64))
    return out


# ---------------------------------------------------------------- pictures

def render(obj, tex, size, yaw, pitch, center, half, light=(-0.4, 0.6, 0.7)):
    """Orthographic render of the OBJ (textured, Lambert-lit) as (size, size, 4) RGBA on a clear background.
    The model turns by yaw (about y) and pitch (about x) and the view frames center +- half."""
    pos, uv, nrm, tris = obj
    alb = np.asarray(tex, np.float64)
    th, tw = alb.shape[:2]
    cy, sy, cp, sp = np.cos(np.radians(yaw)), np.sin(np.radians(yaw)), np.cos(np.radians(pitch)), np.sin(np.radians(pitch))
    rot = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]]) @ np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    p = (pos - np.array(center)) @ rot.T
    n = nrm @ rot.T
    sx, sy_, z = (p[:, 0] / half + 1) * size / 2, (1 - p[:, 1] / half) * size / 2, p[:, 2]
    light = np.array(light) / np.linalg.norm(light)
    img, depth = np.zeros((size, size, 4)), np.full((size, size), -1e9)
    for tri in tris:
        v, t, k = ([c[i] for c in tri] for i in (0, 1, 2))
        x, y, zz = sx[v], sy_[v], z[v]
        x0, x1 = max(0, int(np.floor(x.min()))), min(size - 1, int(np.ceil(x.max())))
        y0, y1 = max(0, int(np.floor(y.min()))), min(size - 1, int(np.ceil(y.max())))
        d = (y[1] - y[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (y[0] - y[2])
        if x0 > x1 or y0 > y1 or abs(d) < 1e-12:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        a = ((y[1] - y[2]) * (gx - x[2]) + (x[2] - x[1]) * (gy - y[2])) / d
        b = ((y[2] - y[0]) * (gx - x[2]) + (x[0] - x[2]) * (gy - y[2])) / d
        c = 1 - a - b
        zp = a * zz[0] + b * zz[1] + c * zz[2]
        win = (a >= -1e-6) & (b >= -1e-6) & (c >= -1e-6) & (zp > depth[y0:y1 + 1, x0:x1 + 1])
        if not win.any():
            continue
        tu = a * uv[t[0], 0] + b * uv[t[1], 0] + c * uv[t[2], 0]
        tv = -(a * uv[t[0], 1] + b * uv[t[1], 1] + c * uv[t[2], 1])
        col = alb[np.clip((tv * th).astype(int), 0, th - 1), np.clip((tu * tw).astype(int), 0, tw - 1)]
        nn = a[..., None] * n[k[0]] + b[..., None] * n[k[1]] + c[..., None] * n[k[2]]
        nn /= np.maximum(np.linalg.norm(nn, axis=-1, keepdims=True), 1e-9)
        shade = 0.55 + 0.6 * np.clip(nn @ light, 0, 1)
        depth[y0:y1 + 1, x0:x1 + 1][win] = zp[win]
        img[y0:y1 + 1, x0:x1 + 1][win] = np.concatenate(
            [np.clip(col[win] * shade[win][:, None], 0, 255), np.full((int(win.sum()), 1), 255.0)], 1)
    return img.astype(np.uint8)


def shrink(rgba, size):
    """Downsample with premultiplied alpha, so edges don't pick up the clear background's colour."""
    return np.asarray(Image.fromarray(rgba).convert("RGBa").resize((size, size), Image.LANCZOS).convert("RGBA"))


def portrait(obj, tex, size):
    """A size x size face like the other golfers': three-quarter view of the mask and hood, clear background."""
    return shrink(render(obj, tex, 4 * size, *PORTRAIT), size)


def on_white(rgba):
    a = rgba[..., 3:].astype(np.float64) / 255
    rgb = np.round(rgba[..., :3] * a + 255 * (1 - a))
    return np.concatenate([rgb, np.full(rgb.shape[:2] + (1,), 255.0)], 2)


def picture(blob, index, size):
    """(header, decoded RGBA, data offset) of a texture file's picture."""
    h, w, ht, fmt, at, lod = tx.headers(blob)[index]
    if size and (w, ht, fmt) != size:
        raise SystemExit(f"Shy Guy: picture {index} is {w}x{ht} format {fmt}, not {size}")
    return (w, ht, fmt), tx.decode(blob[at:at + tx.level_size(w, ht, fmt)], w, ht, fmt), at


def extra_row(raw, obj, tex):
    """B/U/P texture 1: his card, first of the extra page's 8 (58x58 on white)."""
    blob = bytearray(tx.load_bytes(raw))
    (w, ht, fmt), old, at = picture(blob, ROW_TEX, (464, 58, 14))
    new = old.astype(np.float64)
    new[:58, :58] = on_white(portrait(obj, tex, 58))
    put_cmpr(blob, at, old, new)
    return lz.pack(raw[0], bytes(blob))


def extra_faces(raw, icon):
    """B/U/M texture 39: his face, first of the extra page's 8 (64x64, clear background)."""
    blob = bytearray(tx.load_bytes(raw))
    (w, ht, fmt), old, at = picture(blob, FACES_TEX, (512, 64, 14))
    new = old.astype(np.float64)
    new[:, :64] = icon
    put_cmpr(blob, at, old, new)
    return lz.pack(raw[0], bytes(blob))


def face_file(raw, icon):
    """C/W/D: the in-round face (64x64 RGB5A3)."""
    blob = bytearray(tx.load_bytes(raw))
    (w, ht, fmt), old, at = picture(blob, 0, (64, 64, 5))
    tx.put_rgb5a3(blob, at, 64, 0, 0, icon)
    return lz.pack(raw[0], bytes(blob))


def emblem(raw, obj, tex):
    """C/W/C texture 0: Shy Guy's head where the kid's cap is (the leftmost drawing, on white)."""
    blob = bytearray(tx.load_bytes(raw))
    (w, ht, fmt), old, at = picture(blob, 0, None)
    if fmt != 14:
        raise SystemExit("Shy Guy: the emblem isn't a CMPR picture")
    ys, xs = np.nonzero(old[:, :w // 2, :3].min(2) < 200)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    side = int(max(x1 - x0, y1 - y0)) + 1
    new = old.astype(np.float64)
    new[max(0, y0 - 2):y1 + 3, max(0, x0 - 2):x1 + 3, :3] = 255
    head = on_white(shrink(render(obj, tex, 4 * side, 0, -5, (0, 7.2, 0), 3.8), side))
    top, left = (y0 + y1 + 1 - side) // 2, (x0 + x1 + 1 - side) // 2
    rows, cols = slice(max(0, top), top + side), slice(max(0, left), left + side)
    new[rows, cols] = head[rows.start - top:rows.start - top + new[rows, cols].shape[0],
                           cols.start - left:cols.start - left + new[rows, cols].shape[1]]
    put_cmpr(blob, at, old, new)
    return lz.pack(raw[0], bytes(blob))


# ---------------------------------------------------------------- build

def build(clean_files, folder):
    """{disc path: new packed file} for golfer 16's models, texture bank and pictures (built from Koopa's)."""
    read = lambda rel: open(os.path.join(clean_files, *rel.split("/")), "rb").read()
    obj_pos, uv, nrm, tris = load_obj(os.path.join(folder, OBJ))
    ref = mdl.Model(read(SOURCES[GOLFER_MODEL]))
    full = albedo(folder, uv, tris)
    tex = texture(full, 256, 9)

    out = {}
    raw = read(SOURCES[BANK])
    bank = bytearray(lz.decompress(raw)[0])
    for rel in (GOLFER_MODEL, "C/W/E", "B/V/K"):
        mraw = read(SOURCES[rel])
        m = mdl.Model(mraw)
        meshes, count = m.p(m.root + 0x40), m.u32(m.root + 0x3C)
        body = [i for i in range(count) if m.u32(meshes + 0x3C * i + 0x38) == BODY_PART]
        texset = m.p(m.root + 0x8C)
        banked = m.u32(texture_header(m, texset, m.blob[meshes + 0x3C * body[0] + 10]) + 8) & 0x80000000
        if banked and not free_texture_space(m, 0, len(tex), True, body):
            raise SystemExit(f"Shy Guy: {SOURCES[rel]} uses the start of the bank for more than its body")
        bones = bone_map(ref, m)
        world = bind_positions(m)
        pos, bone = rig(obj_pos, tris, {b: world[t] for b, t in bones.items()})
        missing = sorted(set(int(b) for b in bone) - set(bones))
        if missing:
            raise SystemExit(f"Shy Guy: {SOURCES[rel]} has no bones matching C/V/S {missing}")
        target = np.array([bones[int(b)] for b in bone])
        out[rel], palettes = swap(mraw, (pos, uv, nrm, tris, target), tex, ("bank", 0) if banked else ("inline", None))
        print(f"Shy Guy: {rel} (from {SOURCES[rel]}) {len(mraw)} -> {len(out[rel])} bytes, groups {palettes}")
    bank[0:len(tex)] = tex
    out[BANK] = lz.pack(raw[0], bytes(bank))
    print(f"Shy Guy: {BANK} (from {SOURCES[BANK]}) texture at the start (256x256 CMPR, 9 levels, {len(tex)} bytes)")

    obj = (obj_pos, uv, nrm, tris)
    icon = portrait(obj, full, 64)
    out[ROW] = extra_row(read(ROW), obj, full)
    out[FACES] = extra_faces(read(FACES), icon)
    out[FACE] = face_file(read(FACE), icon)
    out[PLATES] = emblem(read(PLATES), obj, full)
    print(f"Shy Guy: pictures in {ROW}, {FACES}, {FACE}, {PLATES}")
    return out
