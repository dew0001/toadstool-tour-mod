"""Pebble Beach Golf Links from the OSM features (osm.py): its 18 holes and everything around them.

Shapely geometry throughout, in metres from osm.ORIGIN. The OSM data is read with x east, y north, then Course
mirrors it to x east, y SOUTH: the game's axes are right-handed with Y up, so with X east its Z points south, and the
rest of the generator writes y straight to game Z.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shapely.affinity import scale
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import unary_union

import osm

# The card (yards from the regular "blue" tees, then the championship tees, par) - pebblebeach.com scorecard.
CARD = {1: (380, 380, 4), 2: (511, 516, 5), 3: (404, 404, 4), 4: (331, 331, 4), 5: (195, 195, 3),
        6: (523, 523, 5), 7: (109, 109, 3), 8: (428, 428, 4), 9: (505, 526, 4), 10: (446, 495, 4),
        11: (390, 390, 4), 12: (202, 202, 3), 13: (445, 445, 4), 14: (580, 580, 5), 15: (397, 397, 4),
        16: (403, 403, 4), 17: (178, 178, 3), 18: (543, 543, 5)}


def _poly(f):
    if f["kind"] == "way":
        if len(f["pts"]) < 4 or not f["closed"]:
            return None
        p = Polygon(f["pts"])
    else:
        outers = [Polygon(r) for r in f["outer"] if len(r) >= 4]
        if not outers:
            return None
        p = unary_union([o.buffer(0) for o in outers])
        for r in f["inner"]:
            if len(r) >= 4:
                p = p.difference(Polygon(r).buffer(0))
    return p.buffer(0) if not p.is_valid else p


class Course:
    def __init__(self):
        data = json.load(open(os.path.join(osm.DATA, "features.json")))
        self.features = data["features"]
        self.points = data["points"]
        course = next(f for f in self.features if f["tags"].get("leisure") == "golf_course"
                      and f["tags"].get("name") == "Pebble Beach Golf Course")
        self.area = _poly(course)
        self.holes = {}
        for f in self.features:
            t = f["tags"]
            if t.get("golf") == "hole" and f["kind"] == "way" and not t.get("name"):
                line = LineString(f["pts"])
                if self.area.buffer(30).contains(Point(f["pts"][0])) and self.area.buffer(30).contains(
                        Point(f["pts"][-1])):
                    self.holes[int(t["ref"])] = line
        assert sorted(self.holes) == list(range(1, 19)), sorted(self.holes)
        self.kinds = {}
        for f in self.features:
            t = f["tags"]
            key = None
            g = t.get("golf")
            if g in ("fairway", "green", "tee", "bunker", "rough", "water_hazard", "lateral_water_hazard",
                     "driving_range"):
                key = g
            elif g == "green;fairway":
                key = "fairway"
            elif t.get("building"):
                key = "building"
            elif t.get("natural") in ("beach", "sand"):
                key = "beach"
            elif t.get("natural") in ("wood",) or t.get("landuse") == "forest":
                key = "wood"
            elif t.get("natural") == "bare_rock":
                key = "rock"
            elif t.get("natural") == "water" or t.get("leisure") == "swimming_pool":
                key = "water"
            if key:
                p = _poly(f)
                if p is not None and not p.is_empty:
                    self.kinds.setdefault(key, []).append((p, t))
        self.cartpaths = [LineString(f["pts"]) for f in self.features
                          if f["tags"].get("golf") in ("cartpath", "path") and f["kind"] == "way" and len(f["pts"]) > 1]
        self.roads = [(LineString(f["pts"]), f["tags"].get("highway")) for f in self.features
                      if f["tags"].get("highway") and f["kind"] == "way" and len(f["pts"]) > 1
                      and f["tags"].get("highway") not in ("footway", "path", "steps")]
        self.trees = [tuple(p["pt"]) for p in self.points if p["tags"].get("natural") == "tree"]
        self.land = self._land()
        self._mirror()

    def _mirror(self):
        """x east, y north -> x east, y south (see the top)."""
        def m(g):
            return scale(g, 1.0, -1.0, origin=(0, 0))
        self.area = m(self.area)
        self.holes = {n: m(line) for n, line in self.holes.items()}
        self.kinds = {k: [(m(p), t) for p, t in items] for k, items in self.kinds.items()}
        self.cartpaths = [m(line) for line in self.cartpaths]
        self.roads = [(m(line), kind) for line, kind in self.roads]
        self.trees = [(x, -y) for x, y in self.trees]
        self.land = m(self.land)

    def _land(self):
        """Land polygon from the OSM coastline ways (sea on the right of a coastline way)."""
        coast = [f["pts"] for f in self.features if f["tags"].get("natural") == "coastline" and f["kind"] == "way"]
        # stitch ways end to end
        segs = [list(map(tuple, c)) for c in coast]
        chains = []
        while segs:
            c = segs.pop()
            changed = True
            while changed:
                changed = False
                for i, s in enumerate(segs):
                    if s[0] == c[-1]:
                        c += s[1:]
                        segs.pop(i)
                        changed = True
                        break
                    if s[-1] == c[0]:
                        c = s[:-1] + c
                        segs.pop(i)
                        changed = True
                        break
            chains.append(c)
        big = Polygon([(-5000, -5000), (5000, -5000), (5000, 5000), (-5000, 5000)])
        land_parts, open_chains = [], []
        for c in chains:
            if c[0] == c[-1] and len(c) > 3:
                land_parts.append(Polygon(c).buffer(0))   # islands / rocks
            else:
                open_chains.append(c)
        # the mainland: the long open chain(s), closed round the north and east of the box (land side)
        main = max(open_chains, key=len) if open_chains else None
        land = Polygon()
        if main:
            a, b = main[0], main[-1]
            # walk from the chain's end round the box back to its start, keeping the land on the left of the chain
            ring = main + self._box_walk(b, a)
            land = Polygon(ring).buffer(0)
        return unary_union([land] + land_parts)

    @staticmethod
    def _box_walk(frm, to, size=5000):
        """Points from `frm` out to the box edge, counter-clockwise round the box, then in to `to`."""
        def edge_point(p):
            x, y = p
            d = {"w": x + size, "e": size - x, "s": y + size, "n": size - y}
            side = min(d, key=d.get)
            return side, {"w": (-size, y), "e": (size, y), "s": (x, -size), "n": (x, size)}[side]
        corners = [(-size, -size), (size, -size), (size, size), (-size, size)]   # sw, se, ne, nw (ccw)

        def angle(p):
            return math.atan2(p[1], p[0])
        s0, p0 = edge_point(frm)
        s1, p1 = edge_point(to)
        out = [p0]
        a0, a1 = angle(p0), angle(p1)
        # counter-clockwise from a0 to a1: land is to the left of the coastline (OSM: land left, sea right)
        span = (a1 - a0) % (2 * math.pi)
        for c in sorted(corners, key=lambda c: (angle(c) - a0) % (2 * math.pi)):
            if 0 < (angle(c) - a0) % (2 * math.pi) < span:
                out.append(c)
        out.append(p1)
        return out

    def hole(self, n):
        return self.holes[n]

    def features_near(self, geom, dist, kinds=None):
        zone = geom.buffer(dist)
        out = {}
        for k, items in self.kinds.items():
            if kinds and k not in kinds:
                continue
            for p, t in items:
                if p.intersects(zone):
                    out.setdefault(k, []).append((p, t))
        return out

    def green_of(self, n):
        line = self.holes[n]
        end = Point(line.coords[-1])
        greens = [p for p, t in self.kinds.get("green", []) if p.distance(end) < 25]
        return min(greens, key=lambda p: p.distance(end)) if greens else end.buffer(12)

    def tees_of(self, n):
        line = self.holes[n]
        start = Point(line.coords[0])
        return sorted([p for p, t in self.kinds.get("tee", []) if p.distance(start) < 60],
                      key=lambda p: p.distance(start))


if __name__ == "__main__":
    c = Course()
    print("land area km2", round(c.land.area / 1e6, 2))
    for n in range(1, 19):
        line = c.holes[n]
        g = c.green_of(n)
        tees = c.tees_of(n)
        print(n, "par", c.CARD[n][2] if hasattr(c, "CARD") else CARD[n][2], "line", round(line.length / 0.9144), "yd",
              "green area", round(g.area), "m2", "tees", len(tees), "start on land", c.land.contains(Point(line.coords[0])))
