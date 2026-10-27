"""Scenery for the Pebble holes: generated textures (houses, the Lodge, roads), house geometry from OSM footprints,
the far landscape and sea out to FAR metres, and a ring of the real mountains round Carmel Bay beyond it.

Everything here works in local metres (x east, y south, h up: pebble.Course's frame); holegen.py turns it into game units."""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dem  # noqa: E402

FAR = 2050.0          # far landscape radius round the hole's middle (m)
RING_NEAR = 2150.0    # mountain rings (m)
RING_FAR = 2300.0


# ---------------------------------------------------------------- textures (our own art)

def _noise(size, scale, seed):
    rng = np.random.default_rng(seed)
    small = rng.uniform(0, 1, (max(2, size // scale), max(2, size // scale)))
    img = Image.fromarray((small * 255).astype(np.uint8)).resize((size, size), Image.BICUBIC)
    return np.asarray(img, np.float64) / 255


def wall_texture(seed=1, windows=2, lodge=False):
    """Stucco with a window per column per storey (two storeys per texture: v = height / 6 m)."""
    s = 128
    base = 232 + 14 * (_noise(s, 8, seed) - 0.5) + 6 * (_noise(s, 2, seed + 1) - 0.5)
    img = np.stack([base, base * 0.985, base * 0.95], -1)
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    cols = 4 if lodge else windows
    cw = s / cols
    for row in range(2):
        y0 = row * 64 + (14 if lodge else 18)
        y1 = y0 + (34 if lodge else 28)
        for k in range(cols):
            x0 = k * cw + cw * 0.28
            x1 = (k + 1) * cw - cw * 0.28
            if lodge:
                d.rectangle([x0 - 3, y0 - 2, x1 + 3, y1 + 2], fill=(60, 80, 70))   # dark green shutters
            d.rectangle([x0, y0, x1, y1], fill=(255, 255, 250))                       # frame
            d.rectangle([x0 + 2, y0 + 2, x1 - 2, y1 - 2], fill=(70, 90, 115))         # glass
            d.line([((x0 + x1) / 2, y0 + 2), ((x0 + x1) / 2, y1 - 2)], fill=(250, 250, 245), width=1)
        d.rectangle([0, row * 64 + 60, s, row * 64 + 63], fill=(200, 196, 188))       # floor band
    return im


def roof_texture(seed=2):
    """Shingle rows (grey; vertex colours tint each roof)."""
    s = 128
    rng = np.random.default_rng(seed)
    im = Image.new("RGB", (s, s), (150, 150, 150))
    d = ImageDraw.Draw(im)
    for row in range(16):
        y = row * 8
        off = (row % 2) * 6
        for k in range(-1, 12):
            x = k * 12 + off
            v = int(rng.uniform(125, 175))
            d.rectangle([x, y, x + 11, y + 7], fill=(v, v, v))
        d.line([(0, y + 7), (s, y + 7)], fill=(90, 90, 90))
    return im.filter(ImageFilter.SMOOTH)


def asphalt_texture(seed=3):
    s = 64
    v = 105 + 30 * (_noise(s, 2, seed) - 0.5) + 10 * (_noise(s, 8, seed + 1) - 0.5)
    img = np.stack([v, v, v * 1.02], -1)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


GENERATED = {"wall": (wall_texture, 128), "lodge": (lambda: wall_texture(5, lodge=True), 128),
             "roof": (roof_texture, 128), "asphalt": (asphalt_texture, 64)}


def cmpr_texture(img, size):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    import shyguy
    levels = int(math.log2(size)) + 1
    return shyguy.texture(img.convert("RGB"), size, levels), levels


# ---------------------------------------------------------------- houses

WALL_TINTS = [(255, 252, 245), (250, 240, 220), (236, 226, 205), (225, 230, 236), (245, 235, 225), (215, 205, 190)]
ROOF_TINTS = [(120, 122, 128), (95, 85, 78), (150, 90, 70), (80, 88, 96), (130, 120, 105)]


def house_mesh(poly, ground, rng, lodge=False):
    """Walls and a roof for one footprint. Returns {"wall"|"roof"|"lodge": (points (n,3) metres, tris, uv, rgb)}."""
    poly = poly.simplify(0.4)
    if poly.geom_type != "Polygon" or poly.area < 12:
        return {}
    rect = poly.minimum_rotated_rectangle
    boxy = poly.area / max(rect.area, 1e-6) > 0.8
    shape = rect if boxy else poly
    ring = list(shape.exterior.coords)[:-1]
    cx0, cy0 = shape.centroid.x, shape.centroid.y
    if shape.exterior.is_ccw is False:
        ring = ring[::-1]
    xs = np.array([p[0] for p in ring])
    ys = np.array([p[1] for p in ring])
    base = float(np.min(ground(xs, ys))) - 0.3
    storeys = 3 if lodge else (2 if poly.area > 220 or rng.uniform() < 0.35 else 1)
    top = base + 0.3 + 3.0 * storeys + 0.4
    wt = WALL_TINTS[0] if lodge else WALL_TINTS[rng.integers(len(WALL_TINTS))]
    rt = (95, 105, 110) if lodge else ROOF_TINTS[rng.integers(len(ROOF_TINTS))]
    wt = tuple(int(v * 0.56) for v in wt)      # vertex colour 128 = the texture as it is
    rt = tuple(int(min(255, v * 0.9)) for v in rt)
    out = {}
    wp, wt_, wu, wc = [], [], [], []
    along = 0.0
    for i in range(len(ring)):
        a, b = ring[i], ring[(i + 1) % len(ring)]
        L = math.dist(a, b)
        k = len(wp)
        # ring is counter-clockwise from above, so outward is to the right of a->b
        wp += [(a[0], base, a[1]), (b[0], base, b[1]), (b[0], top, b[1]), (a[0], top, a[1])]
        u0, u1 = along / 6.0, (along + L) / 6.0
        v0, v1 = 0.0, -(top - base) / 6.0
        wu += [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
        wc += [wt] * 4
        wt_ += [(k, k + 1, k + 2), (k, k + 2, k + 3)]   # front faces outward (the game's winding)
        along += L
    out["lodge" if lodge else "wall"] = (np.array(wp), wt_, np.array(wu), wc)
    # roof
    rp, rtris, ru, rc = [], [], [], []
    if boxy:
        c = np.array(rect.centroid.coords[0])
        pts = np.array(rect.exterior.coords[:4])
        e0, e1 = pts[1] - pts[0], pts[2] - pts[1]
        long_axis = e0 if np.linalg.norm(e0) >= np.linalg.norm(e1) else e1
        short = min(np.linalg.norm(e0), np.linalg.norm(e1))
        ax = long_axis / np.linalg.norm(long_axis)
        half_ridge = max(np.linalg.norm(long_axis) / 2 - short / 2, 0.3)
        rh = min(short * 0.35, 4.5)
        r0 = (c[0] - ax[0] * half_ridge, top + rh, c[1] - ax[1] * half_ridge)
        r1 = (c[0] + ax[0] * half_ridge, top + rh, c[1] + ax[1] * half_ridge)
        eave = [(p[0] + (p[0] - c[0]) * 0.06, top, p[1] + (p[1] - c[1]) * 0.06) for p in ring]
        # each eave corner joins the nearer ridge end; faces between consecutive corners
        k = 0
        for i in range(4):
            a, b = eave[i], eave[(i + 1) % 4]
            ra = r0 if np.dot(np.array([a[0], a[2]]) - c, ax) < 0 else r1
            rb = r0 if np.dot(np.array([b[0], b[2]]) - c, ax) < 0 else r1
            if ra == rb:
                rp += [a, b, ra]
                ru += [((a[0] - cx0) / 4, (a[2] - cy0) / 4), ((b[0] - cx0) / 4, (b[2] - cy0) / 4), ((ra[0] - cx0) / 4, (ra[2] - cy0) / 4)]
                rtris += [(k, k + 1, k + 2)]
                k += 3
            else:
                rp += [a, b, rb, ra]
                ru += [((p_[0] - cx0) / 4, (p_[2] - cy0) / 4) for p_ in (a, b, rb, ra)]
                rtris += [(k, k + 1, k + 2), (k, k + 2, k + 3)]
                k += 4
        rc = [rt] * len(rp)
    else:
        import mapbox_earcut as earcut
        ring2 = np.array(ring, np.float64)
        idx = earcut.triangulate_float64(ring2, np.array([len(ring2)], np.uint32)).reshape(-1, 3)
        rp = [(x, top + 0.2, y) for x, y in ring2]
        ru = [((x - cx0) / 4, (y - cy0) / 4) for x, y in ring2]
        for t in idx:
            a_, b_, c_ = (np.array(rp[i]) for i in t)
            rtris.append(tuple(int(i) for i in (t if np.cross(b_ - a_, c_ - a_)[1] < 0 else t[[0, 2, 1]])))
        rc = [rt] * len(rp)
    if rp:
        out["roof"] = (np.array(rp), rtris, np.array(ru), rc)
    return out


# ---------------------------------------------------------------- the far landscape and the mountains

def elevation(x, y):
    """Fine DEM where it has data (the course area), the coarse one elsewhere."""
    f = dem.fine()
    lat_ok = None
    hf = f.sample(x, y)
    hc = dem.coarse().sample(x, y)
    # the fine mosaic covers roughly x -2300..2200, y -1900..1700 round the origin (y south)
    inside = (np.asarray(x) > -2200) & (np.asarray(x) < 2100) & (np.asarray(y) > -1800) & (np.asarray(y) < 1600)
    return np.where(inside, hf, hc)


def horizon(center, eye_h, d0, d1, step_deg=1.5):
    """Max elevation angle of the land between d0 and d1 metres, per azimuth: [(azimuth rad, tan angle, dist)]."""
    out = []
    ds = np.geomspace(d0, d1, 90)
    for az in np.arange(0, 360, step_deg):
        a = math.radians(az)
        xs = center[0] + np.sin(a) * ds
        ys = center[1] + np.cos(a) * ds
        h = elevation(xs, ys)
        h = np.where(h > 1.5, h, -50)
        t = (h - eye_h) / ds
        i = int(np.argmax(t))
        out.append((a, float(t[i]), float(ds[i]), float(h[i])))
    return out


def mountain_ring(center, radius, profile, colour, base=-4.0):
    """A strip at `radius` whose top follows the profile's angles. Returns points (n,3), tris, uv, colours."""
    pts, uv, cols, tris = [], [], [], []
    n = len(profile)
    for i, (a, t, d, h) in enumerate(profile):
        x, y = center[0] + np.sin(a) * radius, center[1] + np.cos(a) * radius
        top = max(base + 0.5, 12.0 + t * radius)
        pts += [(x, base, y), (x, top, y)]
        uv += [(i * 0.5, 0.0), (i * 0.5, -(top - base) / 160)]
        fade = min(1.0, max(0.0, (d - 2000) / 20000))
        cc = tuple(int(colour[k] * (1 - 0.45 * fade) + (170, 185, 205)[k] * 0.45 * fade) for k in range(3))
        cols += [cc, cc]
    for i in range(n):
        j = (i + 1) % n
        a0, a1, b0, b1 = 2 * i, 2 * i + 1, 2 * j, 2 * j + 1
        if pts[a1][1] <= base + 0.6 and pts[b1][1] <= base + 0.6:
            continue
        # seen from the centre (inside the ring): faces point inwards
        tris += [(a0, b0, b1), (a0, b1, a1)]
    return np.array(pts), tris, np.array(uv), cols
