"""Merge the OSM tiles in a course's data folder into one feature list (ways and multipolygon relations with their
tags and coordinates), in a local metric frame (metres east, metres north of ORIGIN).
The course is TTMOD_COURSE (pebble, the default, or pasadena: COURSES); every generator script follows it.
python -I osm.py   -> <data>/features.json, and prints a summary of golf features."""
import glob
import json
import math
import os
import xml.etree.ElementTree as ET
from collections import Counter

ROOT = os.environ.get("TTMOD_ROOT", os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))
COURSES = {                   # course -> the local frame's origin (lat, lon), near the course's middle
    "pebble": (36.566, -121.938),       # Pebble Beach Golf Links (course code 8)
    "pasadena": (29.6165, -95.1768),    # Pasadena Municipal Golf Course, Pasadena, Texas (course code 9)
}
COURSE = os.environ.get("TTMOD_COURSE", "pebble")
DATA = os.path.join(ROOT, "mod", "course-data", COURSE)   # fetch_data.py downloads it
ORIGIN = COURSES[COURSE]      # lat, lon
R = 6378137.0


def to_local(lat, lon):
    x = math.radians(lon - ORIGIN[1]) * R * math.cos(math.radians(ORIGIN[0]))
    y = math.radians(lat - ORIGIN[0]) * R
    return x, y


def to_latlon(x, y):
    """Works on numbers and numpy arrays."""
    lat = ORIGIN[0] + y / R * (180 / math.pi)
    lon = ORIGIN[1] + x / (R * math.cos(math.radians(ORIGIN[0]))) * (180 / math.pi)
    return lat, lon


def load():
    nodes, ways, rels = {}, {}, {}
    for path in sorted(glob.glob(os.path.join(DATA, "osm_*.xml"))):
        root = ET.parse(path).getroot()
        for e in root:
            tags = {t.get("k"): t.get("v") for t in e.findall("tag")}
            if e.tag == "node":
                nodes[e.get("id")] = (float(e.get("lat")), float(e.get("lon")), tags)
            elif e.tag == "way":
                ways[e.get("id")] = ([n.get("ref") for n in e.findall("nd")], tags)
            elif e.tag == "relation":
                rels[e.get("id")] = ([(m.get("type"), m.get("ref"), m.get("role")) for m in e.findall("member")],
                                     tags)
    return nodes, ways, rels


def main():
    nodes, ways, rels = load()
    feats = []
    for wid, (refs, tags) in ways.items():
        if not tags or any(r not in nodes for r in refs):
            continue
        pts = [to_local(nodes[r][0], nodes[r][1]) for r in refs]
        feats.append({"kind": "way", "id": wid, "tags": tags, "pts": pts, "closed": refs[0] == refs[-1]})
    for rid, (members, tags) in rels.items():
        if tags.get("type") != "multipolygon":
            continue
        outer, inner = [], []
        for typ, ref, role in members:
            if typ == "way" and ref in ways and all(r in nodes for r in ways[ref][0]):
                pts = [to_local(nodes[r][0], nodes[r][1]) for r in ways[ref][0]]
                (inner if role == "inner" else outer).append(pts)
        feats.append({"kind": "rel", "id": rid, "tags": tags, "outer": outer, "inner": inner})
    pts = [{"id": nid, "tags": t, "pt": to_local(la, lo)} for nid, (la, lo, t) in nodes.items() if t]
    json.dump({"origin": ORIGIN, "features": feats, "points": pts}, open(os.path.join(DATA, "features.json"), "w"))
    c = Counter()
    for f in feats:
        t = f["tags"]
        key = t.get("golf") and "golf=" + t["golf"] or t.get("building") and "building" or \
            t.get("natural") and "natural=" + t["natural"] or t.get("landuse") and "landuse=" + t["landuse"] or \
            t.get("leisure") and "leisure=" + t["leisure"] or t.get("highway") and "highway" or "other"
        c[key] += 1
    for k, v in c.most_common(40):
        print(v, k)
    pc = Counter((p["tags"].get("natural") or p["tags"].get("golf") or "") for p in pts)
    print("points", pc.most_common(10))
    holes = [f for f in feats if f["tags"].get("golf") == "hole"]
    for h in sorted(holes, key=lambda f: (f["tags"].get("name", ""), int(f["tags"].get("ref", "0") or 0))):
        t = h["tags"]
        print("hole", t.get("ref"), "par", t.get("par"), "name", t.get("name"), "dist", t.get("dist"),
              "len", round(sum(math.dist(a, b) for a, b in zip(h["pts"], h["pts"][1:])) / 0.9144), "yd",
              "start", [round(v) for v in h["pts"][0]])
    for f in feats:
        if f["tags"].get("leisure") == "golf_course":
            print("course", f["kind"], f["id"], f["tags"].get("name"))


if __name__ == "__main__":
    main()
