"""Timber Creek Golf Club (Friendswood, Texas) from the OSM features (osm.py with TTMOD_COURSE=timbercreek), the same
way as pasadena.py.

The club has 27 holes in three nines (Creekside, The Pines, Timber Trails), each numbered 1-9 in OSM
("golf:course:name"). The game's course is The Pines (holes 1-9) then Timber Trails (10-18): the club's par-72
pairing, the one the rating sites list at 6,993 yards. Creekside's holes are still there as real ground round them.
Thick woods of oaks and pines with Clear Creek winding through (canopy.py places the trees), houses round it, and no
industry on the horizon.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shapely.geometry import LineString

import pasadena

NAME = "Timber Creek"         # the course's name in the game
DISC = "H"                    # its files' top folder on the disc
NINES = {"The Pines": 0, "Timber Trails": 9}   # OSM nine -> holes before it in the game's 18
# The card (yards from the white tees, the blue tees, par): TheGrint and 18birdies, The Pines / Timber Trails
# (6,350 / 6,993, par 72).
CARD = {1: (357, 399, 4), 2: (294, 361, 4), 3: (526, 567, 5), 4: (339, 378, 4), 5: (399, 427, 4),
        6: (131, 150, 3), 7: (361, 407, 4), 8: (155, 179, 3), 9: (513, 550, 5), 10: (415, 482, 4),
        11: (152, 165, 3), 12: (382, 412, 4), 13: (189, 209, 3), 14: (397, 441, 4), 15: (388, 427, 4),
        16: (472, 512, 5), 17: (415, 428, 4), 18: (465, 499, 5)}


class Course(pasadena.Course):
    COURSE_NAME = "Timber Creek Golf Club"
    WATERWAYS = True          # its drains and creeks (Clear Creek) are mapped as lines
    INDUSTRY = False

    def _pick_holes(self):
        holes = {}
        for f in self.features:
            t = f["tags"]
            if t.get("golf") == "hole" and f["kind"] == "way" and t.get("golf:course:name") in NINES:
                holes[NINES[t["golf:course:name"]] + int(t["ref"])] = LineString(f["pts"])
        return holes


if __name__ == "__main__":
    pasadena.report(Course(), CARD)
