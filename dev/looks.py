"""Halloween costumes, the looks (v24; Andrew: "these costumes look awful out of place not sitting correctly a bunch
of copies do better", then "Go with it" for a look per golfer painted onto their own outfit).

Each golfer's costume repaints its own textures, so it always fits:
  - colour rules (hue / saturation / value ranges -> new hue, saturation, brightness; shading kept) make a 64K
    table over RGB565 colours, applied to every CMPR block's two end colours of the golfer's body textures (eyes
    left alone). The patch carries only the table: Play.bat applies it to the player's own textures (the
    "recolour" step of a create op; app 10), so no game pixels are in the download,
  - patterns (a skeleton's bones, a mummy's bandages) are whole 4x4 blocks of colours of our own, painted where
    the body point a block shows (rasterised through the meshes in texture space) falls in the pattern,
  - Daisy's bikini repaints her top and skirt textures with colours of our own (costumes.py has its shape).
Recolour blocks: the end colours go through the table; a 4-colour block (c0 > c1) whose new ends would order the
other way swaps them and flips each index's low bit (0<->1, 2<->3); equal new ends become (c, c - 1); a 3-colour
block (c0 <= c1, index 3 clear) that would flip swaps them and exchanges indices 0 and 1.
"""
import colorsys
import struct

import numpy as np

import textures as tx

# ---------------------------------------------------------------- colour tables

def expand565(v):
    v = np.asarray(v, np.int64)
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    return np.stack([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)], -1)


def to565(rgb):
    c = np.clip(np.round(np.asarray(rgb, float)), 0, 255).astype(np.int64)
    return ((c[..., 0] >> 3) << 11) | ((c[..., 1] >> 2) << 5) | (c[..., 2] >> 3)


def rule_colour(rgb, rules):
    """rgb (0..255) through the first rule it matches (or unchanged). A rule: h (lo, hi degrees, may wrap), s and
    v (lo, hi), and the new colour: "h" hue (None keeps), "s" saturation (None keeps; "smul" scales), "v" a
    brightness factor, "vadd" added after it."""
    r, g, b = (c / 255 for c in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    h *= 360
    for rule in rules:
        h0, h1 = rule.get("hue", (0, 360))
        inside = h0 <= h <= h1 if h0 <= h1 else (h >= h0 or h <= h1)
        s0, s1 = rule.get("sat", (0, 1))
        v0, v1 = rule.get("val", (0, 1))
        if inside and s0 <= s <= s1 and v0 <= v <= v1:
            nh = rule["h"] / 360 if rule.get("h") is not None else h / 360
            ns = rule["s"] if rule.get("s") is not None else min(1.0, s * rule.get("smul", 1.0))
            nv = min(1.0, max(0.0, v * rule.get("v", 1.0) + rule.get("vadd", 0.0)))
            return tuple(c * 255 for c in colorsys.hsv_to_rgb(nh, ns, nv))
    return rgb


def make_lut(rules):
    """The 65536-entry RGB565 -> RGB565 table of a look's rules (identity where no rule matches)."""
    rgb = expand565(np.arange(65536))
    out = np.arange(65536, dtype=np.int64)
    for i in range(65536):
        c = tuple(int(x) for x in rgb[i])
        n = rule_colour(c, rules)
        if n is not c:
            out[i] = int(to565(n))
    return out.astype(np.uint16)


def make_lut5a3(rules):
    """The 65536-entry table for RGB5A3 texels: opaque ones (top bit) stay opaque 5:5:5, see-through ones keep their
    3-bit alpha with 4:4:4 colour."""
    out = np.arange(65536, dtype=np.int64)
    for v in range(65536):
        if v & 0x8000:
            rgb = (((v >> 10) & 31) * 255 / 31, ((v >> 5) & 31) * 255 / 31, (v & 31) * 255 / 31)
            n = rule_colour(rgb, rules)
            if n is not rgb:
                r, g, b = (int(round(c * 31 / 255)) for c in n)
                out[v] = 0x8000 | (min(31, r) << 10) | (min(31, g) << 5) | min(31, b)
        else:
            rgb = (((v >> 8) & 15) * 17, ((v >> 4) & 15) * 17, (v & 15) * 17)
            n = rule_colour(rgb, rules)
            if n is not rgb:
                r, g, b = (int(round(c * 15 / 255)) for c in n)
                out[v] = (v & 0x7000) | (min(15, r) << 8) | (min(15, g) << 4) | min(15, b)
    return out.astype(np.uint16)


def lut_bytes(lut):
    """A table as the patch carries it: each entry's difference from its own index (u16, wrapping), so the
    untouched majority compresses to almost nothing."""
    return b"".join(struct.pack(">H", (int(v) - i) & 0xFFFF) for i, v in enumerate(lut))


def recolour5a3(data, at, length, lut):
    """RGB5A3 data in place: every texel through the table."""
    for o in range(at, at + length - 1, 2):
        v = (data[o] << 8) | data[o + 1]
        n = int(lut[v])
        data[o], data[o + 1] = n >> 8, n & 0xFF


# CMPR index bytes with indices 0 and 1 exchanged (2 and 3 kept): for 3-colour blocks whose ends swap
FLIP3 = bytes(sum(((f ^ 1 if f < 2 else f) << (2 * k)) for k, f in enumerate(((x >> (2 * k)) & 3 for k in range(4))))
              for x in range(256))


def recolour(data, at, length, lut):
    """Recolour CMPR data in place (bytearray), every 8-byte block in [at, at + length) (see the docstring)."""
    for o in range(at, at + length - 7, 8):
        c0, c1 = struct.unpack_from(">HH", data, o)
        n0, n1 = int(lut[c0]), int(lut[c1])
        if c0 > c1:                         # 4 colours
            if n0 > n1:
                struct.pack_into(">HH", data, o, n0, n1)
            elif n0 < n1:
                struct.pack_into(">HH", data, o, n1, n0)
                for k in range(4, 8):
                    data[o + k] ^= 0x55
            else:
                struct.pack_into(">HH", data, o, *((n0, n0 - 1) if n0 > 0 else (1, 0)))
        else:                               # 3 colours and clear
            if n0 <= n1:
                struct.pack_into(">HH", data, o, n0, n1)
            else:
                struct.pack_into(">HH", data, o, n1, n0)
                for k in range(4, 8):
                    data[o + k] = FLIP3[data[o + k]]


# ---------------------------------------------------------------- a model's textures

def textures_of(m):
    """[(index, banked, data offset (module offset, or bank offset), length, fmt, w, h, levels)] of a model."""
    ts = m.p(m.root + 0x8C)
    out = []
    for idx, (h, w, ht, fmt, at, lod) in enumerate(tx.headers(m.blob, ts)):
        levels = lod + 1
        length = sum(tx.level_size(max(1, w >> k), max(1, ht >> k), fmt) for k in range(levels))
        banked = bool(at & 0x80000000)
        out.append((idx, banked, (at & 0x7FFFFFFF) if banked else ts + at, length, fmt, w, ht, levels))
    return out


def body_textures(m, part=1):
    """{texture index: [mesh indexes]} of the meshes of a part (the body)."""
    meshes, count = m.p(m.root + 0x40), m.u32(m.root + 0x3C)
    out = {}
    for i in range(count):
        o = meshes + 0x3C * i
        if m.u32(o + 0x38) == part:
            for k in range(m.blob[o + 7]):
                out.setdefault(m.blob[o + 10 + 4 * k], []).append(i)
    return out


def image(src, off, fmt, w, h):
    return tx.decode(bytes(src[off:off + tx.level_size(w, h, fmt)]), w, h, fmt)[:h, :w]


def eye_like(img):
    """An eye's picture: much near-white, with a dark pupil or a coloured iris."""
    rgb = img[..., :3].reshape(-1, 3).astype(float) / 255
    mx, mn = rgb.max(1), rgb.min(1)
    white = (mn > 0.8).mean()
    dark = (mx < 0.3).mean()
    vivid = ((mx - mn) / np.maximum(mx, 1e-6) > 0.5).mean()
    return 0.15 <= white <= 0.97 and (dark > 0.005 or vivid > 0.01)


# ---------------------------------------------------------------- patterns

def block_offset(level_off, w, bx, by):
    tiles_w = (w + 7) // 8
    return level_off + ((by // 2) * tiles_w + bx // 2) * 32 + ((by % 2) * 2 + bx % 2) * 8


def uniform_block(rgb):
    c = int(to565(rgb))
    c0, c1 = (c, c - 1) if c > 0 else (1, 0)
    return struct.pack(">HH", c0, c1) + bytes(4)


def paint_blocks(data, off, w, h, levels, covered, ids, palette):
    """Paint whole CMPR blocks at every level where, over the texels the block stands for, the pattern `ids`
    ((H, W): palette index + 1, 0 = none) covers at least half of the `covered` (H, W bool) ones."""
    lvl_off = off
    for k in range(levels):
        lw, lh = max(1, w >> k), max(1, h >> k)
        step = 4 << k
        for by in range((lh + 3) // 4):
            for bx in range((lw + 3) // 4):
                ys, xs = slice(by * step, (by + 1) * step), slice(bx * step, (bx + 1) * step)
                cov = covered[ys, xs]
                if not cov.any():
                    continue
                marks = ids[ys, xs][cov]
                hit = marks[marks > 0]
                if len(hit) * 2 >= cov.sum():
                    colour = palette[int(np.bincount(hit).argmax()) - 1]
                    o = block_offset(lvl_off, lw, bx, by)
                    data[o:o + 8] = uniform_block(colour)
        lvl_off += tx.level_size(lw, lh, 14)


def rasterise(surfaces, w, h, lo, hi):
    """Per texel of a (w, h) texture: the body point it shows on the given mesh surfaces ([(positions (n, 3, 3),
    texcoords (n, 3, 2))], bind pose) as shares of the body (lo, hi its bounds): x / half width, (y - lowest) /
    height, z from the middle / half depth; and which texels any triangle shows."""
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    mid = (lo + hi) / 2
    half = np.maximum((hi - lo) / 2, 1e-6)
    pts = np.zeros((h, w, 3))
    cov = np.zeros((h, w), bool)
    for P, T in surfaces:
        for tri, uv in zip(P, T):
            uv = uv - np.floor(uv.min(0))
            px = uv * (w, h)
            x0, y0 = np.floor(px.min(0)).astype(int)
            x1, y1 = np.ceil(px.max(0)).astype(int)
            a, b, c = px
            den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(den) < 1e-12:
                continue
            ys, xs = np.mgrid[y0:y1 + 1, x0:x1 + 1]
            qx, qy = xs + 0.5, ys + 0.5
            l1 = ((b[1] - c[1]) * (qx - c[0]) + (c[0] - b[0]) * (qy - c[1])) / den
            l2 = ((c[1] - a[1]) * (qx - c[0]) + (a[0] - c[0]) * (qy - c[1])) / den
            l3 = 1 - l1 - l2
            ok = (l1 >= -0.02) & (l2 >= -0.02) & (l3 >= -0.02)
            if not ok.any():
                continue
            p = l1[ok, None] * tri[0] + l2[ok, None] * tri[1] + l3[ok, None] * tri[2]
            f = np.stack([(p[:, 0] - mid[0]) / half[0], (p[:, 1] - lo[1]) / (hi[1] - lo[1]),
                          (p[:, 2] - mid[2]) / half[2]], 1)
            yy, xx = ys[ok] % h, xs[ok] % w
            pts[yy, xx] = f
            cov[yy, xx] = True
    return pts, cov


def rasterise_bones(surfaces, w, h):
    """Per texel of a (w, h) texture: the model-space point it shows and the bone most of its triangle's corners
    ride (-1 where no triangle). surfaces: [(positions (n, 3, 3), texcoords (n, 3, 2), bones (n, 3))]."""
    pts = np.zeros((h, w, 3))
    bone = np.full((h, w), -1, np.int64)
    for P, T, B in surfaces:
        for tri, uv, bb in zip(P, T, B):
            uv = uv - np.floor(uv.min(0))
            px = uv * (w, h)
            x0, y0 = np.floor(px.min(0)).astype(int)
            x1, y1 = np.ceil(px.max(0)).astype(int)
            a, b, c = px
            den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(den) < 1e-12:
                continue
            ys, xs = np.mgrid[y0:y1 + 1, x0:x1 + 1]
            qx, qy = xs + 0.5, ys + 0.5
            l1 = ((b[1] - c[1]) * (qx - c[0]) + (c[0] - b[0]) * (qy - c[1])) / den
            l2 = ((c[1] - a[1]) * (qx - c[0]) + (a[0] - c[0]) * (qy - c[1])) / den
            l3 = 1 - l1 - l2
            ok = (l1 >= -0.02) & (l2 >= -0.02) & (l3 >= -0.02)
            if not ok.any():
                continue
            p = l1[ok, None] * tri[0] + l2[ok, None] * tri[1] + l3[ok, None] * tri[2]
            vals, counts = np.unique(bb, return_counts=True)
            yy, xx = ys[ok] % h, xs[ok] % w
            pts[yy, xx] = p
            bone[yy, xx] = vals[counts.argmax()]
    return pts, bone


def paint_ours(data, off, w, h, levels, pts, cov, colour):
    """Repaint a CMPR texture in place with colours of our own only: every texel the meshes show gets
    colour(body share), the others in its tiles the nearest painted colour; tiles the meshes don't touch keep
    their bytes. (Daisy's bikini.)"""
    from PIL import Image
    import shyguy
    img = np.zeros((h, w, 3))
    for y, x in zip(*np.nonzero(cov)):
        img[y, x] = colour(pts[y, x])
    if cov.any():                                  # fill the rest from the nearest painted texel (grow rings)
        done = cov.copy()
        while not done.all():
            grow = np.zeros_like(done)
            acc = np.zeros_like(img)
            cnt = np.zeros((h, w))
            for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                sd = np.roll(done, (dy, dx), (0, 1))
                si = np.roll(img, (dy, dx), (0, 1))
                new = sd & ~done
                acc[new] += si[new]
                cnt[new] += 1
                grow |= new
            img[grow] = acc[grow] / cnt[grow][:, None]
            done |= grow
    lvl_off = off
    base = Image.fromarray(np.clip(np.round(img), 0, 255).astype(np.uint8))
    for k in range(levels):
        lw, lh = max(1, w >> k), max(1, h >> k)
        level = np.asarray(base.resize((lw, lh), Image.BOX), float) if k else img
        enc = shyguy.cmpr(level)
        step = 8 << k
        tiles_w = (lw + 7) // 8
        for ty in range((lh + 7) // 8):
            for tx_ in range(tiles_w):
                if cov[ty * step:(ty + 1) * step, tx_ * step:(tx_ + 1) * step].any():
                    t = (ty * tiles_w + tx_) * 32
                    data[lvl_off + t:lvl_off + t + 32] = enc[t:t + 32]
        lvl_off += tx.level_size(lw, lh, 14)


def socket_eye(img):
    """Dry Bones' eye, all colours of our own: a black hollow socket with a small glowing white pupil where the
    eye's own pupil was (a third of its size, a soft glow round it). img: the eye's picture (its pupil: the dark
    pixels' middle)."""
    h, w = img.shape[:2]
    dark = img[..., :3].max(-1) < 80
    ys, xs = np.nonzero(dark)
    cx, cy = (xs.mean(), ys.mean()) if len(xs) else (w / 2, h / 2)
    r = max(1.5, (np.sqrt(dark.sum() / np.pi) if len(xs) else min(w, h) / 6) * 0.36)
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.hypot(xx + 0.5 - cx, yy + 0.5 - cy)
    socket = np.array([14.0, 12.0, 18.0])
    core = np.array([245.0, 245.0, 236.0])
    glow = np.clip(1 - (d - r) / (1.6 * r), 0, 1)[..., None] ** 2 * 0.55
    out = socket * (1 - glow) + np.array([200.0, 205.0, 215.0]) * glow
    out[d <= r] = core
    return out


def encode_levels(rgb, w, h, levels):
    """A picture of our own as CMPR with mipmaps (box filtered)."""
    from PIL import Image
    import shyguy
    base = Image.fromarray(np.clip(np.round(rgb), 0, 255).astype(np.uint8))
    return b"".join(shyguy.cmpr(np.asarray(base.resize((max(1, w >> k), max(1, h >> k)), Image.BOX), float))
                    for k in range(levels))


# ---------------------------------------------------------------- the looks

WHITE_BONE = (236, 232, 214)
BANDAGE = (226, 214, 180)
BANDAGE_LINE = (168, 150, 112)


class Anatomy:
    """A golfer's parts for patterns, from its in-round model's skeleton and body: the torso's bones (pelvis to
    chest) and its box (hip to shoulders, half width, middle depth), and each limb bone's place."""

    def __init__(self, m, chest, pelvis, neck, skeleton, body_points):
        par, world, kids = skeleton(m)
        self.world = np.array([[w[3], w[7], w[11]] for w in world])
        sub = lambda b: _subtree(kids, b)
        torso, b = [], chest
        while b >= 0:
            torso.append(b)
            if b == pelvis:
                break
            b = par[b]
        self.torso = set(torso)
        head = set(sub(neck))
        self.arms = set()
        for k in kids[chest]:
            if k != neck and k not in head:
                self.arms |= set(sub(k))
        self.legs = set()
        for k in kids[pelvis]:
            if k not in self.torso and k not in head and k not in self.arms:
                self.legs |= set(sub(k))
        pts, bones = body_points(m)
        tp = pts[np.isin(bones, list(self.torso))]
        arm_y = [self.world[k][1] for k in kids[chest] if k in self.arms]
        self.hip = float(self.world[pelvis][1])
        self.shoulder = float(np.mean(arm_y)) if arm_y else float(tp[:, 1].max())
        self.half = float(np.percentile(np.abs(tp[:, 0]), 90)) if len(tp) else 1.0
        self.mid_z = float(np.median(tp[:, 2])) if len(tp) else 0.0


def _subtree(kids, b):
    out, todo = [], [b]
    while todo:
        x = todo.pop()
        out.append(x)
        todo += kids[x]
    return out


def skeleton_ids(an, pts, bone):
    """1 where a bone of a skeleton costume shows: ribs, sternum and pelvis on the torso's front, the spine on its
    back, a bone along the front of each arm and leg."""
    x, y, z = pts[..., 0], pts[..., 1], pts[..., 2]
    span = max(an.shoulder - an.hip, 1e-6)
    t = (y - an.hip) / span                       # 0 at the hip bone, 1 at the shoulders
    front = z > an.mid_z
    torso = np.isin(bone, list(an.torso))
    ribs = torso & front & (t > 0.42) & (t < 0.95) & (np.abs(x) < 0.85 * an.half) & (((t - 0.42) / 0.11) % 1.0 < 0.42)
    sternum = torso & front & (t > 0.4) & (t < 0.97) & (np.abs(x) < 0.09 * an.half)
    pelvis = torso & front & (t > 0.0) & (t < 0.16) & (np.abs(x) < 0.7 * an.half)
    spine = torso & ~front & (t > 0.0) & (t < 0.97) & (np.abs(x) < 0.11 * an.half)
    bw = an.world[np.clip(bone, 0, len(an.world) - 1)]
    limb_r = 0.22 * an.half
    arms = np.isin(bone, list(an.arms)) & (np.abs(y - bw[..., 1]) < limb_r) & (z > bw[..., 2])
    legs = np.isin(bone, list(an.legs)) & (np.abs(x - bw[..., 0]) < limb_r) & (z > bw[..., 2])
    return (ribs | sternum | pelvis | spine | arms | legs).astype(np.int64)


def bandage_ids(an, pts, bone):
    """A mummy's wraps: darker lines slanting round the body and limbs."""
    x, y, z = pts[..., 0], pts[..., 1], pts[..., 2]
    band = max(an.shoulder - an.hip, 1e-6) / 7
    t = (y + 0.35 * x * np.sign(z - an.mid_z + 1e-9)) / band
    return (t % 1.0 < 0.2).astype(np.int64)


PATTERNS = {"skeleton": (skeleton_ids, [WHITE_BONE]), "bandage": (bandage_ids, [BANDAGE_LINE])}
# the in-round model's chest, pelvis and neck bones of each golfer with a pattern
PATTERN_BONES = {0: (3, 1, 4), 3: (16, 14, 17), 16: (17, 17, 33)}

# hue ranges (degrees): red 345..15, orange 15..40, yellow 40..70, green 75..165, blue 195..255, purple 255..300,
# pink 300..345
LOOKS = {
    0: {"name": "Skeleton Mario", "pattern": "skeleton", "rules": [
        {"hue": (345, 12), "sat": (0.72, 1), "h": 270, "s": 0.25, "v": 0.18},           # red shirt and cap
        {"hue": (200, 250), "sat": (0.55, 1), "h": 270, "s": 0.25, "v": 0.2}]},         # blue overalls
    1: {"name": "Grim Reaper Waluigi", "rules": [
        {"hue": (250, 305), "sat": (0.3, 1), "h": 260, "s": 0.2, "v": 0.2},             # purple
        {"hue": (200, 250), "sat": (0.2, 1), "h": 260, "s": 0.15, "v": 0.25},           # dark blue overalls
        {"hue": (15, 70), "sat": (0.5, 1), "val": (0.5, 1), "h": 0, "s": 0.0, "v": 0.45}]},  # orange shoes, yellow
    2: {"name": "Witch Peach", "rules": [
        {"hue": (300, 350), "sat": (0.25, 1), "h": 280, "s": 0.55, "v": 0.32}]},        # pink dress
    3: {"name": "Mummy Luigi", "pattern": "bandage", "rules": [
        {"hue": (75, 165), "sat": (0.35, 1), "h": 42, "s": 0.2, "v": 1.6, "vadd": 0.1},  # green shirt and cap
        {"hue": (195, 255), "sat": (0.25, 1), "h": 40, "s": 0.22, "v": 2.4, "vadd": 0.1}]},  # blue overalls
    4: {"name": "Dry Bowser", "rules": [
        {"hue": (35, 65), "sat": (0.35, 1), "h": 45, "s": 0.12, "v": 1.05},             # yellow skin
        {"hue": (75, 170), "sat": (0.3, 1), "h": 220, "s": 0.06, "v": 0.55}]},          # green shell
    5: {"name": "Vampire Wario", "rules": [
        {"hue": (40, 70), "sat": (0.45, 1), "h": 270, "s": 0.2, "v": 0.2},              # yellow shirt and cap
        {"hue": (280, 330), "sat": (0.3, 1), "h": 355, "s": 0.85, "v": 0.85},           # purple overalls
        {"hue": (75, 165), "sat": (0.4, 1), "h": 270, "s": 0.2, "v": 0.25},             # green shoes
        {"hue": (15, 40), "sat": (0.2, 0.6), "val": (0.7, 1), "smul": 0.35, "v": 1.02}]},  # skin: pale
    6: {"name": "Haunted Metal Mario", "rules": [
        {"sat": (0, 0.25), "h": 275, "s": 0.45, "v": 0.85}]},                           # metal: dark purple
    7: {"name": "Birdo", "rules": [
        {"hue": (345, 15), "sat": (0.5, 1), "h": 270, "s": 0.2, "v": 0.2}]},            # red bow: black
    8: {"name": "Zombie Yoshi", "rules": [
        {"hue": (75, 165), "sat": (0.3, 1), "h": 85, "s": 0.28, "v": 0.78},             # green: grey-green
        {"hue": (345, 15), "sat": (0.45, 1), "h": 15, "s": 0.55, "v": 0.5},             # red saddle: rust
        {"hue": (15, 45), "sat": (0.5, 1), "h": 30, "s": 0.12, "v": 0.6}]},             # orange shoes: grey
    9: {"name": "Werewolf Donkey Kong", "rules": [
        {"hue": (0, 40), "sat": (0.55, 1), "h": 30, "s": 0.07, "v": 1.15},             # brown fur: grey
        {"hue": (20, 45), "sat": (0.2, 0.55), "val": (0.6, 1), "smul": 0.45, "v": 0.95},  # tan skin: greyer
        {"hue": (345, 15), "sat": (0.5, 1), "h": 270, "s": 0.2, "v": 0.2}]},            # red tie: black
    10: {"name": "Vampire Bat Diddy", "rules": [
        {"hue": (5, 40), "sat": (0.45, 1), "val": (0, 0.7), "h": 270, "s": 0.15, "v": 0.35},  # brown fur: black
        {"hue": (345, 15), "sat": (0.5, 1), "h": 270, "s": 0.2, "v": 0.22},             # red cap and shirt
        {"hue": (20, 45), "sat": (0.2, 0.7), "val": (0.7, 1), "smul": 0.3, "v": 0.97}]},  # tan face: pale
    11: {"name": "Jack-o'-lantern Boo", "rules": [
        {"sat": (0, 0.15), "val": (0.75, 1), "h": 28, "s": 0.85, "v": 0.95}]},          # white: pumpkin orange
    12: {"name": "Zombie Petey", "rules": [
        {"hue": (70, 165), "sat": (0.3, 1), "h": 80, "s": 0.3, "v": 0.75},              # green
        {"hue": (345, 15), "sat": (0.5, 1), "h": 285, "s": 0.7, "v": 0.7},              # red head: purple
        {"hue": (15, 50), "sat": (0.5, 1), "smul": 0.5, "v": 0.8}]},                    # orange petals
    13: {"name": "Daisy", "rules": []},                                                 # the bikini (costumes.py)
    14: {"name": "Dry Bowser Jr.", "rules": [
        {"hue": (35, 65), "sat": (0.35, 1), "h": 45, "s": 0.12, "v": 1.05},
        {"hue": (75, 170), "sat": (0.3, 1), "h": 220, "s": 0.06, "v": 0.55}]},
    15: {"name": "Dry Bones Koopa", "rules": [                                       # Andrew: "make koopa dry bones
        {"hue": (40, 65), "sat": (0.45, 1), "h": 45, "s": 0.1, "v": 1.05},              # for his skin": yellow skin
        {"hue": (25, 65), "sat": (0.12, 0.45), "h": 45, "s": 0.07, "v": 0.92},          # cream belly plate: bone, its
        {"hue": (75, 170), "sat": (0.3, 1), "h": 220, "s": 0.05, "v": 0.85},            # lines like ribs; green shell:
        {"hue": (345, 15), "sat": (0.5, 1), "h": 0, "s": 0.0, "v": 0.3}],               # pale grey; red mouth, shoes
         "eye_paint": socket_eye},                                                       # dark; Andrew: "his eyes need
                                                                                        # to look like dry bones"
    16: {"name": "Skeleton Shy Guy", "pattern": "skeleton", "rules": [
        {"hue": (345, 15), "sat": (0.65, 1), "h": 270, "s": 0.25, "v": 0.18},           # red robe
        {"hue": (200, 255), "sat": (0.4, 1), "h": 270, "s": 0.25, "v": 0.2}]},          # blue shoes and belt
    17: {"name": "Black Cat Tony", "rules": [
        {"hue": (8, 48), "sat": (0.42, 1), "val": (0.2, 1), "h": 270, "s": 0.15, "v": 0.2},  # orange fur: black
        {"hue": (345, 8), "sat": (0.5, 1), "h": 28, "s": 0.9, "v": 1.0}]},              # red bandana: orange
}
