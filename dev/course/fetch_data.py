"""Download the real-world data a course is built from, into <TTMOD_ROOT>/mod/course-data/<course>
(TTMOD_COURSE, osm.py: pebble or pasadena):

  - OpenStreetMap data round the course (tiles from the OSM editing API's /map call; Pebble's area is over its
    50,000-node limit in one piece). (c) OpenStreetMap contributors, ODbL.
  - Elevation: Terrarium tiles from the AWS Terrain Tiles open dataset (USGS 3DEP and others; Mapzen format),
    zoom 15 over the course and zoom 11 for the land round it (Pebble: the mountains round Carmel Bay).

Then merges the OSM tiles into features.json (osm.py). Re-running skips files already there.
python -I fetch_data.py
"""
import math
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import osm  # noqa: E402

AGENT = "ttmod-course-data/1.0 (Toadstool Tour fan mod)"
AREAS = {   # course: (OSM box south, west, north, east; elevation tiles {zoom: (N, W, S, E)})
    "pebble": ((36.552, -121.958, 36.580, -121.918),
               {15: (36.582, -121.962, 36.548, -121.912), 11: (36.80, -122.10, 36.30, -121.55)}),
    "pasadena": ((29.603, -95.188, 29.631, -95.165),
                 {15: (29.634, -95.192, 29.599, -95.161), 11: (29.80, -95.40, 29.43, -94.95)}),
}
OSM_BOX, DEM = AREAS[osm.COURSE]
OSM_STEP = (0.007, 0.010)


def get(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return
    req = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = r.read()
    open(path, "wb").write(data)
    print(f"{os.path.basename(path)}: {len(data):,} bytes")


def tile(lat, lon, z):
    n = 2 ** z
    return int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)


def main():
    os.makedirs(osm.DATA, exist_ok=True)
    s, w, n, e = OSM_BOX
    k = 0
    lat = s
    while lat < n - 1e-9:
        lon = w
        while lon < e - 1e-9:
            box = f"{lon:.3f},{lat:.3f},{lon + OSM_STEP[1]:.3f},{lat + OSM_STEP[0]:.3f}"
            get(f"https://api.openstreetmap.org/api/0.6/map?bbox={box}", os.path.join(osm.DATA, f"osm_{k}.xml"))
            k += 1
            lon += OSM_STEP[1]
            time.sleep(1)
        lat += OSM_STEP[0]
    for z, (north, west, south, east) in DEM.items():
        folder = os.path.join(osm.DATA, f"dem{z}")
        os.makedirs(folder, exist_ok=True)
        x0, y0 = tile(north, west, z)
        x1, y1 = tile(south, east, z)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                get(f"https://elevation-tiles-prod.s3.amazonaws.com/terrarium/{z}/{x}/{y}.png",
                    os.path.join(folder, f"{z}_{x}_{y}.png"))
    osm.main()


if __name__ == "__main__":
    main()
