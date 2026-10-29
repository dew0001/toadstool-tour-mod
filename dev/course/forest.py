"""v22: the real woods round a hole, from the canopy heights (canopy.py), for courses whose Course.canopy is set
(Pasadena, Battleground, Timber Creek).

Near the hole line every tree is a prop: one of the game's Cheep Cheep Falls trees, with its collision, standing on
its real spot at its real height (holegen.place_props). A hole model shows at most about 300 prop instances (the
loader's draw list has 320 nodes; 772 hung the game), so the PROP_BUDGET trees nearest the line are props. Farther
out the canopy itself is a mesh, its top at the trees' height over the ground and walls down to the ground at its
edges, in a leafy texture of our own: the woods read as woods from the fairway without the props' cost (no
collision: a ball out there is lost in the trees anyway).
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import canopy  # noqa: E402
import osm  # noqa: E402

PROP_BUDGET = 280             # props of real trees per hole (plus the 4 tee markers)
GRID = 7.0                    # m: the canopy mesh's grid
REACH = 380.0                 # m from the hole line: the canopy mesh stops there (the far landscape takes over)
MIN_HEIGHT = 5.0              # m of canopy that counts as woods for the mesh
TOP_SINK = 0.88               # the mesh's top a little under the tallest crowns (it averages a cell)
# props by shape: (name, broad crown?) - the Cheep Cheep Falls trees (holegen.TREES has their sizes)
BUSH, BROAD, PINE, YOUNG = "mur_0203_tree", "has_0204_tree", "mur_0202_tree", "has_0201_tree"


def species(height, crown, rng):
    """A prop for a real tree: bushes under 6 m; tall narrow crowns are pines (loblolly), wide ones oaks (live oak,
    water oak: the windswept broad canopy), the rest young pines or oaks."""
    if height < 6:
        return BUSH
    ratio = crown / height
    if height >= 16 and ratio < 0.42:
        return PINE
    if ratio >= 0.5 or (height < 12 and rng.uniform() < 0.5):
        return BROAD
    return YOUNG if height < 13 else (PINE if rng.uniform() < 0.5 else BROAD)


def canopy_texture(seed=11):
    """Leaf clumps in greens, darker in the gaps (vertex colours shade the walls)."""
    s = 128
    rng = np.random.default_rng(seed)
    img = np.zeros((s, s, 3))
    img[:] = (38, 70, 34)
    yy, xx = np.mgrid[0:s, 0:s]
    for _ in range(140):
        cx, cy, r = rng.uniform(0, s), rng.uniform(0, s), rng.uniform(5, 13)
        tone = rng.uniform(0.75, 1.25)
        col = np.array((70, 118, 52)) * tone
        for dx in (-s, 0, s):          # wrap so the texture tiles
            for dy in (-s, 0, s):
                d = np.hypot(xx - cx - dx, yy - cy - dy) / r
                m = d < 1
                lit = np.clip(1.15 - 0.55 * d - 0.25 * (yy - cy - dy) / r, 0.55, 1.3)
                img[m] = col * lit[m, None]
    noise = rng.uniform(-14, 14, (s, s, 1))
    im = Image.fromarray(np.clip(img + noise, 0, 255).astype(np.uint8))
    return im.filter(ImageFilter.SMOOTH)


GENERATED = {"canopy": (canopy_texture, 128)}


class Heights:
    """Canopy height (m) at points of the course frame (x east, y south: pebble.Course mirrors y), lightly smoothed."""

    def __init__(self):
        from scipy import ndimage
        chm, self.x0, self.y0, self.px = canopy.load()
        self.h = ndimage.gaussian_filter(chm.astype(np.float32), 1.2)

    def __call__(self, x, y):
        lat, lon = osm.to_latlon(np.asarray(x, float), -np.asarray(y, float))
        mx = np.radians(lon) * 6378137.0
        my = np.log(np.tan(np.pi / 4 + np.radians(lat) / 2)) * 6378137.0
        col = np.clip(((mx - self.x0) / self.px).astype(int), 0, self.h.shape[1] - 1)
        row = np.clip(((self.y0 - my) / self.px).astype(int), 0, self.h.shape[0] - 1)
        return self.h[row, col]


_heights = None


def heights():
    global _heights
    if _heights is None:
        _heights = Heights()
    return _heights


def pick(c, line, region, clear, inside_land):
    """The props: [(x, y, height, crown)] of the PROP_BUDGET real trees nearest the hole line (in the region, on
    land, not in `clear`), and the distance from the line out to which the props stand."""
    from shapely import contains_xy
    a = np.asarray(c.canopy, float)
    if not len(a):
        return [], 0.0
    ok = contains_xy(region, a[:, 0], a[:, 1]) & ~contains_xy(clear, a[:, 0], a[:, 1])
    ok &= inside_land(a[:, 0], a[:, 1])
    a = a[ok]
    from shapely.geometry import Point
    d = np.array([line.distance(Point(x, y)) for x, y in a[:, :2]])
    order = np.argsort(d)[:PROP_BUDGET]
    return [tuple(map(float, a[k])) for k in order], (float(d[order[-1]]) if len(order) else 0.0)


def mesh(line, region, clear, ground, prop_reach, ox, oy):
    """The canopy beyond the props as parts for holegen.parts_arrays: [(texture, material, code, points (n,3) metres
    (x, height, y), tris, uv, rgb)]."""
    from shapely import contains_xy
    from shapely.geometry import Point
    H = heights()
    reach = line.buffer(REACH).intersection(region)
    minx, miny, maxx, maxy = reach.bounds
    xs = np.arange(minx, maxx + GRID, GRID)
    ys = np.arange(miny, maxy + GRID, GRID)
    X, Y = np.meshgrid(xs, ys)                    # corners
    cx, cy = X[:-1, :-1] + GRID / 2, Y[:-1, :-1] + GRID / 2
    hc = H(cx, cy)
    near_line = np.array([line.distance(Point(x, y)) for x, y in zip(cx.ravel(), cy.ravel())]).reshape(cx.shape)
    woods = (hc >= MIN_HEIGHT) & (near_line > prop_reach + GRID)
    woods &= contains_xy(reach, cx, cy) & ~contains_xy(clear, cx, cy)
    # lone cells look like boxes: keep cells with at least 2 wooded neighbours
    from scipy import ndimage
    nb = ndimage.convolve(woods.astype(int), np.array([[0, 1, 0], [1, 0, 1], [0, 1, 0]]), mode="constant")
    woods &= nb >= 2
    if not woods.any():
        return []
    top = H(X, Y) * TOP_SINK
    gnd = ground(X.ravel(), Y.ravel()).reshape(X.shape)
    rng = np.random.default_rng(int(abs(ox * 7 + oy * 13)) % 2 ** 31)
    pts, tris, uv, rgb = [], [], [], []
    index = {}

    def corner(i, j):
        k = (i, j)
        if k not in index:
            index[k] = len(pts)
            x, y = X[i, j], Y[i, j]
            hh = max(top[i, j], MIN_HEIGHT * 0.8)
            pts.append((x, gnd[i, j] + hh, y))
            uv.append((x / 8.0, y / 8.0))
            t = rng.uniform(0.85, 1.12)
            rgb.append(tuple(int(min(255, v * t)) for v in (150, 170, 140)))
        return index[k]
    for i, j in zip(*np.nonzero(woods)):
        a, b, cc, d = corner(i, j), corner(i, j + 1), corner(i + 1, j + 1), corner(i + 1, j)
        tris += [(a, cc, b), (a, d, cc)]
    # tops face the game's way (holegen: (p1 - p0) x (p2 - p0) points down for ground)
    T = np.asarray(tris, int)
    P = np.asarray(pts, float)
    nrm = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
    flip = nrm[:, 1] > 0
    T[flip] = T[flip][:, [0, 2, 1]]
    tris = [tuple(t) for t in T]
    # walls where a wooded cell meets an open one: from the top edge down to the ground
    rows, cols = woods.shape
    for i, j in zip(*np.nonzero(woods)):
        for di, dj, e0, e1 in ((-1, 0, (i, j), (i, j + 1)), (1, 0, (i + 1, j + 1), (i + 1, j)),
                               (0, -1, (i + 1, j), (i, j)), (0, 1, (i, j + 1), (i + 1, j + 1))):
            ni, nj = i + di, j + dj
            if 0 <= ni < rows and 0 <= nj < cols and woods[ni, nj]:
                continue
            t0, t1 = corner(*e0), corner(*e1)
            k0 = len(pts)
            for (ii, jj), tk in ((e0, t0), (e1, t1)):
                x, y = X[ii, jj], Y[ii, jj]
                pts.append((x, gnd[ii, jj] - 0.3, y))
                along = (x + y) / 8.0
                uv.append((along, 0.0))
                rgb.append((70, 82, 64))
            # the top corners again, with wall texture coordinates
            for (ii, jj), tk in ((e0, t0), (e1, t1)):
                x, y = X[ii, jj], Y[ii, jj]
                pts.append(pts[tk])
                uv.append(((x + y) / 8.0, (pts[tk][1] - gnd[ii, jj]) / 8.0))
                rgb.append((118, 132, 108))
            g0, g1, u0, u1 = k0, k0 + 1, k0 + 2, k0 + 3
            tris += [(u0, g1, g0), (u0, u1, g1), (u0, g0, g1), (u0, g1, u1)]   # both sides
    P = np.asarray(pts, float)
    T = np.asarray(tris, int)
    return [("canopy", 1, 0x00, P, T, np.asarray(uv, float), np.asarray(rgb, np.uint8))]
