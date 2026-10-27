"""Shy Guy from Mario Power Tennis (GOME01, the maintainer's own disc): his model, ready for shyguy.py.

Mario Power Tennis is Camelot's too: the same file layout and compression, texture sets, and a later revision of
the model format (model.py reads both). Shy Guy is "heiho" there; his model is B/G/P (the select screen loads it
when the cursor reaches him; 132 bones, 26 meshes, 24 textures):

  - body meshes (BODY_MESHES): mask 3, eye whites and blush 4, eye rims 5, robe and sleeves 6, belt 7, 8, legs 9
    (untextured, colour at mesh +0x30), hood 10, robe hem 11, 12, shoes 13-16; the others are his racket, a ball,
    and a leaf skirt and feathers for other moves,
  - rigid groups index the rigid positions (+0x08, as many as the array holds, not the count field); skinned groups
    index the skinned ones (+0x10) the same way: entries up to the last block's end (root +0x54, 0x20 each, +0
    end) are in the bind pose, except a run of zeros the game fills each frame from the face table at +0x5C
    (4 bytes, then positions in the same format): his mouth,
  - each vertex's bone: a group's palette slot (DL PNMTXIDX / 3), or, for slots of -1 (the CPU-skinned buffer) or
    past the bone count, the nearest of that group's other bones,
  - in Mario Power Tennis his eye whites are drawn black; here mesh 4's eyes (EYE_BOTTOM, EYE_GAP) sample a black
    cell, the inside of his mouth (MOUTH_TOP) keeps its colour and the blush between is left out; the eyes sit
    EYE_FORWARD in front of the mask.

Everything comes out the way shyguy.load_obj gives the OBJ: positions, (u, -v) texcoords, normals, counter-clockwise
triangles of (v, vt, vn), plus one ATLAS x ATLAS texture with all his textures in it and each position's bone.
"""
import struct

import numpy as np
from PIL import Image

import model as mdl
import textures as tx

MODEL = "B/G/P"
BODY_MESHES = (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16)
EYE_FILL, EYE_RIM = 4, 5
EYE_FORWARD = 0.06      # model units the eyes come out from the mask (the game draws them over it)
EYE_BOTTOM, EYE_GAP = 7.25, 0.3   # mesh 4 above this height and this far off the middle is the eyes,
MOUTH_TOP = 6.0                   # below this the inside of his mouth, and between the two the blush (left out)
ATLAS = 256
SCALE = 1               # textures go into the atlas at their own size (as in Mario Power Tennis); 2- and
                        # 4-pixel ones as flat 4x4 blocks per texel
PAD = 8                 # each texture's edge repeated this far round it, and every cell on the 4x4 blocks of the
                        # CMPR the atlas becomes; the space left over takes the nearest texture's colours too, so
                        # the smaller mip levels don't darken textures at their edges


class Disc:
    """Read-only access to a GameCube disc image (.iso or .ciso): file bytes by path ("B/G/P")."""

    def __init__(self, path):
        self.f = open(path, "rb")
        head = self.f.read(0x8000)
        self.ciso = head[:4] == b"CISO"
        if self.ciso:
            self.block = struct.unpack("<I", head[4:8])[0]
            self.index, n = {}, 0
            for i, used in enumerate(head[8:]):
                if used:
                    self.index[i] = n
                    n += 1
        h = self.read(0, 0x440)
        fst_off, fst_size = struct.unpack(">II", h[0x424:0x42C])
        fst = self.read(fst_off, fst_size)
        count = struct.unpack(">I", fst[8:12])[0]
        names = 12 * count
        name = lambda o: fst[names + o:fst.index(b"\0", names + o)].decode("latin1")
        self.files = {}

        def walk(start, end, prefix):
            i = start
            while i < end:
                word, a, b = struct.unpack(">III", fst[12 * i:12 * i + 12])
                if word >> 24:
                    walk(i + 1, b, prefix + name(word & 0xFFFFFF) + "/")
                    i = b
                else:
                    self.files[prefix + name(word & 0xFFFFFF)] = (a, b)
                    i += 1
        walk(1, count, "")
        self.game = h[:6].decode("latin1")

    def read(self, off, size):
        if not self.ciso:
            self.f.seek(off)
            return self.f.read(size)
        out = bytearray()
        while size > 0:
            blk, o = divmod(off, self.block)
            take = min(size, self.block - o)
            if blk in self.index:
                self.f.seek(0x8000 + self.index[blk] * self.block + o)
                out += self.f.read(take)
            else:
                out += bytes(take)
            off, size = off + take, size - take
        return bytes(out)

    def file(self, path):
        off, size = self.files[path]
        return self.read(off, size)


def physical(m, at):
    """Entries the array at root + at really holds (up to the next array the module points at)."""
    base = m.p(m.root + at)
    return (min(v for v in m.ptr.values() if v > base) - base) // (3 * mdl.COMP[m.fmt(4)[0]][1])


def skinned_positions(m, used):
    """Skinned positions 0..used-1 in the bind pose, the game's face table filling the zeroed run."""
    s = np.array(mdl.array(m, 4, 0x10, used, 3))
    zero = np.nonzero(np.abs(s).sum(1) == 0)[0]
    if len(zero):
        start, n = int(zero[0]), int(zero[-1] - zero[0] + 1)
        if len(zero) != n:
            raise SystemExit("Mario Power Tennis Shy Guy: the zeroed positions aren't one run")
        comp, frac = m.fmt(4)
        code, size = mdl.COMP[comp]
        face = np.array(struct.unpack_from(f">{3 * n}{code}", m.blob, m.p(m.root + 0x5C) + 4), float) / (1 << frac)
        s[start:start + n] = face.reshape(-1, 3)
    return s


def textures_of(m):
    base = m.blob.find(b"\x00\x20\xaf\x30")
    out = []
    for h, w, ht, fmt, at, lod in tx.headers(m.blob, base):   # data offsets count from the set's start
        out.append(tx.decode(m.blob[base + at:base + at + tx.level_size(w, ht, fmt)], w, ht, fmt))
    return out


def atlas(images):
    """Pack {key: RGBA array} into one ATLAS x ATLAS image: ({key: (x, y, w, h) in pixels}, image)."""
    canvas = np.zeros((ATLAS, ATLAS, 4), np.uint8)
    used = np.zeros((ATLAS, ATLAS), bool)
    cells, x, y, row = {}, 0, 0, 0
    for key, img in sorted(images.items(), key=lambda kv: -kv[1].shape[0]):
        h, w = img.shape[:2]
        if w <= 4:   # tiny palette-like textures: each texel a flat 4x4 block
            img = np.repeat(np.repeat(img, 4, 0), 4, 1)
        elif SCALE != 1:
            img = np.asarray(Image.fromarray(img).resize((w * SCALE, h * SCALE), Image.BICUBIC))
        h, w = img.shape[:2]
        ph, pw = PAD + (-h) % 4, PAD + (-w) % 4   # whole 4x4 blocks
        if x + w + PAD + pw > ATLAS:
            x, y, row = 0, y + row, 0
        if y + h + PAD + ph > ATLAS:
            raise SystemExit("Mario Power Tennis Shy Guy: his textures don't fit the atlas")
        padded = np.pad(img, ((PAD, ph), (PAD, pw), (0, 0)), mode="edge")
        canvas[y:y + padded.shape[0], x:x + padded.shape[1]] = padded
        used[y:y + padded.shape[0], x:x + padded.shape[1]] = True
        cells[key] = (x + PAD, y + PAD, w, h)
        x, row = x + padded.shape[1], max(row, padded.shape[0])
    while not used.all():   # the rest of the atlas: the nearest texture's colours, spread a pixel at a time
        for axis, step in ((0, 1), (0, -1), (1, 1), (1, -1)):
            near = np.roll(used, step, axis)
            if step > 0:
                (near[:step] if axis == 0 else near[:, :step])[...] = False
            else:
                (near[step:] if axis == 0 else near[:, step:])[...] = False
            take = near & ~used
            canvas[take] = np.roll(canvas, step, axis)[take]
            used |= take
    return cells, Image.fromarray(canvas).convert("RGB")


def shy_guy(disc_path):
    """{"pos", "uv", "nrm", "tris", "image", "bone", "joints", "mesh"} for Mario Power Tennis' Shy Guy (bind pose;
    "mesh": each triangle's mesh)."""
    disc = Disc(disc_path)
    if disc.game != "GOME01":
        raise SystemExit(f"{disc_path} is {disc.game}, not Mario Power Tennis (GOME01)")
    m = mdl.Model(disc.file(MODEL))
    if not m.mpt:
        raise SystemExit(f"Mario Power Tennis {MODEL} isn't a model")
    world = mdl.world_bind(m)
    joints = np.array([[w[3], w[7], w[11]] for w in world])
    nbones = len(joints)
    rigid = np.array(mdl.array(m, 4, 0x08, physical(m, 0x08), 3))
    blocks = m.p(m.root + 0x54)
    used = max(m.u32(blocks + 0x20 * k) for k in range(m.u32(m.root + 0x50)))
    skinned = skinned_positions(m, used)
    uvs = np.array(mdl.texcoords(m))
    texs = textures_of(m)

    images = {"black": np.full((2, 2, 4), (8, 8, 8, 255), np.uint8)}
    tris, tri_mesh = [], []
    for i, mo, g, go, mtx, dls in mdl.meshes(m):
        if i not in BODY_MESHES:
            continue
        nm = m.u32(go + 4)
        palette = [b if b < nbones else -1 for b in (-1 if v == 0xFFFFFFFF else v for v in mtx[:nm])]
        is_rigid = m.u32(go) & 1
        texkey = int(m.blob[mo + 10]) if m.blob[mo + 7] else None
        if texkey is None:
            colour = tuple(m.blob[mo + 0x30:mo + 0x33])
            texkey = f"colour{colour}"
            images[texkey] = np.full((2, 2, 4), colour + (255,), np.uint8)
        elif texkey not in images:
            images[texkey] = texs[texkey]
        for dl, size in dls:
            for tri in mdl.triangles(m, mo, nm, dl, size):
                if any(v[1] >= (len(rigid) if is_rigid else len(skinned)) for v in tri):
                    continue
                key = texkey
                if i == EYE_FILL:   # the eye whites (drawn black in Mario Power Tennis), the blush, the mouth
                    centre = skinned[[v[1] for v in tri]].mean(0)
                    if centre[1] >= EYE_BOTTOM and abs(centre[0]) >= EYE_GAP:
                        key = "black"
                    elif centre[1] >= MOUTH_TOP:
                        continue
                out = []
                for v in tri:
                    src = ("r" if is_rigid else "s", v[1], i if i in (EYE_FILL, EYE_RIM) else None)
                    slot = palette[v[0]] if v[0] < len(palette) else -1
                    out.append((src, slot, key, None if key == "black" else v[3], palette))
                tris.append(out[::-1])   # GX winding is clockwise; OBJ's (what shyguy expects) isn't
                tri_mesh.append(i)

    cells, image = atlas(images)
    pos_index, uv_index, pos, bone, uv = {}, {}, [], [], []
    obj_tris = []
    for tri in tris:
        corner_ids = []
        for src, slot, key, t, palette in tri:
            if src not in pos_index:
                p = (rigid if src[0] == "r" else skinned)[src[1]].copy()
                b = slot
                if b < 0:   # CPU-skinned or an extra matrix: the nearest of the group's bones
                    cand = [c for c in palette if c >= 0] or list(range(nbones))
                    b = min(cand, key=lambda c: np.linalg.norm(joints[c] - p))
                pos_index[src] = len(pos)
                pos.append(p)
                bone.append(b)
            x, y, w, h = cells[key]
            u, v = (0.5, 0.5) if t is None else uvs[t]
            uk = (key, t)
            if uk not in uv_index:
                uv_index[uk] = len(uv)
                uv.append(((x + u * w) / ATLAS, -(y + v * h) / ATLAS))
            corner_ids.append((pos_index[src], uv_index[uk]))
        obj_tris.append(corner_ids)
    pos = np.array(pos)
    # the eyes come forward, out of the mask
    head = joints[7] - np.array([0, 1.5, 0])
    for src, k in pos_index.items():
        if src[2] is not None:
            d = pos[k] - head
            pos[k] += EYE_FORWARD * d / np.linalg.norm(d)
    # smooth normals from the triangles (area-weighted)
    nrm = np.zeros_like(pos)
    for (a, _), (b, _), (c, _) in obj_tris:
        nrm[[a, b, c]] += np.cross(pos[b] - pos[a], pos[c] - pos[a])
    flat = np.linalg.norm(nrm, axis=1) < 1e-9   # only degenerate triangles: point it out from the middle
    nrm[flat] = pos[flat] - np.array([0, pos[:, 1].mean(), 0])
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
    tris_out = [tuple((p, t, p) for p, t in tri) for tri in obj_tris]
    return {"pos": pos, "uv": np.array(uv), "nrm": nrm, "tris": tris_out, "image": image,
            "bone": np.array(bone), "joints": joints, "mesh": np.array(tri_mesh)}
