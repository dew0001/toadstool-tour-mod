"""Battleground Golf Course at Deer Park (Deer Park, Texas) from the OSM features (osm.py with TTMOD_COURSE=battleground):
its 18 holes and everything round them, the same way as pasadena.py.

Flat Gulf Coast ground a few metres above the sea, its ponds and drains as water hazards, its trees from the canopy
heights (canopy.py), and the Ship Channel's refineries on the horizon (industry.py; Shell Deer Park is next door).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import osm
import pasadena

NAME = "Battleground"         # the course's name in the game
DISC = "G"                    # its files' top folder on the disc
# The card (yards from the gold tees, the black tees, par): battlegroundgolfcourse.com, GolfPass, greenskeeper.org
# (6,303 / 6,942, par 72).
CARD = {1: (372, 426, 4), 2: (349, 388, 4), 3: (164, 179, 3), 4: (409, 455, 4), 5: (477, 507, 5),
        6: (171, 186, 3), 7: (394, 415, 4), 8: (454, 514, 5), 9: (378, 410, 4), 10: (461, 505, 5),
        11: (387, 416, 4), 12: (386, 417, 4), 13: (156, 187, 3), 14: (378, 446, 4), 15: (375, 408, 4),
        16: (445, 491, 5), 17: (149, 175, 3), 18: (398, 417, 4)}


MONUMENT = (29.749875, -95.080594)   # the San Jacinto Monument, 7.9 km north-east (hole 9's marker is "The Monument")


class Course(pasadena.Course):
    COURSE_NAME = "Battleground Golf Course at Deer Park"
    WATERWAYS = True          # its drains and creeks (Clear Creek) are mapped as lines

    def __init__(self):
        super().__init__()
        x, y = osm.to_local(*MONUMENT)
        self.LANDMARKS = [(x, -y, "san_jacinto")]   # the course frame: y south (pebble.Course._mirror)


if __name__ == "__main__":
    pasadena.report(Course(), CARD)
