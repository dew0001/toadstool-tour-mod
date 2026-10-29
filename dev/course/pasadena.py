"""Pasadena Municipal Golf Course (Pasadena, Texas) from the OSM features (osm.py with TTMOD_COURSE=pasadena): its
18 holes and everything around them, the same way as pebble.py (whose Course this builds on).

Inland and flat (about 10 m above the sea): the land is everywhere, so there is no coast or sea; its water is the
ponds and ditches mapped as water hazards. Round it: the oil tank farm by the course and Ellington Field's hangars
(OSM), and refineries on the horizon (industry.py; Andrew: "Make the background like factories and refineries").
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shapely.affinity import scale
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

import pebble

NAME = "Pasadena Municipal"   # the course's name in the game
DISC = "F"                    # its files' top folder on the disc (Pebble Beach's is E)
# The card (yards from the blue tees, the black tees, par) - greenskeeper.org's scorecard (6,225 / 6,750, par 72).
CARD = {1: (467, 490, 5), 2: (105, 138, 3), 3: (384, 410, 4), 4: (352, 395, 4), 5: (352, 372, 4),
        6: (488, 516, 5), 7: (419, 437, 4), 8: (363, 408, 4), 9: (141, 167, 3), 10: (389, 405, 4),
        11: (477, 521, 5), 12: (195, 224, 3), 13: (281, 324, 4), 14: (475, 495, 5), 15: (137, 165, 3),
        16: (409, 431, 4), 17: (404, 449, 4), 18: (387, 403, 4)}


class Course(pebble.Course):
    COURSE_NAME = "Pasadena Municipal Golf Course"
    LODGE = None
    WATER_KINDS = ("water", "water_hazard", "lateral_water_hazard")
    INDUSTRY = True           # holegen.py: industry.py's tanks, sheds and refineries
    CANOPY = True             # v22: its real trees (canopy.py)
    WATERWAYS = False         # v22: creeks and drains mapped only as lines become water this wide (m) round them
    WATERWAY_WIDTH = {"river": 12.0, "stream": 4.0, "canal": 6.0, "drain": 3.0, "ditch": 3.0}

    def __init__(self):
        super().__init__()

        def polys(test):
            out = []
            for f in self.features:
                if test(f["tags"]):
                    p = pebble._poly(f)
                    if p is not None and not p.is_empty:
                        out.append(scale(p, 1.0, -1.0, origin=(0, 0)))   # the frame's y south (pebble.Course._mirror)
            return out
        self.tanks = polys(lambda t: t.get("man_made") == "storage_tank")
        if self.WATERWAYS:   # (not underground, not the dry intermittent gullies)
            for f in self.features:
                t = f["tags"]
                w = self.WATERWAY_WIDTH.get(t.get("waterway"))
                if w is None or f["kind"] != "way" or len(f["pts"]) < 2 or t.get("tunnel") or \
                        t.get("culvert") == "yes" or t.get("intermittent") == "yes":
                    continue
                band = LineString(f["pts"]).buffer(float(t.get("width", w)) / 2, cap_style=2)
                self.kinds.setdefault("water", []).append((scale(band, 1.0, -1.0, origin=(0, 0)), t))
        self.industrial = unary_union(polys(lambda t: t.get("landuse") == "industrial") or [Polygon()])

    def _land(self):
        return Polygon([(-5000, -5000), (5000, -5000), (5000, 5000), (-5000, 5000)])

    def tees_of(self, n):
        """v22: every tee on the hole's line (within 20 m of it) in its first 160 m, not just those within 60 m of
        the line's start: OSM's lines often start on a far-back tee the scorecard doesn't list (Timber Creek's Pines
        7 starts 63 m behind its blue tee). holegen.py picks the ones that match the card."""
        line = self.holes[n]
        start = Point(line.coords[0])
        return sorted([p for p, t in self.kinds.get("tee", []) if line.distance(p.centroid) < 20
                       and line.project(p.centroid) < 160], key=lambda p: p.distance(start))


def report(c, card):
    print("course area m2", round(c.area.area), "trees", len(c.canopy or c.trees))
    for n in range(1, 19):
        line = c.holes[n]
        g = c.green_of(n)
        tees = c.tees_of(n)
        inside = c.area.buffer(5).contains(line)
        print(n, "par", card[n][2], "card", card[n][:2], "line", round(line.length / 0.9144), "yd", "green",
              round(g.area), "m2", "tees", len(tees), "in course", inside)
    for k, v in sorted(c.kinds.items()):
        print(k, len(v))


if __name__ == "__main__":
    report(Course(), CARD)
