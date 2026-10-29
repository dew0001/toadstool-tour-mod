"""Generate a hole of a real course for Toadstool Tour: hole model (+0), collision (+4), flyover camera (+C).

Real data: OSM shapes (pebble.py, pasadena.py: the course is TTMOD_COURSE, coursesite.py) on real elevation (dem.py).
Frame: metres east (x) and south (y) of the hole's tee (pebble.Course's frame); game units are 32 ft (UNIT_M metres):
game X = east, game Z = south, game Y = up.

python -I holegen.py <out folder> [hole numbers]   -> <out>/<disc folder>/<hole letter>/{A,B,C}
"""
import json
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import numpy as np
from scipy.spatial import Delaunay
from shapely import contains_xy, distance, points as shp_points
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

import collision as col
import dem
import holedata
import holeterrain as ht
import coursesite
import forest
import industry
import modlink
import scenery
import textures as tx

UNIT_M = 32 * 0.3048          # one game unit in metres
FT = 0.3048
POS_FRAC, TEX_FRAC = 7, 6     # model positions s16/128 units (+-256 = +-2.5 km), texcoords s16/64
DETAIL = 120                  # metres either side of the hole line: fine points
REGION = 560                  # metres: the model's terrain reaches this far from the hole line
COLL = 300                    # metres: collision terrain this far from the hole line
FINE, COARSE = 3.0, 10.0      # point spacing (m)
EDGE = 1.6                    # spacing of points along surface outlines (m)
TILE = 90.0                   # display-list tiles (m)
LIGHT = (-0.7071, -0.5934, -0.3851)

# textures: (source module, index in its terrain texture set)
TEX = {
    "fairway": ("A/Y/I", 10), "cut": ("A/Y/I", 3), "rough": ("A/Y/I", 1), "natural": ("A/Y/I", 0),
    "deep": ("A/Y/I", 2), "green": ("A/Y/I", 4), "fringe": ("A/Y/I", 5), "sand": ("A/Y/I", 11),
    "dirt": ("A/Y/I", 12), "rock": ("B/G/S", 43), "beach": ("B/G/S", 9), "sea": ("B/G/S", 0),
    "foam": ("B/G/S", 1),
    "wall": ("gen", "wall"), "lodge": ("gen", "lodge"), "roof": ("gen", "roof"), "asphalt": ("gen", "asphalt"),
}
if getattr(coursesite.Course, "INDUSTRY", False):   # Pasadena's tanks, sheds and refineries (industry.py)
    TEX.update({name: ("gen", name) for name in industry.GENERATED})
    scenery.GENERATED.update(industry.GENERATED)
if getattr(coursesite.Course, "CANOPY", False):   # v22: the woods' canopy mesh (forest.py)
    TEX["canopy"] = ("gen", "canopy")
    scenery.GENERATED.update(forest.GENERATED)
TEX_ORDER = list(TEX)
# v22: the disc's free area (between the file table and the first game file, 272 MB) holds every new file; four
# courses at 512x512 terrain textures in every hole didn't fit. On the courses with canopy trees (built from v22) these
# go in at half size (their 512x512 level left out: about 3 cm a texel at the game's 8 m repeat); greens and fringes,
# seen close while putting, keep theirs. 1.2 MB less a hole.
HALF_TEXTURES = ({"fairway", "cut", "rough", "natural", "deep", "sand", "rock", "beach", "sea"}
                 if getattr(coursesite.Course, "CANOPY", False) else set())
MATS = [(1.0, 1.0), (0.5, 0.5), (0.25, 0.25), (2.0, 2.0)]   # texcoord unit = 4 m: tile 4 m, 8 m, 16 m, 2 m
# surface -> (texture, material, game surface code, zone)
SURF = {
    ht.SEA: ("sea", 2, 0x18, col.ZONE_HAZARD), ht.BEACH: ("beach", 1, 0x24, col.ZONE_HAZARD),
    ht.ROCK: ("rock", 1, 0x09, col.ZONE_HAZARD), ht.NATURAL: ("natural", 1, 0x16, col.ZONE_OB),
    ht.ROUGH: ("rough", 1, 0x04, 0), ht.CUT: ("cut", 1, 0x0A, 0), ht.FAIRWAY: ("fairway", 1, 0x01, 0),
    ht.FRINGE: ("fringe", 0, 0x0B, 0), ht.GREEN: ("green", 0, 0x02, 0), ht.BUNKER: ("sand", 0, 0x03, 0),
    ht.TEE: ("fringe", 0, 0x08, 0), ht.PATH: ("dirt", 0, 0x07, 0), ht.ROAD: ("asphalt", 1, 0x06, col.ZONE_OB),
    ht.WATER: ("sea", 0, 0x05, col.ZONE_HAZARD), ht.BUILDING: ("dirt", 1, 0x06, col.ZONE_OB),
    ht.FAIRWAY_X: ("fairway", 1, 0x01, 0), ht.FRINGE_X: ("fringe", 0, 0x0B, 0), ht.GREEN_X: ("green", 0, 0x02, 0),
    ht.PAVED: ("asphalt", 1, 0x07, 0),
}
OTHER_HOLE = (ht.FAIRWAY_X, ht.FRINGE_X, ht.GREEN_X)   # collision: col.ATTR_OTHER_HOLE (the auto-aim skips them)
CLIFF = 99   # pseudo-surface for steep triangles


# ---------------------------------------------------------------- points and triangles

def ring_points(geom, spacing):
    out = []
    polys = [geom] if geom.geom_type == "Polygon" else list(getattr(geom, "geoms", []))
    for p in polys:
        if p.is_empty or p.geom_type != "Polygon":
            continue
        for ring in [p.exterior] + list(p.interiors):
            n = max(int(ring.length / spacing), 4)
            out += [ring.interpolate(i / n, normalized=True).coords[0] for i in range(n)]
    return out


def line_points(line, spacing):
    n = max(int(line.length / spacing), 2)
    return [line.interpolate(i / n, normalized=True).coords[0] for i in range(n + 1)]


def dedupe(pts, min_dist, keep_first):
    """Drop points closer than min_dist to an earlier kept point (the first keep_first points always stay)."""
    pts = np.asarray(pts)
    cell = {}
    kept = []
    for i, (x, y) in enumerate(pts):
        k = (int(x // min_dist), int(y // min_dist))
        clash = False
        if i >= keep_first:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for j in cell.get((k[0] + dx, k[1] + dy), ()):
                        if (pts[j][0] - x) ** 2 + (pts[j][1] - y) ** 2 < min_dist ** 2:
                            clash = True
                            break
        if not clash:
            cell.setdefault(k, []).append(i)
            kept.append(i)
    return pts[kept]


def make_points(c, line):
    corridor = line.buffer(DETAIL)
    region = line.buffer(REGION)
    minx, miny, maxx, maxy = region.bounds
    outline = []
    near = line.buffer(DETAIL + 40)
    for kind in ("green", "tee", "bunker", "fairway", "rough", "beach", "rock") + c.WATER_KINDS:
        for p, t in c.kinds.get(kind, []):
            if p.intersects(region):
                g = p.intersection(region)
                outline += ring_points(g, EDGE if g.intersects(near) else 4.0)
                if kind == "green":
                    outline += ring_points(g.buffer(1.5), EDGE)
    for p, t in c.kinds.get("building", []):
        if p.intersects(region):
            outline += ring_points(p, 2.5)
    for ls in c.cartpaths:
        if ls.intersects(near):
            outline += ring_points(ls.buffer(1.2).intersection(region), EDGE)
    coast = c.land.boundary.intersection(region.buffer(50))
    for seg in getattr(coast, "geoms", [coast]):
        if seg.is_empty:
            continue
        pts = line_points(seg, 2.0)
        outline += pts
    # cliff tops and the sea just off the coast
    land_in = c.land.buffer(-3.0).boundary.intersection(region)
    for seg in getattr(land_in, "geoms", [land_in]):
        if not seg.is_empty and seg.length > 1:
            outline += line_points(seg, 2.5)
    for off, step in ((5.0, 4.0), (12.0, 5.0), (25.0, 7.0)):    # the sea's colour and depth ramps
        sea_out = c.land.buffer(off).boundary.intersection(region)
        for seg in getattr(sea_out, "geoms", [sea_out]):
            if not seg.is_empty and seg.length > 1:
                outline += line_points(seg, step)
    gx = np.arange(np.floor(minx / FINE) * FINE, maxx + FINE, FINE)
    gy = np.arange(np.floor(miny / FINE) * FINE, maxy + FINE, FINE)
    FX, FY = np.meshgrid(gx, gy)
    fine = np.stack([FX.ravel(), FY.ravel()], 1)
    fine = fine[contains_xy(corridor, fine[:, 0], fine[:, 1])]
    cx = np.arange(np.floor(minx / COARSE) * COARSE, maxx + COARSE, COARSE)
    cy = np.arange(np.floor(miny / COARSE) * COARSE, maxy + COARSE, COARSE)
    CX, CY = np.meshgrid(cx, cy)
    coarse = np.stack([CX.ravel(), CY.ravel()], 1)
    coarse = coarse[contains_xy(region.difference(corridor.buffer(FINE)), coarse[:, 0], coarse[:, 1])]
    # the region's own edge
    edge = line_points(region.exterior, COARSE)
    outline = [p for p in outline if region.contains(Point(p))]
    pts = np.concatenate([np.asarray(outline).reshape(-1, 2), np.asarray(edge), fine, coarse])
    pts = dedupe(pts, 0.9, 0)
    return pts, region


# ---------------------------------------------------------------- heights

def heights(c, pts, codes_v):
    d = dem.fine()
    h = d.sample(pts[:, 0], pts[:, 1])
    land = contains_xy(c.land, pts[:, 0], pts[:, 1])
    # cliff tops: near the coast take the highest ground within 9 m (the DEM blurs the cliff edge)
    near_coast = distance(c.land.boundary, shp_points(pts)) < 12
    beachy = unary_union([p for p, t in c.kinds.get("beach", [])] or [Polygon()]).buffer(15)
    flat_coast = contains_xy(beachy, pts[:, 0], pts[:, 1])
    idx = np.where(land & near_coast & ~flat_coast)[0]
    if len(idx):
        best = h[idx].copy()
        for ang in np.linspace(0, 2 * np.pi, 12, endpoint=False):
            for r in (4.0, 8.0):
                qx, qy = pts[idx, 0] + r * np.cos(ang), pts[idx, 1] + r * np.sin(ang)
                inland = contains_xy(c.land, qx, qy)
                best = np.where(inland, np.maximum(best, d.sample(qx, qy)), best)
        h[idx] = best
    on_coast = distance(c.land.boundary, shp_points(pts)) < 0.3
    h = np.where(land, np.maximum(h, 0.8), 0.0)
    h[on_coast] = 0.2
    # bunkers sunk 0.6 m with a soft edge, tees flattened
    for p, t in c.kinds.get("bunker", []):
        inside = contains_xy(p, pts[:, 0], pts[:, 1])
        if inside.any():
            dd = distance(p.boundary, shp_points(pts[inside]))
            h[inside] -= 0.6 * np.clip(dd / 1.5, 0, 1)
    for p, t in c.kinds.get("tee", []):
        inside = contains_xy(p, pts[:, 0], pts[:, 1])
        if inside.sum() >= 3:
            h[inside] = h[inside].mean() + 0.25
    return h


# ---------------------------------------------------------------- textures

def texture_set(names):
    """Merged texture set (headers + data) from the source modules' terrain sets; returns bytes."""
    entries = []
    for name in names:
        rel, idx = TEX[name]
        if rel == "gen":
            make, size = scenery.GENERATED[idx]
            data, levels = scenery.cmpr_texture(make(), size)
            hdr = bytearray(struct.pack('>9I', size << 16 | size, 14, 0, 1, 1, 5, 1, 0, (levels - 1) << 8))
            entries.append((hdr, data))
            continue
        src = SOURCES.setdefault(rel, modlink.Source(rel))
        ts = src.ptr[src.stub(0x8) + 0x8C]
        ho, w, h, f, d, lod = tx.headers(src.blob, ts)[idx]
        hdr = bytearray(src.blob[ho:ho + 0x24])
        if name in HALF_TEXTURES and lod >= 1 and w >= 512:   # leave the top level out
            d += max(tx.level_size(w, h, f), 32)
            w, h, lod = w // 2, h // 2, lod - 1
            struct.pack_into('>I', hdr, 0, h << 16 | w)
            struct.pack_into('>I', hdr, 0x20, (struct.unpack_from('>I', hdr, 0x20)[0] & ~0xFF00) | lod << 8)
        size, lw, lh = 0, w, h
        for _ in range(lod + 1):
            size += max(tx.level_size(lw, lh, f), 32)
            lw, lh = max(lw // 2, 1), max(lh // 2, 1)
        entries.append((hdr, bytes(src.blob[ts + d:ts + d + size])))
        TEX_PROV.append((rel, ts + d, size))
    n = len(entries)
    head = 0xC + 8 * n
    head = (head + 31) & ~31
    out = bytearray(struct.pack('>3I', modlink.TEXSET_MAGIC, n, 0xC)) + bytes(8 * n)
    out += bytes(head - len(out))
    hdr_at = []
    for hdr, data in entries:
        hdr_at.append(len(out))
        out += hdr
    out += bytes((-len(out)) % 32)
    data_at = []
    for i, (hdr, data) in enumerate(entries):
        struct.pack_into('>I', out, 0xC + 8 * i, hdr_at[i])
        struct.pack_into('>I', out, hdr_at[i] + 8, len(out))
        data_at.append(len(out))
        out += data
        out += bytes((-len(out)) % 32)
    texture_set.data_at = data_at
    return bytes(out)


TEX_PROV = []


SOURCES = {}


# ---------------------------------------------------------------- display lists

def strip_dl(tris, vertex):
    import shyguy
    return shyguy.display_list([tuple(int(v) for v in t) for t in tris], vertex)


# ---------------------------------------------------------------- the hole

class Hole:
    pass


def build(n, out_dir):
    c = build.course = getattr(build, "course", None) or coursesite.Course()
    line = c.hole(n)
    ox, oy = line.coords[0]
    pts, region = make_points(c, line)
    tri = Delaunay(pts)
    T = tri.simplices
    cen = pts[T].mean(1)
    keep = contains_xy(region, cen[:, 0], cen[:, 1])
    T = T[keep]
    cen = cen[keep]
    codes_t = ht.classify(c, cen[:, 0], cen[:, 1], n)
    codes_v = ht.classify(c, pts[:, 0], pts[:, 1], n)
    h = heights(c, pts, codes_v)
    # orientation: (p1 - p0) x (p2 - p0) must point down in the game's axes (x, h, y)
    P3 = np.stack([pts[:, 0], h, pts[:, 1]], 1)
    a, b, cc = P3[T[:, 0]], P3[T[:, 1]], P3[T[:, 2]]
    nrm = np.cross(b - a, cc - a)
    flip = nrm[:, 1] > 0
    T[flip] = T[flip][:, [0, 2, 1]]
    a, b, cc = P3[T[:, 0]], P3[T[:, 1]], P3[T[:, 2]]
    nrm = -np.cross(b - a, cc - a)          # upward face normals
    nlen = np.linalg.norm(nrm, axis=1, keepdims=True)
    nrm = nrm / np.maximum(nlen, 1e-9)
    steep = (nrm[:, 1] < 0.55) & (codes_t != ht.SEA) & (codes_t != ht.BUILDING)
    surf_t = codes_t.astype(np.int16)
    surf_t[steep] = CLIFF
    # vertex shading
    vn = np.zeros_like(P3)
    for k in range(3):
        np.add.at(vn, T[:, k], nrm * nlen)
    vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-9)
    L = -np.array(LIGHT)
    lit = np.clip(vn @ L, 0, 1)
    shade = 0.62 + 0.42 * lit
    rng = np.random.default_rng(n)
    shade *= 1 + rng.normal(0, 0.025, len(shade))
    # mowing stripes across the fairways, 9 m wide, square to the hole
    d_hole = np.array(line.coords[-1]) - np.array(line.coords[0])
    d_hole /= np.linalg.norm(d_hole)
    stripe = np.floor(((pts - np.array([ox, oy])) @ d_hole) / 9.0) % 2
    mown = np.isin(codes_v, (ht.FAIRWAY, ht.FAIRWAY_X, ht.TEE))
    shade *= np.where(mown, np.where(stripe == 0, 1.06, 0.94), 1.0)
    cliff_v = np.unique(T[steep].ravel())    # sea cliffs and banks: dark rock
    shade[cliff_v] *= 0.68
    tone = {ht.ROUGH: 0.86, ht.CUT: 0.93, ht.NATURAL: 0.74, ht.ROAD: 0.9, ht.PAVED: 0.9, ht.BUILDING: 0.8}
    for k_, f_ in tone.items():
        shade[codes_v == k_] *= f_
    cval = np.clip(128 * shade, 40, 220).astype(np.uint8)
    colours = np.stack([cval, cval, cval, np.full_like(cval, 255)], 1)
    # game-space vertices (units), relative to the tee
    G = np.stack([(pts[:, 0] - ox) / UNIT_M, h / UNIT_M, (pts[:, 1] - oy) / UNIT_M], 1)
    uv = np.stack([(pts[:, 0] - ox) / 4.0, -(pts[:, 1] - oy) / 4.0], 1)

    # ----- tees and pins
    tees = c.tees_of(n) + [Point(ox, oy).buffer(2)]    # the OSM hole line starts on the back tee
    green = c.green_of(n)
    gc = green.centroid
    yards, back_yards, par = coursesite.CARD[n]
    along = lambda p: p.centroid.distance(gc) / 0.9144     # tee to the middle of the green, yards
    regular = min(tees, key=lambda p: abs(along(p) - yards)).centroid
    back = min(tees, key=lambda p: abs(along(p) - back_yards) - 0.01 * along(p)).centroid

    # ----- scenery: houses, the far landscape and sea, the mountains
    rng2 = np.random.default_rng(77 + n)
    extra = []      # (texture, material, surface code, points (k,3) metres as (x, h, y), tris, uv, rgb)
    lodge_pt = Point(*c.LODGE) if c.LODGE else None   # Pebble's Lodge
    houses_coll = []
    house_parts = []
    mid = np.array(line.interpolate(0.5, normalized=True).coords[0])
    industrial = getattr(c, "INDUSTRY", False)
    fine_ground = lambda x, y: dem.fine().sample(x, y)
    if industrial:   # storage tanks (OSM circles) as tanks, hangars and industrial buildings as metal sheds
        for poly in c.tanks:
            if poly.intersects(region):
                one = industry.Parts(mid)
                industry.osm_tank(one, poly, fine_ground, rng2)
                for part in one.parts():
                    house_parts.append(part)
                    if line.distance(poly) < COLL:
                        houses_coll.append((part[3], part[4], line.distance(poly)))
    for poly, tags in c.kinds.get("building", []):
        if industrial and tags.get("man_made") == "storage_tank":
            continue
        shed = industrial and (tags.get("building") in ("hangar", "industrial", "warehouse")
                               or c.industrial.contains(poly.centroid))
        if not poly.intersects(region) or poly.area > (30000 if shed else 6000):
            continue
        if shed:
            one = industry.Parts(mid)
            industry.osm_shed(one, poly, fine_ground, rng2, tags.get("building") == "hangar")
            for part in one.parts():
                house_parts.append(part)
                if line.distance(poly) < COLL:
                    houses_coll.append((part[3], part[4], line.distance(poly)))
            continue
        lodge = lodge_pt is not None and poly.distance(lodge_pt) < 90 and poly.area > 400
        for kind, (P, tris_, uv_, rgb) in scenery.house_mesh(poly, lambda x, y: dem.fine().sample(x, y), rng2,
                                                             lodge).items():
            house_parts.append((kind, 3 if kind == "roof" else 0, 0x06, P, tris_, uv_, rgb))
            if line.distance(poly) < COLL:
                houses_coll.append((P, tris_, line.distance(poly)))
    far_parts = far_landscape(c, region, pts, h, mid)
    if industrial:   # refineries on the horizon
        sky = industry.Parts(mid)
        sites = industry.skyline(sky, mid, lambda x, y: np.maximum(scenery.elevation(x, y), 0.8), c.area, line)
        industry.landmarks(sky, mid, lambda x, y: np.maximum(scenery.elevation(x, y), 0.8), getattr(c, "LANDMARKS", ()))
        far_parts += sky.parts() + industry.horizon_ring(mid, scenery.RING_NEAR)
        print("refineries", sites)
    for d0, d1, radius, colour in () if industrial else ((scenery.FAR, 9000, scenery.RING_NEAR, (70, 95, 62)),
                                                         (9000, 40000, scenery.RING_FAR, (120, 140, 160))):
        prof = scenery.horizon(mid, 15.0, d0, d1)
        P, tris_, uv_, rgb = scenery.mountain_ring(mid, radius, prof, colour)
        if tris_:
            far_parts.append(("natural", 2, 0x00, P, tris_, uv_, rgb))
    for name, parts in (("houses", house_parts), ("far", far_parts)):
        print(name, sum(len(p[3]) for p in parts), "vertices")

    # ----- model module
    L_ = modlink.Linker()
    texnames = TEX_ORDER
    TEX_PROV.clear()
    texset = L_.alloc(texture_set(texnames))
    k_ = 0
    for name, at in zip(texnames, texture_set.data_at):
        if TEX[name][0] != "gen":
            rel_, off_, size_ = TEX_PROV[k_]
            L_.prov.append((rel_, off_, texset + at, size_))
            k_ += 1
    groups = [(SURF_TEX(k), T[surf_t == k]) for k in sorted(set(surf_t.tolist())) if k != ht.SEA]
    root = model_root(L_, texnames, texset, G, uv, colours, groups)
    own_models = []    # (name, root) prop models of our own, one identity instance each
    for name, parts in (("pb_houses", house_parts), ("pb_far", far_parts)):
        arr = parts_arrays(parts, ox, oy)
        if arr:
            own_models.append((name, model_root(L_, texnames, texset, arr[0], arr[1], arr[2], arr[3],
                                                POS_FRAC if name != "pb_far" else POS_FRAC - 1)))
    sea = sea_parts(c, pts, T[surf_t == ht.SEA]) + surf_foam(c, region)
    arr = parts_arrays(sea, ox, oy)
    if arr:     # its own model (vertex budget)
        own_models.append(("pb_sea", model_root(L_, texnames, texset, arr[0], arr[1], arr[2], arr[3])))
    props = place_props(c, line, region, pts, h, tri, n, regular, back, gc)
    print("props", [(nm, len(ii)) for nm, sr, ii in props], "out to", round(place_props.reach), "m")
    if c.canopy is not None:    # v22: the woods beyond the props (forest.py), in pieces under 16-bit indices
        fparts = forest.mesh(line, region, place_props.clear, scenery.elevation, place_props.reach, ox, oy)
        for k, part in enumerate(split_part(p_) for p_ in fparts):
            for j, piece in enumerate(part):
                arr = parts_arrays([piece], ox, oy)
                own_models.append((f"pb_forest{k}{j}", model_root(L_, texnames, texset, arr[0], arr[1], arr[2],
                                                                  arr[3])))
                print("forest", len(arr[0]), "vertices", len(piece[4]), "triangles")
    if os.environ.get("ONLY_PROPS"):
        props = [p for p in props if p[0] in os.environ["ONLY_PROPS"].split(",")]
    objects = L_.alloc(bytes(0x10 * (len(props) + len(own_models))), 32)
    for k, (name, r_) in enumerate(own_models, start=len(props)):
        L_.ptr(objects + 0x10 * k, r_)
        struct.pack_into('>I', L_.blob, objects + 0x10 * k + 4, 1)
        L_.ptr(objects + 0x10 * k + 8, L_.alloc(inst_bytes(IDENTITY), 4))
        L_.ptr(objects + 0x10 * k + 12, L_.alloc(name.encode() + bytes(1), 4))
    for k, (name, src_rel, insts) in enumerate(props):
        src = SOURCES.setdefault(src_rel, modlink.Source(src_rel))
        o = src_object(src, name)
        L_.ptr(objects + 0x10 * k, L_.import_(src, src.ptr[o]))
        struct.pack_into('>I', L_.blob, objects + 0x10 * k + 4, len(insts))
        arr = L_.alloc(b"".join(inst_bytes(i) for i in insts), 4)
        L_.ptr(objects + 0x10 * k + 8, arr)
        L_.ptr(objects + 0x10 * k + 12, L_.alloc(name.encode() + b"\0", 4))
    model = L_.finish(root, len(props) + len(own_models), objects)

    # ----- collision: the terrain near the hole
    coll_reach = COLL
    while True:   # at most 65535 triangles in a collision mesh: shrink the reach until it fits
        near = line.buffer(coll_reach)
        cmask = contains_xy(near, cen[:, 0], cen[:, 1])
        used = np.unique(T[cmask].ravel())
        remap = -np.ones(len(pts), int)
        remap[used] = np.arange(len(used))
        faces = []
        in_course = contains_xy(c.area, cen[cmask][:, 0], cen[cmask][:, 1])
        for t_, s_, inc in zip(T[cmask], surf_t[cmask], in_course):
            if s_ == CLIFF:   # banks inside the course play as rock; the sea cliffs are a penalty area
                at = col.attr(0x09, 0 if inc else col.ZONE_HAZARD)
            else:
                texname, mat, code, zone = SURF[int(s_)]
                at = col.attr(code, zone) | (col.ATTR_OTHER_HOLE if s_ in OTHER_HOLE else 0)
            faces.append((int(remap[t_[0]]), int(remap[t_[1]]), int(remap[t_[2]]), at))
        cpts = [tuple(p) for p in G[used]]
        for P, tris_, dist_ in houses_coll:
            if dist_ > coll_reach:
                continue
            k0 = len(cpts)
            cpts += [((x - ox) / UNIT_M, hh / UNIT_M, (y - oy) / UNIT_M) for x, hh, y in P]
            faces += [(k0 + a_, k0 + b_, k0 + c_, col.attr(0x06, col.ZONE_OB)) for a_, b_, c_ in tris_]
        if len(faces) <= 64000 and len(cpts) <= 65000:
            break
        coll_reach -= 25
    cmesh = col.make_mesh(cpts, faces)

    toward = np.array([regular.x - gc.x, regular.y - gc.y])
    toward /= np.linalg.norm(toward) or 1
    side = np.array([-toward[1], toward[0]])
    r = math.sqrt(green.area / math.pi)
    pins = []
    for off in (toward * 0.45, -toward * 0.45, side * 0.4, -side * 0.4):
        p = np.array([gc.x, gc.y]) + off * r
        if not green.contains(Point(p)):
            p = np.array([gc.x, gc.y]) + off * r * 0.4
        pins.append(p)

    def ground_ft(x, y):
        hh = dem.fine().sample(np.array([x]), np.array([y]))[0]
        gx_, gz_ = (x - ox) / UNIT_M, (y - oy) / UNIT_M
        gy_ = col.ground(cmesh, gx_, gz_)
        y_units = gy_[0] if gy_ else hh / UNIT_M
        return (gx_ * 32, y_units * 32, gz_ * 32)
    tee_ft = [ground_ft(regular.x, regular.y), ground_ft(back.x, back.y)]
    pin_ft = [ground_ft(*p) for p in pins]
    layout = col.make_layout(tee_ft, pin_ft, LIGHT)
    cprops = []
    for name, src_rel, insts in props:
        cm = collision_prop(name)
        near_insts = [i for i in insts if line.distance(Point(ox + i["pos"][0] * UNIT_M, oy + i["pos"][2] * UNIT_M)) < coll_reach]
        if cm is not None and near_insts and not os.environ.get("NO_COLL_PROPS"):
            for k in range(0, len(near_insts), 256):   # at most 256 instances an object
                cprops.append((name, cm, near_insts[k:k + 256]))
    coll = col.make_collision(cmesh, cprops, layout)
    blob, relocs = col.build(coll)

    # ----- flyover
    cam = flyover(G, pts, line, ox, oy, h, tee_ft, pin_ft)
    cam_packed = holedata.pack_camera(cam)

    yards = int(round(math.dist(tee_ft[0][::2], pin_ft[0][::2]) / 3))
    back_yards = int(round(math.dist(tee_ft[1][::2], pin_ft[0][::2]) / 3))
    letter = chr(65 + n - 1)
    d = os.path.join(out_dir, coursesite.DISC, letter)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "A"), "wb").write(model)
    json.dump({"copies": [["files/" + r, so, do, ln] for r, so, do, ln in L_.prov]},
              open(os.path.join(d, "A.prov.json"), "w"))
    col.save_packed(os.path.join(d, "B"), blob, relocs)
    open(os.path.join(d, "C"), "wb").write(cam_packed)
    top = coursesite.DISC
    info = {"hole": n, "par": coursesite.CARD[n][2], "yards": yards, "back": back_yards,
            "model": f"{top}/{letter}/A", "collision": f"{top}/{letter}/B", "flyover": f"{top}/{letter}/C",
            "points": len(pts), "triangles": len(T), "collision_triangles": len(faces),
            "model_bytes": len(L_.blob), "tees_ft": tee_ft, "pins_ft": pin_ft}
    print(json.dumps({k: v for k, v in info.items() if k not in ("tees_ft", "pins_ft")}))
    return info


# ---------------------------------------------------------------- props (trees, tee markers)

PROP_SRC = "A/Y/I"            # Cheep Cheep Falls hole 201: its trees and tee markers (collision in A/Y/J)
PROP_COLL = "A/Y/J"
TREES = {                     # name -> (model height in its units, wanted height range in metres)
    "has_0204_tree": (None, (11, 18)),    # broad, windswept canopy: Monterey cypress
    "mur_0202_tree": (None, (18, 27)),    # tall pine: Monterey pine
    "has_0201_tree": (None, (9, 15)),     # young pines
    "mur_0203_tree": (None, (2.5, 4.5)),  # bushes
}
TEE_MARKER = "mur_0201_tee"
MAX_INSTANCES = 75


def src_object(src, name):
    objs, n = src.stub(0x10), src.stub(0xC)
    for k in range(n):
        o = objs + 0x10 * k
        p = src.ptr[o + 12]
        if src.blob[p:src.blob.index(b"\0", p)].decode() == name:
            return o
    raise KeyError(name)


_coll_cache = {}


def collision_prop(name):
    if PROP_COLL not in _coll_cache:
        _coll_cache[PROP_COLL] = col.parse(*col.load(PROP_COLL))
    for obj in _coll_cache[PROP_COLL]["objects"]:
        if obj["name"] == name:
            return obj["mesh"]
    return None


def prop_height(name):
    m = collision_prop(name)
    lo, hi = m["bbox"][1], m["bbox"][4]
    return hi - lo            # collision units (the bbox of a 0x0131A313 mesh is in game units)


def prop_half_width(name):
    m = collision_prop(name)
    return max(m["bbox"][3] - m["bbox"][0], m["bbox"][5] - m["bbox"][2]) / 2


def inst(pos_units, scale, yaw, wide=None):
    """An instance: uniform scale, or `wide` across and `scale` up."""
    hh = math.radians(yaw) / 2
    sx = float(scale if wide is None else wide)
    return {"flags": 7, "pos": [float(v) for v in pos_units], "scale": [sx, float(scale), sx],
            "quat": [0.0, math.sin(hh), 0.0, math.cos(hh)]}


def inst_bytes(i):
    return struct.pack('>I10f', i["flags"], *i["pos"], *i["scale"], *i["quat"])


def place_props(c, line, region, pts, h, tri, n, regular, back, gc):
    from scipy.interpolate import LinearNDInterpolator
    ground = LinearNDInterpolator(tri, h)
    ox, oy = line.coords[0]
    rng = np.random.default_rng(1000 + n)
    buildings = unary_union([p for p, t in c.kinds.get("building", []) if p.intersects(region)] or [Polygon()])
    roads = unary_union([ls.buffer(4) for ls, k in c.roads if ls.intersects(region)] or [Polygon()])
    playing = unary_union([p for k in ("fairway", "green", "tee", "bunker") for p, t in c.kinds.get(k, [])
                           if p.intersects(region)] or [Polygon()]).buffer(8)
    keep_out = unary_union([buildings.buffer(3), roads, playing])
    heights = {name: prop_height(name) for name in TREES}
    out = {name: [] for name in TREES}
    place_props.reach = 0.0
    if c.canopy is not None:   # v22: the real trees (forest.py), nearest the hole line first
        clear = unary_union([buildings.buffer(2), roads] +
                            [p.buffer(0 if k == "fairway" else 1.5) for k in ("fairway", "green", "tee", "bunker")
                             for p, t in c.kinds.get(k, []) if p.intersects(region)] +
                            [p for k in c.WATER_KINDS for p, t in c.kinds.get(k, []) if p.intersects(region)]
                            or [Polygon()])
        chosen, place_props.reach = forest.pick(c, line, region, clear, lambda xs, ys: contains_xy(c.land, xs, ys))
        place_props.clear = clear
        for x, y, tall, crown in chosen:
            name = forest.species(tall, crown, rng)
            gy_ = ground(x, y)
            if not np.isfinite(gy_):
                continue
            up = tall / UNIT_M / heights[name]
            across = min(max(crown / UNIT_M / prop_half_width(name), 0.7 * up), 1.5 * up)
            out[name].append(inst(((x - ox) / UNIT_M, float(gy_) / UNIT_M - 0.02, (y - oy) / UNIT_M), up,
                                  rng.uniform(0, 360), across))
        spots = []
    else:
        spots = None
    coast_d = lambda x, y: c.land.boundary.distance(Point(x, y))
    for x, y, why in place_old_spots(c, line, region, rng, playing, keep_out) if spots is None else ():
        near_sea = coast_d(x, y) < 160
        r = rng.uniform()
        if r < 0.12:
            name = "mur_0203_tree"
        elif near_sea:
            name = "has_0204_tree" if r < 0.8 else "mur_0202_tree"
        else:
            name = "mur_0202_tree" if r < 0.55 else ("has_0204_tree" if r < 0.85 else "has_0201_tree")
        if len(out[name]) >= MAX_INSTANCES:
            continue
        gy_ = ground(x, y)
        if not np.isfinite(gy_):
            continue
        lo, hi = TREES[name][1]
        want = rng.uniform(lo, hi) / UNIT_M
        out[name].append(inst(((x - ox) / UNIT_M, float(gy_) / UNIT_M - 0.02, (y - oy) / UNIT_M),
                              want / heights[name], rng.uniform(0, 360)))
    props = [(name, PROP_SRC, insts) for name, insts in out.items() if insts]
    # tee markers: a pair on each tee, across the line to the green
    marks = []
    for t in (regular, back):
        d = np.array([gc.x - t.x, gc.y - t.y])
        d /= np.linalg.norm(d) or 1
        side = np.array([d[1], -d[0]])
        yaw = math.degrees(math.atan2(d[0], d[1]))
        for s_ in (-1, 1):
            x, y = t.x + side[0] * s_ * 2.4, t.y + side[1] * s_ * 2.4
            gy_ = ground(x, y)
            marks.append(inst(((x - ox) / UNIT_M, float(gy_) / UNIT_M, (y - oy) / UNIT_M), 0.2, yaw + 180))
    props.append((TEE_MARKER, PROP_SRC, marks))
    return props


def split_part(part, limit=60000):
    """A part with too many vertices for one model root (16-bit indices) -> parts, cut by x."""
    texname, mat, code, P, T, uv, rgb = part[:7]
    P, T = np.asarray(P), np.asarray(T)
    if len(P) <= limit:
        return [part]
    cx = P[T].mean(1)[:, 0]
    pieces = int(math.ceil(len(P) / limit)) + 1
    cuts = np.quantile(cx, np.linspace(0, 1, pieces + 1))
    out = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        sel = T[(cx >= a) & ((cx < b) | (b == cuts[-1]))]
        used = np.unique(sel.ravel())
        remap = -np.ones(len(P), int)
        remap[used] = np.arange(len(used))
        out.append((texname, mat, code, P[used], remap[sel], np.asarray(uv)[used], np.asarray(rgb)[used]) +
                   tuple(part[7:]))
    return out


def place_old_spots(c, line, region, rng, playing, keep_out):
    """Pebble Beach's trees (v11): OSM's tree points, then a random scatter, nearest the hole line first."""
    spots = []   # (x, y, kind)
    for x, y in c.trees:
        if region.contains(Point(x, y)) and c.land.contains(Point(x, y)) and not playing.contains(Point(x, y)):
            spots.append((x, y, "osm"))
    minx, miny, maxx, maxy = region.bounds
    step = 20.0
    for gx in np.arange(minx, maxx, step):
        for gy in np.arange(miny, maxy, step):
            x, y = gx + rng.uniform(-8, 8), gy + rng.uniform(-8, 8)
            p = Point(x, y)
            if not region.contains(p) or not c.land.contains(p) or keep_out.contains(p):
                continue
            in_course = c.area.contains(p)
            chance = 0.12 if in_course else 0.55
            if rng.uniform() < chance:
                spots.append((x, y, "course" if in_course else "town"))
    spots.sort(key=lambda s: (s[2] != "osm", line.distance(Point(s[0], s[1]))))
    return spots


def model_root(L_, texnames, texset, G_all, uv_all, col_all, groups, pos_frac=POS_FRAC):
    """Arrays, meshes (tiled display lists) and a root like the game's terrain roots; returns the root offset.
    groups: [((texture, material, code), tris)] with tris indexing the arrays."""
    if len(G_all) > 65536:
        raise SystemExit(f"{len(G_all)} vertices: too many for 16-bit indices")
    mats = L_.alloc(b"".join(struct.pack('>5f', 0, 0, su, sv, 0) for su, sv in MATS))
    posb = L_.alloc(cpack(G_all, pos_frac))
    texb = L_.alloc(cpack(uv_all, TEX_FRAC))
    colb = L_.alloc(np.asarray(col_all, np.uint8).tobytes())
    L_.alloc(bytes(32))

    def vertex(v):
        return struct.pack('>HHH', v, v, v)

    merged = {}
    for key, tris in groups:
        if len(tris):
            merged.setdefault(key, []).append(np.asarray(tris, int).reshape(-1, 3))
    recs = []
    for key, parts in merged.items():
        texname, mat, code = key[:3]
        # the sea's surface (code 0x18) goes on the water layer, as in Blooper Bay and Cheep Cheep Falls
        flags, layer, pass_ = key[3:] if len(key) > 3 else (0x40000101, 1, 3) if code == 0x18 else (0x40000101, 0, 2)
        tris_all = np.concatenate(parts)
        cen_g = G_all[tris_all].mean(1)[:, [0, 2]] * UNIT_M
        tiles = {}
        for i, key in enumerate(map(tuple, np.floor(cen_g / TILE).astype(int))):
            tiles.setdefault(key, []).append(i)
        entries = []
        for key, idxs in tiles.items():
            tris = tris_all[idxs]
            dl = L_.alloc(strip_dl(tris, vertex), 32)
            size = len(L_.blob) - dl
            pp = G_all[tris.ravel()]
            entries.append((dl, size, pp.min(0), pp.max(0)))
        ent = L_.alloc(b"".join(struct.pack('>II6f', 0, sz, *lo, *hi) for d_, sz, lo, hi in entries), 32)
        for i, (d_, sz, lo, hi) in enumerate(entries):
            L_.ptr(ent + 0x20 * i, d_)
        grp = L_.alloc(struct.pack('>IIi', 3, 1, -1) + bytes(0x24) + struct.pack('>II', len(entries), 0), 32)
        L_.ptr(grp + 0x34, ent)
        rec = bytearray(0x3C)
        struct.pack_into('>II', rec, 0, layer, flags)
        rec[10], rec[11] = texnames.index(texname), mat
        struct.pack_into('>IIiII', rec, 0x28, 1, 0, -1, pass_, code)
        recs.append((rec, grp))
    meshes = L_.alloc(b"".join(r for r, g in recs), 32)
    for i, (r, g) in enumerate(recs):
        L_.ptr(meshes + 0x3C * i + 0x2C, g)
    root = L_.alloc(bytes(0xD0), 32)
    struct.pack_into('>I', L_.blob, root, 0x0131A313)
    struct.pack_into('>I', L_.blob, root + 4, 0x80000060 | pos_frac)
    struct.pack_into('>I', L_.blob, root + 0x18, 0xFF)
    struct.pack_into('>I', L_.blob, root + 0x2C, 0x80000060 | TEX_FRAC)
    struct.pack_into('>I', L_.blob, root + 0x34, 1)
    struct.pack_into('>I', L_.blob, root + 0x3C, len(recs))
    struct.pack_into('>I', L_.blob, root + 0x90, 2)
    for off, target in ((0x08, posb), (0x30, texb), (0x38, colb), (0x40, meshes), (0x44, mats), (0x8C, texset)):
        L_.ptr(root + off, target)
    L_.ptr_end(root + 0xA4)
    return root


def parts_arrays(parts, ox, oy):
    """[(texture, material, code, points (k,3) metres, tris, uv, rgb or rgba[, (flags, layer, pass)])] -> one set of
    arrays and groups."""
    Gs, uvs, cols, groups = [], [], [], []
    k0 = 0
    for part in parts:
        texname, mat, code, P, tris_, uv_, rgb = part[:7]
        P = np.asarray(P, float)
        Gs.append(np.stack([(P[:, 0] - ox) / UNIT_M, P[:, 1] / UNIT_M, (P[:, 2] - oy) / UNIT_M], 1))
        uvs.append(np.asarray(uv_, float).reshape(-1, 2))
        rgb = np.asarray(rgb, np.uint8).reshape(len(P), -1)
        if rgb.shape[1] == 3:
            rgb = np.concatenate([rgb, np.full((len(P), 1), 255, np.uint8)], 1)
        cols.append(rgb)
        groups.append(((texname, mat, code) + tuple(part[7:8][0] if len(part) > 7 else ()),
                       np.asarray(tris_, int).reshape(-1, 3) + k0))
        k0 += len(P)
    if not Gs:
        return None
    return np.concatenate(Gs), np.concatenate(uvs), np.concatenate(cols), groups


IDENTITY = {"flags": 0, "pos": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0], "quat": [0.0, 0.0, 0.0, 1.0]}


SEA_RGB = np.array([111, 183, 159])      # Blooper Bay's sea surface tint (its alpha there: 0 at the shore, 95 offshore)
DEEP_RGB = np.array([30, 92, 116])       # the seabed out of the shallows
SEA_ALPHA = 140                          # the surface offshore (more than Blooper Bay's 95: the waves show)
WATER_LAYER = (0x40000101, 1, 3)


def sea_depth(d):
    return -np.minimum(0.4 + 0.2 * d, 10.0)


def sea_parts(c, pts, T_sea, far_haze=None):
    """The sea as Blooper Bay draws it: a seabed (its sand tinted teal in the shallows, dark further out) under a
    see-through surface on the water layer. T_sea indexes pts (x, y metres); returns parts for parts_arrays."""
    if not len(T_sea):
        return []
    used = np.unique(T_sea.ravel())
    remap = -np.ones(len(pts), int)
    remap[used] = np.arange(len(used))
    tris = remap[T_sea]
    P = pts[used]
    d = distance(c.land.boundary, shp_points(P))
    t = np.clip(d / 45.0, 0, 1)[:, None]
    bed = SEA_RGB * (1 - t) + DEEP_RGB * t
    if far_haze is not None:
        bed = bed * (1 - far_haze[used]) + np.array([150, 165, 175]) * far_haze[used]
    alpha = np.round(SEA_ALPHA * np.clip(d / 20.0, 0, 1))
    surf = np.concatenate([np.tile(SEA_RGB, (len(P), 1)), alpha[:, None]], 1)
    uv = np.stack([P[:, 0] / 4.0, -P[:, 1] / 4.0], 1)
    uv -= np.round(uv.mean(0))      # small texcoords (s16/64)
    bed_P = np.stack([P[:, 0], sea_depth(d), P[:, 1]], 1)
    surf_P = np.stack([P[:, 0], np.zeros(len(P)), P[:, 1]], 1)
    return [("beach", 1, 0x05, bed_P, tris, uv, bed.astype(np.uint8)),
            ("sea", 2, 0x18, surf_P, tris, uv, surf.astype(np.uint8), WATER_LAYER)]


def surf_foam(c, region, width=9.0):
    """White water along the coast: a ribbon from the waterline out to `width` m, fading out to sea (a part)."""
    band = c.land.buffer(width).difference(c.land.buffer(0.3)).intersection(region.buffer(-2))
    if band.is_empty:
        return []
    outline = np.asarray(ring_points(band, 2.0)).reshape(-1, 2)
    minx, miny, maxx, maxy = band.bounds
    gx, gy = np.meshgrid(np.arange(minx, maxx, 3.0), np.arange(miny, maxy, 3.0))
    inner = np.stack([gx.ravel(), gy.ravel()], 1)
    inner = inner[contains_xy(band, inner[:, 0], inner[:, 1])]
    P = dedupe(np.concatenate([outline, inner]), 0.8, 0)
    if len(P) < 3:
        return []
    tri = Delaunay(P)
    T = tri.simplices
    cen = P[T].mean(1)
    T = T[contains_xy(band.buffer(0.2), cen[:, 0], cen[:, 1])]
    a, b, cc = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
    cw = (b[:, 0] - a[:, 0]) * (cc[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (cc[:, 0] - a[:, 0]) < 0
    T[cw] = T[cw][:, [0, 2, 1]]       # counter-clockwise in (x, y), the game's (X, Z), faces up in the game
    d = distance(c.land.boundary, shp_points(P))
    alpha = np.clip(255 * (1 - (d - 1.0) / (width - 1.0)), 0, 230).astype(np.uint8)
    col = np.stack([np.full(len(P), 255, np.uint8)] * 3 + [alpha], 1)
    P3 = np.stack([P[:, 0], np.full(len(P), 0.25), P[:, 1]], 1)
    uv = np.stack([P[:, 0] / 6.0, -P[:, 1] / 6.0], 1)
    uv -= np.round(uv.mean(0))
    return [("foam", 1, 0x19, P3, T, uv, col, (0xC0000101, 1, 3))]


def SURF_TEX(k):
    """(texture, material, code) of a terrain surface."""
    if k == CLIFF:
        return ("rock", 1, 0x09)
    texname, mat, code, zone = SURF[k]
    return (texname, mat, code)


def far_landscape(c, region, pts, h, mid):
    """Land and sea from the region's edge out to scenery.FAR (coarse, hazier with distance)."""
    edge = distance(region.exterior, shp_points(pts)) < 0.6
    e_pts, e_h = pts[edge], h[edge]
    step = 45.0
    gx = np.arange(mid[0] - scenery.FAR, mid[0] + scenery.FAR + step, step)
    gy = np.arange(mid[1] - scenery.FAR, mid[1] + scenery.FAR + step, step)
    X, Y = np.meshgrid(gx, gy)
    q = np.stack([X.ravel(), Y.ravel()], 1)
    q = q + np.random.default_rng(5).uniform(-8, 8, q.shape)
    r = np.hypot(q[:, 0] - mid[0], q[:, 1] - mid[1])
    q = q[(r < scenery.FAR) & ~contains_xy(region.buffer(step * 0.4), q[:, 0], q[:, 1])]
    ang = np.linspace(0, 2 * np.pi, 360, endpoint=False)
    ring = np.stack([mid[0] + scenery.FAR * np.sin(ang), mid[1] + scenery.FAR * np.cos(ang)], 1)
    q = np.concatenate([q, ring])
    land = contains_xy(c.land, q[:, 0], q[:, 1])
    qh = np.where(land, np.maximum(scenery.elevation(q[:, 0], q[:, 1]), 0.8), 0.0)
    allp = np.concatenate([e_pts, q])
    allh = np.concatenate([e_h, qh])
    tri = Delaunay(allp)
    T = tri.simplices
    cen = allp[T].mean(1)
    keep = ~contains_xy(region.buffer(-0.5), cen[:, 0], cen[:, 1])
    keep &= np.hypot(cen[:, 0] - mid[0], cen[:, 1] - mid[1]) < scenery.FAR
    T = T[keep]
    cen = cen[keep]
    P3 = np.stack([allp[:, 0], allh, allp[:, 1]], 1)
    a, b, cc = P3[T[:, 0]], P3[T[:, 1]], P3[T[:, 2]]
    flip = np.cross(b - a, cc - a)[:, 1] > 0
    T[flip] = T[flip][:, [0, 2, 1]]
    dist = np.hypot(allp[:, 0] - mid[0], allp[:, 1] - mid[1])
    haze = np.clip((dist - 500) / 2000, 0, 1)[:, None]
    on_land = contains_xy(c.land, cen[:, 0], cen[:, 1])
    land_rgb = np.array([96, 110, 92]) * (1 - haze) + np.array([150, 165, 175]) * haze
    uvp = np.stack([(allp[:, 0] - mid[0]) / 32.0, -(allp[:, 1] - mid[1]) / 32.0], 1)
    out = []
    sel = T[on_land]
    if len(sel):
        used = np.unique(sel.ravel())
        remap = -np.ones(len(allp), int)
        remap[used] = np.arange(len(used))
        out.append(("natural", 2, 0x06, P3[used], remap[sel], uvp[used], land_rgb[used].astype(np.uint8)))
    for part in sea_parts(c, allp, T[~on_land], haze):
        tex, mat, code, P_, tris_, uv_, rgb_ = part[:7]
        out.append((tex, 2, code, P_, tris_, uv_ / 8.0) + part[6:])
    return out


def cpack(arr, frac):
    q = np.round(np.asarray(arr) * (1 << frac)).astype(np.int64)
    if q.min() < -0x8000 or q.max() > 0x7FFF:
        raise ValueError(f"coordinates out of s16 range with {frac} fraction bits: {q.min()} {q.max()}")
    return q.astype('>i2').tobytes()


# ---------------------------------------------------------------- flyover camera

def look_quat(eye, target):
    """Quaternion (x, y, z, w) turning the camera's -Z to look at target with +Y up."""
    f = np.array(target, float) - np.array(eye, float)
    f /= np.linalg.norm(f)
    up = np.array([0.0, 1.0, 0.0])
    r = np.cross(f, up)
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    m = np.stack([r, u, -f], 1)      # columns: camera x, y, z axes in world
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1) * 2
        w, x, y, z = 0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        w, x, y, z = (m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        w, x, y, z = (m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s
    else:
        s = math.sqrt(1 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        w, x, y, z = (m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s
    return [x, y, z, w]


def flyover(G, pts, line, ox, oy, h, tee_ft, pin_ft):
    """Three clips: over the tee looking down the hole, along the hole, down onto the green."""
    U = 1 / holedata.CAM_POS_SCALE      # key units per game unit
    tee = np.array(tee_ft[0]) / 32
    pin = np.array(pin_ft[0]) / 32
    L = np.linalg.norm((pin - tee)[[0, 2]])
    dirv = (pin - tee) / max(np.linalg.norm(pin - tee), 1e-6)
    flat = np.array([dirv[0], 0, dirv[2]])
    flat /= np.linalg.norm(flat)

    def key(frame, eye, target):
        return [frame] + [float(v * U) for v in eye], [frame] + look_quat(eye, target)

    clips = []
    # 1: behind and above the tee, slowly rising
    e0 = tee - flat * 3.0 + np.array([0, 1.2, 0])
    e1 = tee - flat * 2.0 + np.array([0, 2.4, 0])
    t0 = tee + flat * L * 0.5
    p0, r0 = key(0, e0, t0)
    p1, r1 = key(119, e1, t0 + flat * L * 0.2)
    clips.append({"length": 120, "pos": [p0, p1], "rot": [r0, r1], "fov": [[0, 50.0], [119, 50.0]]})
    # 2: flying down the hole
    pos, rot = [], []
    for i, f in enumerate((0, 90, 179)):
        s = (0.15, 0.5, 0.85)[i]
        e = tee + (pin - tee) * s + np.array([0, 3.5 + 1.5 * math.sin(s * math.pi), 0])
        pk, rk = key(f, e, e + flat * 6.0 - np.array([0, 2.0, 0]))
        pos.append(pk)
        rot.append(rk)
    clips.append({"length": 180, "pos": pos, "rot": rot, "fov": [[0, 55.0], [179, 55.0]]})
    # 3: onto the green
    e0 = pin - flat * 6.0 + np.array([0, 2.5, 0])
    e1 = pin - flat * 3.0 + np.array([0, 1.0, 0])
    p0, r0 = key(0, e0, pin)
    p1, r1 = key(149, e1, pin)
    clips.append({"length": 150, "pos": [p0, p1], "rot": [r0, r1], "fov": [[0, 45.0], [149, 40.0]]})
    return {"clips": clips, "sets": [[0, 1, 2], [], []]}


if __name__ == "__main__":
    out = sys.argv[1]
    holes = [int(a) for a in sys.argv[2:]] or list(range(1, 19))
    infos = [build(n, out) for n in holes]
    json.dump(infos, open(os.path.join(out, f"holes_{'_'.join(map(str, holes))}.json"), "w"), indent=1)
