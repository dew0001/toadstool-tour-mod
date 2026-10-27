"""Read Toadstool Tour character models (e.g. Koopa Troopa = disc files C/V/S and C/V/Z).

A model file is a type-2 (relocatable) module. Its first code stub returns a pointer to the model root, which
MODEL_DRAW (0x800072C8) and FUN_80006524 read as:
  +0x04 position format (bits 4..6 component type, low 4 bits of +0x07 = fraction bits)  +0x08 positions  +0x0C count
  +0x10 skinned positions (bind pose)  +0x14 count
  +0x18 normal format (0xFF = none)  +0x1C normals  +0x20 count  +0x24 skinned normals
  +0x2C texcoord format  +0x30 texcoords  +0x90 texcoord sets
  +0x34 colour format (0xFF = none)  +0x38 colours
  +0x3C mesh count  +0x40 meshes (0x3C each)  +0x44 materials (0x14 each)
  +0x58 extra bone count  +0x60 bone count  +0x64 bones (0x60 each)  +0x8C texture set
Rigid groups (flag bit 0) index +0x08/+0x1C directly; their positions are in model space (bind pose) and each
vertex is drawn with its bone's skin matrix (animated bone x inverse bind, the bone's +0x04 matrix). Skinned groups
index a per-instance buffer the CPU fills from +0x10/+0x24 every frame.
Mario Power Tennis (also Camelot) uses a later revision, root magic 0x0131A5B5: the same root and groups, meshes
of 0x40 bytes, bones of 0x6C, and format words without the top bit (same packing as the 0x8xxxxxxx ones).
Model() reads both.
Usage: python -I model.py <packed disc file>
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import camelot_lz as lz  # noqa: E402

COMP = {0: ("B", 1), 1: ("b", 1), 2: ("H", 2), 3: ("h", 2), 4: ("f", 4)}  # GX_U8, S8, U16, S16, F32
MAGIC_TT, MAGIC_MPT = 0x0131A313, 0x0131A5B5   # Toadstool Tour, Mario Power Tennis


def load(source):
    """Decode a packed model file given as a path or as bytes."""
    raw = source if isinstance(source, (bytes, bytearray)) else open(source, "rb").read()
    blob, end = lz.decompress(raw)
    relocs, _ = lz.relocations(raw, end)
    return blob, relocs


def u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


class Model:
    """Decoded module plus its pointers (relocation targets, as module offsets)."""

    def __init__(self, source):
        self.blob, relocs = load(source)
        self.ptr = {off: val for kind, ext, off, val in relocs if kind == 0 and not ext}
        self.root = root_offset(self.blob, relocs)
        self.mpt = self.root is not None and u32(self.blob, self.root) == MAGIC_MPT
        self.mesh_size = 0x40 if self.mpt else 0x3C
        self.bone_size = 0x6C if self.mpt else 0x60   # MPT's have 12 more bytes at the end

    def fmt(self, at):
        """(component type, fraction bits) of the format word at root + at, or None."""
        word = self.u32(self.root + at)
        if self.mpt:
            return None if word == 0xFF else ((word >> 5) & 7, word & 0x1F)
        return fmt(word, self.blob[self.root + at + 3])

    def u32(self, o):
        return u32(self.blob, o)

    def p(self, o):
        """Pointer field at o (module offset of the target), or None."""
        return self.ptr.get(o)


def root_offset(blob, relocs):
    hi = lo = None
    for kind, ext, off, val in relocs:
        if off == 20 and kind == 2:
            hi = val
        if off == 24 and kind == 3:
            lo = val
    return hi if hi == lo else None


def fmt(word, top_byte):
    if word == 0xFF:
        return None
    comp = (word >> 4) & 7 if word < 0x80000000 else (word >> 5) & 7
    frac = top_byte & 0xF if word < 0x80000000 else top_byte & 0x1F
    return comp, frac


def describe(blob, root):
    pos_fmt = fmt(u32(blob, root + 4), blob[root + 7])
    nrm_fmt = fmt(u32(blob, root + 0x18), blob[root + 0x1B])
    tex_fmt = fmt(u32(blob, root + 0x2C), blob[root + 0x2F])
    info = {
        "pos": (pos_fmt, u32(blob, root + 8), u32(blob, root + 0xC)),
        "nrm": (nrm_fmt, u32(blob, root + 0x1C), u32(blob, root + 0x20)),
        "tex": (tex_fmt, u32(blob, root + 0x30), u32(blob, root + 0x90)),
        "col": (u32(blob, root + 0x34), u32(blob, root + 0x38)),
        "meshes": (u32(blob, root + 0x3C), u32(blob, root + 0x40)),
        "materials": u32(blob, root + 0x44),
        "bones": (u32(blob, root + 0x60), u32(blob, root + 0x64), u32(blob, root + 0x58)),
        "texset": u32(blob, root + 0x8C),
        "anim": u32(blob, root + 0x54), "x7c": u32(blob, root + 0x7C),
    }
    return info


def meshes(m):
    """Yield (mesh index, mesh offset, group index, group offset, matrices, display lists) for every group.
    Mesh (0x3C): +0x04 flags (bit 30: colours), +0x06 texcoord sets, +0x07 textures, +0x28 groups, +0x2C -> groups.
    Group (0x38): +0x00 flags (bit 0: rigid positions, bit 1: several display lists), +0x04 matrix count,
    +0x08.. bone indices (palette slot n = PNMTXIDX 3n), +0x30 display list count, +0x34 -> list entries
    (0x20 each: +0 -> list, +4 size)."""
    r = m.root
    count, base = m.u32(r + 0x3C), m.p(r + 0x40)
    for i in range(count):
        mo = base + m.mesh_size * i
        groups, gbase = m.u32(mo + 0x28), m.p(mo + 0x2C)
        for g in range(groups):
            go = gbase + 0x38 * g
            nmtx = m.u32(go + 4)
            mtx = [m.u32(go + 8 + 4 * k) for k in range(min(nmtx, 10))]
            ndl, dlbase = m.u32(go + 0x30), m.p(go + 0x34)
            dls = []
            if m.u32(go) & 2:
                for d in range(ndl):
                    dls.append((m.p(dlbase + 0x20 * d), m.u32(dlbase + 0x20 * d + 4)))
            else:
                dls.append((m.p(go + 0x34), m.u32(go + 0x30)))
            yield i, mo, g, go, mtx, dls


def triangles(m, mo, nmtx, dl, size):
    """Decode one display list into triangles of vertices (pnmtx slot or 0, pos, nrm, tex)."""
    b = m.blob
    has_nrm = m.u32(m.root + 0x18) != 0xFF
    has_col = bool(m.u32(mo + 4) & 0x40000000)
    ntex = b[mo + 6]
    out, o, end = [], dl, dl + size
    while o < end:
        op = b[o]
        if op == 0:
            o += 1
            continue
        if op == 0x08:                      # GX load CP register: reg byte + 4-byte value
            o += 6
            continue
        prim = op & 0xF8
        if prim not in (0x80, 0x90, 0x98, 0xA0):
            raise ValueError(f"opcode {op:02X} at 0x{o:X}")
        n = struct.unpack_from(">H", b, o + 1)[0]
        o += 3
        verts = []
        for _ in range(n):
            slot = 0
            if nmtx != 1:
                slot = b[o] // 3                # PNMTXIDX = 3 * palette slot
                o += 1
            pos = struct.unpack_from(">H", b, o)[0]
            o += 2
            nrm = None
            if has_nrm:
                nrm = struct.unpack_from(">H", b, o)[0]
                o += 2
            if has_col:
                o += 2
            tex = None
            for t in range(ntex):
                v = struct.unpack_from(">H", b, o)[0]
                o += 2
                if t == 0:
                    tex = v
            verts.append((slot, pos, nrm, tex))
        if prim == 0x80:
            for k in range(0, n - 3, 4):
                out += [(verts[k], verts[k + 1], verts[k + 2]), (verts[k], verts[k + 2], verts[k + 3])]
        elif prim == 0x90:
            out += [tuple(verts[k:k + 3]) for k in range(0, n - 2, 3)]
        elif prim == 0x98:
            for k in range(n - 2):
                tri = (verts[k], verts[k + 1], verts[k + 2]) if k % 2 == 0 else (verts[k + 1], verts[k], verts[k + 2])
                out.append(tri)
        else:
            out += [(verts[0], verts[k], verts[k + 1]) for k in range(1, n - 1)]
    return out


def bones(m):
    """[(parent or -1, 3x4 local matrix as 12 floats)] from the bone list (0x60 each: +0 parent, +4 matrix)."""
    base, count = m.p(m.root + 0x64), m.u32(m.root + 0x60)
    out = []
    for i in range(count):
        o = base + m.bone_size * i
        parent = m.u32(o)
        out.append((-1 if parent == 0xFFFFFFFF else parent, struct.unpack_from(">12f", m.blob, o + 4)))
    return out


def mul34(a, b):
    """3x4 affine a * b (rows of 4)."""
    r = []
    for i in range(3):
        row = a[4 * i:4 * i + 4]
        for j in range(4):
            v = sum(row[k] * b[4 * k + j] for k in range(3))
            if j == 3:
                v += row[3]
            r.append(v)
    return r


def quat34(x, y, z, w):
    return [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0,
            2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0,
            2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0]


def world_bind(m):
    """Rest-pose model-space matrix of every bone: parent * T(+0x40) * R(quaternion +0x4C) * S(+0x34).
    (Each bone's +0x04 matrix is the inverse of this: model space -> bone space, used for skin blending.)"""
    base, count = m.p(m.root + 0x64), m.u32(m.root + 0x60)
    world = []
    for i in range(count):
        o = base + m.bone_size * i
        parent = m.u32(o)
        s = struct.unpack_from(">3f", m.blob, o + 0x34)
        t = struct.unpack_from(">3f", m.blob, o + 0x40)
        local = quat34(*struct.unpack_from(">4f", m.blob, o + 0x4C))
        for r in range(3):
            for c in range(3):
                local[4 * r + c] *= s[c]
            local[4 * r + 3] = t[r]
        world.append(local if parent == 0xFFFFFFFF else mul34(world[parent], local))
    return world


def apply34(mtx, p):
    return [mtx[4 * i] * p[0] + mtx[4 * i + 1] * p[1] + mtx[4 * i + 2] * p[2] + mtx[4 * i + 3] for i in range(3)]


def array(m, at_fmt, at_base, count, comps):
    (comp, frac) = m.fmt(at_fmt)
    code, size = COMP[comp]
    scale = 1 / (1 << frac)
    base = m.p(m.root + at_base)
    return [[v * scale for v in struct.unpack_from(f">{comps}{code}", m.blob, base + comps * size * i)]
            for i in range(count)]


def positions(m, skinned=False):
    """Rigid positions (root +0x08) or skinned ones (root +0x10); both in model space, bind pose."""
    return array(m, 4, 0x10 if skinned else 8, m.u32(m.root + (0x14 if skinned else 0xC)), 3)


def normals(m, skinned=False):
    """Rigid normals (root +0x1C) or skinned ones (+0x24, count +0x28)."""
    return array(m, 0x18, 0x24 if skinned else 0x1C, m.u32(m.root + (0x28 if skinned else 0x20)), 3)


def texcoords(m):
    """Texture coordinates (root +0x30), as many as the display lists index (up to the next array)."""
    base = m.p(m.root + 0x30)
    later = [v for v in m.ptr.values() if v > base]
    comp, _ = m.fmt(0x2C)
    count = (min(later) - base) // (2 * COMP[comp][1]) if later else 0
    return array(m, 0x2C, 0x30, count, 2)


def rigid_triangles(m):
    """Every triangle of the rigid groups, in model space (bind pose): [((x,y,z) * 3, mesh index)]."""
    pos = positions(m)
    out = []
    for i, mo, g, go, mtx, dls in meshes(m):
        if not m.u32(go) & 1:
            continue
        for dl, size in dls:
            for tri in triangles(m, mo, m.u32(go + 4), dl, size):
                if all(v[1] < len(pos) for v in tri):
                    out.append(([pos[v[1]] for v in tri], i))
    return out


if __name__ == "__main__":
    m = Model(sys.argv[1])
    r = m.root
    print(f"root at 0x{r:X}")
    for i in range(0x28):
        o = r + 4 * i
        p = m.p(o)
        print(f"  +0x{4 * i:02X}: {m.u32(o):08X}" + (f"  -> 0x{p:X}" if p is not None else ""))
