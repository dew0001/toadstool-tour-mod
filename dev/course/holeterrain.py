"""Terrain for one Pebble hole from real data: elevation (dem.py), surfaces (OSM via pebble.py), the sea.

Frame: metres, x east, y south (pebble.Course's), origin at the hole's tee (the start of the OSM hole line); heights in metres above
the sea. The playing corridor (the hole line buffered by DETAIL) gets a fine grid, the rest of the region (REGION)
a coarser one.

Surface codes (what is drawn and what the ball lands on):
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from shapely import contains_xy
from shapely.geometry import Point
from shapely.ops import unary_union

import coursesite
import dem

SEA, BEACH, ROCK, NATURAL, ROUGH, CUT, FAIRWAY, FRINGE, GREEN, BUNKER, TEE, PATH, ROAD, WATER, BUILDING = range(15)
# v12: another hole's fairway, fringe and green (they play as their own surface, marked so the game's auto-aim
# leaves them alone), and roads inside the course (in play, as cart path)
FAIRWAY_X, FRINGE_X, GREEN_X, PAVED = range(15, 19)
NAMES = ["sea", "beach", "rock", "natural", "rough", "first cut", "fairway", "fringe", "green", "bunker", "tee",
         "cart path", "road", "water", "building", "other fairway", "other fringe", "other green", "paved path"]
DETAIL = 110      # metres either side of the hole line: fine grid
REGION = 520      # metres: how far the hole's model reaches
FINE, COARSE = 2.5, 9.0
SEA_LEVEL = 0.0
SEABED = -3.0


class HoleTerrain:
    pass


def classify(course, xs, ys, n=None):
    """Surface code of world points (arrays), highest priority last. With hole n, the other holes' fairways and
    greens get the _X codes."""
    out = np.full(xs.shape, NATURAL, np.int8)
    inside_course = contains_xy(course.area.buffer(-2), xs, ys)
    out[inside_course] = ROUGH

    def split(kind):
        mine = [p for p, own in course.holes_of(kind) if n is None or n in own]
        other = [p for p, own in course.holes_of(kind) if n is not None and n not in own]
        return mine, other
    fairways, other_fairways = split("fairway")
    greens, other_greens = split("green")

    def paint(polys, code, grow=0.0):
        if not polys:
            return
        u = unary_union([p.buffer(grow) if grow else p for p in polys])
        hit = contains_xy(u, xs, ys)
        out[hit] = code

    k = course.kinds
    paint([p for p, t in k.get("rough", [])], CUT)
    paint([p for p, t in k.get("beach", [])], BEACH)
    paint([p for p, t in k.get("rock", [])], ROCK)
    paint([p for p, t in k.get("fairway", [])], CUT, 2.0)
    paint(other_fairways, FAIRWAY_X)
    paint(fairways, FAIRWAY)
    paint(other_greens, FRINGE_X, 1.5)
    paint(greens, FRINGE, 1.5)
    paint(other_greens, GREEN_X)
    paint(greens, GREEN)
    paint([p for p, t in k.get("tee", [])], TEE)
    paint([p for p, t in k.get("bunker", [])], BUNKER)
    paint([p for kind in course.WATER_KINDS for p, t in k.get(kind, [])], WATER)
    roads = [ls.buffer(3.0 if kind in ("residential", "unclassified", "tertiary", "secondary", "primary",
                                       "service") else 2.0) for ls, kind in course.roads]
    paint(roads, ROAD)
    out[(out == ROAD) & inside_course] = PAVED     # out of bounds only outside the course
    paint([ls.buffer(1.2) for ls in course.cartpaths], PATH)
    paint([p for p, t in k.get("building", [])], BUILDING)
    sea = ~contains_xy(course.land, xs, ys)
    out[sea] = SEA
    return out


def heights(course, xs, ys, codes):
    h = dem.fine().sample(xs, ys)
    h = np.where(codes == SEA, SEABED, np.maximum(h, 0.6))
    return h


def build(n, fine=FINE, coarse=COARSE):
    c = coursesite.Course() if not hasattr(build, "course") else build.course
    build.course = c
    line = c.hole(n)
    ox, oy = line.coords[0]
    corridor = line.buffer(DETAIL)
    region = line.buffer(REGION)
    minx, miny, maxx, maxy = region.bounds
    # fine grid points inside the corridor, coarse grid elsewhere in the region; triangulated together later
    gx = np.arange(np.floor(minx / fine) * fine, maxx + fine, fine)
    gy = np.arange(np.floor(miny / fine) * fine, maxy + fine, fine)
    FX, FY = np.meshgrid(gx, gy)
    t = HoleTerrain()
    t.n, t.origin, t.line = n, (ox, oy), line
    t.fine = (gx, gy)
    in_corr = contains_xy(corridor, FX, FY)
    in_reg = contains_xy(region, FX, FY)
    t.FX, t.FY, t.in_corr, t.in_reg = FX, FY, in_corr, in_reg
    codes = classify(c, FX, FY, n)
    t.codes = codes
    t.H = heights(c, FX, FY, codes)
    t.course = c
    return t


def preview(t, path):
    from PIL import Image
    pal = np.array([(30, 70, 150), (225, 210, 165), (110, 100, 90), (70, 105, 45), (75, 140, 50), (90, 160, 60),
                    (110, 190, 70), (120, 200, 90), (140, 220, 110), (240, 230, 190), (100, 180, 80),
                    (170, 165, 150), (120, 120, 120), (50, 110, 190), (200, 120, 100), (130, 180, 120),
                    (130, 190, 130), (150, 200, 140), (150, 150, 140)], np.float64)
    img = pal[t.codes]
    gy, gx = np.gradient(t.H, t.fine[1], t.fine[0])
    shade = np.clip(0.85 - 0.5 * (gx * 0.7 - gy * 0.7) / np.sqrt(1 + gx ** 2 + gy ** 2), 0.35, 1.25)
    img = img * shade[..., None]
    img[~t.in_reg] *= 0.35
    img[t.in_reg & ~t.in_corr] *= 0.8
    for x, y in t.course.trees:
        j = int((x - t.fine[0][0]) / (t.fine[0][1] - t.fine[0][0]))
        i = int((y - t.fine[1][0]) / (t.fine[1][1] - t.fine[1][0]))
        if 0 <= i < img.shape[0] and 0 <= j < img.shape[1]:
            img[max(i - 1, 0):i + 2, max(j - 1, 0):j + 2] = (20, 60, 20)
    xs, ys = t.line.xy
    from PIL import ImageDraw
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)[::-1])
    d = ImageDraw.Draw(im)
    H = img.shape[0]
    sx = 1 / (t.fine[0][1] - t.fine[0][0])
    pts = [((x - t.fine[0][0]) * sx, H - 1 - (y - t.fine[1][0]) * sx) for x, y in zip(xs, ys)]
    d.line(pts, fill=(255, 0, 0), width=2)
    im.save(path)


if __name__ == "__main__":
    os.makedirs("preview_real", exist_ok=True)
    for n in [int(a) for a in sys.argv[1:]] or range(1, 19):
        t = build(n)
        preview(t, f"preview_real/hole{n:02d}.png")
        cnt = np.bincount(t.codes[t.in_reg].ravel(), minlength=15)
        print(n, {NAMES[k]: int(v) for k, v in enumerate(cnt) if v}, "h", round(float(t.H[t.in_corr].min()), 1),
              round(float(t.H[t.in_corr].max()), 1))
