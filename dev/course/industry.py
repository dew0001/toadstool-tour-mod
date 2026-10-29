"""Industrial scenery for Pasadena Municipal (v21; Andrew: "Make the background like factories and refineries because
that's what's in Pasadena"): the oil tank farm and the hangars round the course from OSM as metal tanks and sheds, and
refineries on the horizon like the Houston Ship Channel's, which lie a few km north of the course.

Everything in local metres (x east, y south, h up: pebble.Course's frame), as parts for holegen.parts_arrays:
(texture, material, surface code, points (n, 3) as (x, h, y), tris, uv, rgb). Textures: scenery.GENERATED "metal",
"siding", "stack", "frame". Faces are flat-shaded by the hole's light and hazed with distance like the far land.
"""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

LIGHT = np.array([0.7071, 0.5934, 0.3851])   # towards the light, (x, h, y): holegen.LIGHT negated
HAZE = np.array([150, 165, 175])
SITE_STEP = 650.0             # metres between refinery sites (a world grid, so every hole sees the same plants)
SITE_RANGE = (800.0, 1900.0)  # distance from the hole's middle at which a site is drawn (the far land: 2050)
SITE_CLEAR = 350.0            # and at least this far from the course
SITE_LINE = 680.0             # and from the hole's line (its own land and houses reach 560 m)
SITE_SECTOR = (-75.0, 125.0)  # bearing (degrees from north, clockwise) of the industrial horizon: north to east
CODE = 0x06                   # surface code (out of bounds, like the houses)


# ---------------------------------------------------------------- textures (our own art)

def _noise(size, scale, seed):
    rng = np.random.default_rng(seed)
    small = rng.uniform(0, 1, (max(2, size // scale), max(2, size // scale)))
    img = Image.fromarray((small * 255).astype(np.uint8)).resize((size, size), Image.BICUBIC)
    return np.asarray(img, np.float64) / 255


def metal_texture(seed=11):
    """Painted steel plates: light grey with plate seams and a few rust streaks (vertex colours tint it)."""
    s = 128
    v = 214 + 10 * (_noise(s, 8, seed) - 0.5) + 5 * (_noise(s, 2, seed + 1) - 0.5)
    img = np.stack([v, v * 1.01, v * 1.02], -1)
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    for k in range(4):
        d.line([(k * 32, 0), (k * 32, s)], fill=(170, 172, 175), width=1)
        d.line([(0, k * 32 + 16), (s, k * 32 + 16)], fill=(178, 180, 182), width=1)
    rng = np.random.default_rng(seed)
    for _ in range(5):
        x = int(rng.uniform(4, s - 4))
        y0 = int(rng.uniform(0, s * 0.6))
        d.line([(x, y0), (x, y0 + int(rng.uniform(15, 40)))], fill=(165, 130, 100), width=1)
    return im.filter(ImageFilter.SMOOTH)


def siding_texture(seed=12):
    """Corrugated metal siding: vertical ribs."""
    s = 128
    x = np.arange(s)
    rib = 0.5 + 0.5 * np.cos(2 * np.pi * x / 8)
    v = 175 + 45 * rib[None, :] + 8 * (_noise(s, 8, seed) - 0.5)
    img = np.stack([v, v, v * 1.02], -1)
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    ImageDraw.Draw(im).line([(0, 126), (s, 126)], fill=(120, 120, 125), width=2)    # panel joint
    return im


def stack_texture():
    """A smokestack's red and white bands (one of each per texture height)."""
    s = 64
    im = Image.new("RGB", (s, s), (238, 238, 236))
    ImageDraw.Draw(im).rectangle([0, 0, s, s // 2 - 1], fill=(205, 45, 38))
    return im


def frame_texture():
    """A process unit's steel structure: dark beams and platforms with pipes."""
    s = 64
    im = Image.new("RGB", (s, s), (62, 66, 72))
    d = ImageDraw.Draw(im)
    for k in range(0, s, 16):
        d.line([(k, 0), (k, s)], fill=(120, 124, 130), width=2)
        d.line([(0, k), (s, k)], fill=(140, 144, 150), width=2)
    d.line([(0, 0), (16, 16)], fill=(100, 104, 110))
    d.line([(32, 32), (48, 48)], fill=(100, 104, 110))
    for x in (6, 40):
        d.line([(x, 0), (x, s)], fill=(190, 190, 185), width=1)
    return im


GENERATED = {"metal": (metal_texture, 128), "siding": (siding_texture, 128), "stack": (stack_texture, 64),
             "frame": (frame_texture, 64)}


# ---------------------------------------------------------------- shapes

class Parts:
    """Collects faces per texture; each face gets its own vertices (flat shading)."""

    def __init__(self, center):
        self.center = np.asarray(center, float)
        self.by_tex = {}

    def face(self, tex, pts, uv, tint):
        """A convex polygon (points (x, h, y), counter-clockwise seen from outside) as a triangle fan."""
        pts = np.asarray(pts, float)
        n = np.cross(pts[1] - pts[0], pts[2] - pts[0])
        ln = np.linalg.norm(n)
        if ln < 1e-9:
            return
        n /= ln
        # the game's winding: (p1 - p0) x (p2 - p0) points down for an upward face, so the outward normal is -n
        shade = 0.62 + 0.42 * max(0.0, float(-n @ LIGHT))
        d = math.dist((pts[:, 0].mean(), pts[:, 2].mean()), self.center)
        haze = min(0.45, max(0.0, (d - 800) / 2500))
        rgb = np.clip(np.asarray(tint, float) * shade * (1 - haze) + HAZE * haze * 0.56, 0, 255)
        P, T, U, C = self.by_tex.setdefault(tex, ([], [], [], []))
        k = len(P)
        P += [tuple(p) for p in pts]
        U += [tuple(u) for u in uv]
        C += [tuple(int(v) for v in rgb)] * len(pts)
        T += [(k, k + i, k + i + 1) for i in range(1, len(pts) - 1)]

    def parts(self, mat=0):
        return [(tex, mat, CODE, np.array(P), T, np.array(U), C) for tex, (P, T, U, C) in self.by_tex.items() if T]


def cylinder(out, tex, cx, cy, r, base, height, tint, sides=10, top_r=None, v_scale=6.0, cap_tint=None):
    top_r = r if top_r is None else top_r
    ang = np.linspace(0, 2 * np.pi, sides + 1)
    u_step = 2 * np.pi * r / sides / 6.0
    for i in range(sides):
        a0, a1 = ang[i], ang[i + 1]
        p = [(cx + r * math.cos(a0), base, cy + r * math.sin(a0)), (cx + r * math.cos(a1), base, cy + r * math.sin(a1)),
             (cx + top_r * math.cos(a1), base + height, cy + top_r * math.sin(a1)),
             (cx + top_r * math.cos(a0), base + height, cy + top_r * math.sin(a0))]
        u0, u1 = i * u_step, (i + 1) * u_step
        out.face(tex, p, [(u0, 0), (u1, 0), (u1, -height / v_scale), (u0, -height / v_scale)], tint)
    if top_r > 0.05:   # flat top (counter-clockwise in x, y: the game's winding for a face that looks up)
        cap = [(cx + top_r * math.cos(a), base + height, cy + top_r * math.sin(a)) for a in ang[:-1]]
        out.face(tex, cap, [((p[0] - cx) / 6, (p[2] - cy) / 6) for p in cap], cap_tint or tint)


def box(out, tex, cx, cy, w, d, yaw, base, height, tint, roof_tex=None, roof_tint=None, v_scale=6.0):
    c, s = math.cos(yaw), math.sin(yaw)
    corners = [(cx + c * x - s * y, cy + s * x + c * y) for x, y in ((-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2),
                                                                     (-w / 2, d / 2))]
    if (corners[1][0] - corners[0][0]) * (corners[2][1] - corners[0][1]) - \
            (corners[1][1] - corners[0][1]) * (corners[2][0] - corners[0][0]) < 0:
        corners = corners[::-1]
    prism(out, tex, corners, base, height, tint, roof_tex, roof_tint, v_scale)


def prism(out, tex, ring, base, height, tint, roof_tex=None, roof_tint=None, v_scale=6.0):
    """Walls round a counter-clockwise (x, y) ring and a flat roof (a fan, so the ring should be near convex)."""
    along = 0.0
    for i in range(len(ring)):
        a, b = ring[i], ring[(i + 1) % len(ring)]
        L = math.dist(a, b)
        p = [(a[0], base, a[1]), (b[0], base, b[1]), (b[0], base + height, b[1]), (a[0], base + height, a[1])]
        out.face(tex, p, [(along / 6, 0), ((along + L) / 6, 0), ((along + L) / 6, -height / v_scale),
                          (along / 6, -height / v_scale)], tint)
        along += L
    cx = sum(p[0] for p in ring) / len(ring)
    cy = sum(p[1] for p in ring) / len(ring)
    roof = [(x, base + height, y) for x, y in ring]
    out.face(roof_tex or tex, roof, [((p[0] - cx) / 6, (p[2] - cy) / 6) for p in roof], roof_tint or tint)


def flame(out, cx, cy, top):
    for r, h, tint in ((2.2, 7.0, (255, 120, 25)), (1.2, 10.0, (255, 210, 70))):
        cylinder(out, "metal", cx, cy, r, top, h, tint, sides=6, top_r=0.0)


# ---------------------------------------------------------------- what stands where

TANK_TINTS = [(150, 150, 146), (146, 144, 136), (140, 142, 144)]          # vertex colour 128 = the texture as is
SHED_TINTS = [(130, 138, 146), (140, 140, 136), (118, 128, 140), (142, 136, 128)]


def osm_tank(out, poly, ground, rng):
    """A storage tank from its OSM circle."""
    r = math.sqrt(poly.area / math.pi)
    c = poly.centroid
    base = float(ground(np.array([c.x]), np.array([c.y]))[0]) - 0.3
    h = float(np.clip(r * 0.7, 8, 16)) * rng.uniform(0.9, 1.1)
    cylinder(out, "metal", c.x, c.y, r, base, h, TANK_TINTS[rng.integers(len(TANK_TINTS))], sides=14)


def osm_shed(out, poly, ground, rng, hangar=False):
    """A hangar or industrial building: metal siding and a flat roof on its footprint (or its rectangle)."""
    poly = poly.simplify(0.5)
    if poly.geom_type != "Polygon" or poly.area < 12:
        return
    rect = poly.minimum_rotated_rectangle
    shape = rect if poly.area / max(rect.area, 1e-6) > 0.75 or len(poly.exterior.coords) > 12 else poly
    ring = list(shape.exterior.coords)[:-1]
    if not shape.exterior.is_ccw:
        ring = ring[::-1]
    xs = np.array([p[0] for p in ring])
    ys = np.array([p[1] for p in ring])
    base = float(np.min(ground(xs, ys))) - 0.3
    h = rng.uniform(11, 15) if hangar else rng.uniform(6, 10)
    prism(out, "siding", ring, base, h, SHED_TINTS[rng.integers(len(SHED_TINTS))], "metal", (120, 120, 118))


def refinery(out, sx, sy, ground, seed):
    """One plant round (sx, sy): a tank farm, distillation columns by a process unit, stacks, a flare, sheds."""
    rng = np.random.default_rng(seed)
    g = lambda x, y: float(ground(np.array([x]), np.array([y]))[0]) - 0.5
    yaw = rng.uniform(0, np.pi)
    c, s = math.cos(yaw), math.sin(yaw)
    at = lambda u, v: (sx + c * u - s * v, sy + s * u + c * v)
    # tank farm
    rows, cols = rng.integers(2, 4), rng.integers(2, 5)
    r = rng.uniform(11, 18)
    tint = TANK_TINTS[rng.integers(len(TANK_TINTS))]
    for i in range(rows):
        for j in range(cols):
            if rng.uniform() < 0.15:
                continue
            x, y = at(-140 + j * (2 * r + 12), -60 + i * (2 * r + 12))
            cylinder(out, "metal", x, y, r * rng.uniform(0.85, 1.05), g(x, y), rng.uniform(11, 17), tint, sides=12)
    # process unit with its columns
    ux, uy = at(40, 30)
    box(out, "frame", ux, uy, rng.uniform(25, 40), rng.uniform(18, 28), yaw, g(ux, uy), rng.uniform(35, 60),
        (150, 150, 150), "metal", (110, 110, 110))
    for k in range(rng.integers(3, 7)):
        x, y = at(40 + rng.uniform(-35, 35), 30 + rng.choice([-1, 1]) * rng.uniform(20, 32))
        cylinder(out, "metal", x, y, rng.uniform(2.4, 4.2), g(x, y), rng.uniform(50, 95), (156, 156, 152), sides=8)
    # smokestacks and a flare
    for k in range(rng.integers(1, 3)):
        x, y = at(rng.uniform(70, 120), rng.uniform(-40, 40))
        cylinder(out, "stack", x, y, rng.uniform(3.2, 4.4), g(x, y), rng.uniform(90, 130), (128, 128, 128), sides=8,
                 top_r=2.2, v_scale=16.0, cap_tint=(60, 60, 60))
    x, y = at(rng.uniform(-60, 60), rng.uniform(60, 90))
    h = rng.uniform(80, 110)
    cylinder(out, "metal", x, y, 1.0, g(x, y), h, (120, 120, 118), sides=6)
    flame(out, x, y, g(x, y) + h)
    # sheds and a cracking tower now and then
    for k in range(rng.integers(2, 5)):
        x, y = at(rng.uniform(-120, 120), rng.uniform(-110, -70) if k % 2 else rng.uniform(70, 110))
        box(out, "siding", x, y, rng.uniform(30, 70), rng.uniform(18, 35), yaw, g(x, y), rng.uniform(8, 16),
            SHED_TINTS[rng.integers(len(SHED_TINTS))], "metal", (120, 120, 118))
    if rng.uniform() < 0.5:
        x, y = at(-20, 70)
        box(out, "frame", x, y, 16, 16, yaw, g(x, y), rng.uniform(65, 90), (150, 150, 150), "metal", (110, 110, 110))


def skyline(out, mid, ground, area, line):
    """Refineries on a world grid, drawn where they are SITE_RANGE from the hole's middle in SITE_SECTOR and clear
    of the course."""
    lo, hi = SITE_RANGE
    n = int(hi // SITE_STEP) + 2
    i0, j0 = int(mid[0] // SITE_STEP), int(mid[1] // SITE_STEP)
    count = 0
    for i in range(i0 - n, i0 + n + 1):
        for j in range(j0 - n, j0 + n + 1):
            rng = np.random.default_rng(1_000_003 * (i + 500) + (j + 500))
            sx = (i + rng.uniform(0.2, 0.8)) * SITE_STEP
            sy = (j + rng.uniform(0.2, 0.8)) * SITE_STEP
            dx, dy = sx - mid[0], sy - mid[1]
            d = math.hypot(dx, dy)
            bearing = math.degrees(math.atan2(dx, -dy))
            if not lo <= d <= hi or not SITE_SECTOR[0] <= bearing <= SITE_SECTOR[1]:
                continue
            if area.distance(_pt(sx, sy)) < SITE_CLEAR or line.distance(_pt(sx, sy)) < SITE_LINE \
                    or rng.uniform() < 0.2:
                continue
            refinery(out, sx, sy, ground, int(rng.integers(1 << 30)))
            count += 1
    return count


RING_STEP = 0.25             # degrees per segment of the horizon ring
SOUTH = (150.0, 255.0)       # bearings of Ellington Field and the houses: a tree line, not plants


def horizon_ring(mid, radius, base=-4.0):
    """The far horizon all round, a silhouette strip at `radius` (beyond the far land) like scenery.mountain_ring:
    plants, tanks and towers with flare tips to the north and east (the Ship Channel, Bayport), trees and roofs to
    the south. Its shape goes by world bearing (seeded per 1/4 degree), so every hole sees the same skyline. It
    reaches above the eye, hiding Blooper Bay's sea under the sky. Returns parts (faces point inwards)."""
    n = int(round(360 / RING_STEP))
    tops = np.empty(n)
    cols = np.empty((n, 3))
    k = 0
    rng = np.random.default_rng(4242)
    while k < n:   # blocks a few segments wide: a plant's mass, a tank, a tower, a stack
        bearing = k * RING_STEP
        south = SOUTH[0] <= bearing <= SOUTH[1]
        r = rng.uniform()
        if south:
            w, top, col = rng.integers(2, 8), rng.uniform(18, 30), (62, 88, 66)
        elif r < 0.12:                                   # a stack or a column
            w, top, col = 1, rng.uniform(95, 150), (100, 106, 116)
        elif r < 0.3:                                    # a process unit
            w, top, col = rng.integers(2, 5), rng.uniform(55, 90), (78, 86, 98)
        else:                                            # tanks and sheds
            w, top, col = rng.integers(3, 10), rng.uniform(32, 55), (88, 96, 108)
        tops[k:k + w] = top
        cols[k:k + w] = col
        k += w
    pts, tris, uv, rgb = [], [], [], []
    for i in range(n):
        a0, a1 = math.radians(i * RING_STEP), math.radians((i + 1) * RING_STEP)
        p0 = (mid[0] + math.sin(a0) * radius, mid[1] - math.cos(a0) * radius)   # bearing clockwise from north
        p1 = (mid[0] + math.sin(a1) * radius, mid[1] - math.cos(a1) * radius)
        k = len(pts)
        pts += [(p0[0], base, p0[1]), (p1[0], base, p1[1]), (p1[0], tops[i], p1[1]), (p0[0], tops[i], p0[1])]
        u0 = (i % 128) * 0.5    # (texcoords are s16/64: keep them small)
        u1 = u0 + 0.5
        uv += [(u0, 0), (u1, 0), (u1, -tops[i] / 40), (u0, -tops[i] / 40)]
        rgb += [tuple(int(v) for v in cols[i])] * 4
        tris += [(k, k + 2, k + 1), (k, k + 3, k + 2)]   # seen from inside the ring
        if tops[i] > 90 and not (SOUTH[0] <= i * RING_STEP <= SOUTH[1]) and rng.uniform() < 0.4:   # a flare
            m = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
            k = len(pts)
            pts += [(p0[0], tops[i], p0[1]), (p1[0], tops[i], p1[1]), (m[0], tops[i] + 14, m[1])]
            uv += [(0, 0), (0.5, 0), (0.25, -0.3)]
            rgb += [(255, 140, 40)] * 3
            tris += [(k, k + 2, k + 1)]
    return [("metal", 0, CODE, np.array(pts), tris, np.array(uv), rgb)]


def _pt(x, y):
    from shapely.geometry import Point
    return Point(x, y)


# ---------------------------------------------------------------- landmarks far off (v22)
LANDMARK_SHOWN = 2000.0       # m from the hole's middle: inside the far land (the camera sees 3.9 km)


def landmarks(out, mid, ground, places):
    """Landmarks past the camera's reach (Course.LANDMARKS: [(x, y, kind)] in the course frame) drawn LANDMARK_SHOWN
    from the hole's middle on their real bearing, scaled to fill the angle the real one does from there."""
    for x, y, kind in places:
        dx, dy = x - mid[0], y - mid[1]
        d = math.hypot(dx, dy)
        k = min(1.0, LANDMARK_SHOWN / d)
        sx, sy = mid[0] + dx * k, mid[1] + dy * k
        base = float(np.asarray(ground(np.array([sx]), np.array([sy])))[0])
        {"san_jacinto": san_jacinto}[kind](out, sx, sy, base, k)


def san_jacinto(out, x, y, base, k):
    """The San Jacinto Monument (La Porte, 173 m): terraces, a square shaft tapering from 14.6 m to 9 m, the
    observation floor and the Lone Star on top. k scales it."""
    stone, light = (214, 204, 178), (232, 224, 204)
    box(out, "siding", x, y, 40 * k, 40 * k, 0.0, base, 2 * k, stone)
    box(out, "siding", x, y, 25 * k, 25 * k, 0.0, base + 2 * k, 14 * k, stone)
    top = base + 158 * k
    cylinder(out, "siding", x, y, 14.6 / 2 * math.sqrt(2) * k, base + 16 * k, top - base - 16 * k, light, sides=4,
             top_r=9.0 / 2 * math.sqrt(2) * k, v_scale=12.0)
    box(out, "siding", x, y, 10.5 * k, 10.5 * k, math.pi / 4, top, 4.5 * k, stone)
    star_top = top + 4.5 * k
    r = 5.2 * k
    for ang in (0.0, math.pi / 2):            # two upright stars, crossed, seen from every side
        ca, sa = math.cos(ang), math.sin(ang)
        cx, ch = 0.0, star_top + r
        ring = [((r if i % 2 == 0 else r * 0.42) * math.sin(i * math.pi / 5),
                 (r if i % 2 == 0 else r * 0.42) * math.cos(i * math.pi / 5)) for i in range(10)]
        pts = [(x, ch, y)] + [(x + u * ca, ch + v, y + u * sa) for u, v in ring] +               [(x + ring[0][0] * ca, ch + ring[0][1], y + ring[0][0] * sa)]
        uv = [(0.0, 0.0)] * len(pts)
        out.face("metal", pts, uv, (235, 235, 230))
        out.face("metal", pts[:1] + pts[:0:-1], uv, (235, 235, 230))
