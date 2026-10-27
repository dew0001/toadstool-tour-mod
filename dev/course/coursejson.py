"""Write <course folder>/course.json for build_mod.py --course8 and make_patch.py --course8: the 18 holes in
order (card yards, back-tee yards, par and the three files each: E/<hole letter>/A model, B collision,
C flyover), the files to put on the disc, and how make_patch finds the game bytes in them (provenance for the
models, a search of Cheep Cheep Falls' collision file for the tree meshes in the collision files).
--partial: holes not generated yet borrow the first generated hole's files (for testing)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pebble  # noqa: E402

folder = sys.argv[1]
partial = "--partial" in sys.argv


def files_of(n):
    letter = chr(64 + n)
    paths = {k: f"E/{letter}/{f}" for k, f in (("model", "A"), ("collision", "B"), ("flyover", "C"))}
    ok = all(os.path.exists(os.path.join(folder, *p.split("/"))) for p in paths.values())
    return paths if ok else None


done = {n: files_of(n) for n in range(1, 19) if files_of(n)}
missing = [n for n in range(1, 19) if n not in done]
if missing and not partial:
    raise SystemExit(f"holes not generated yet: {missing}")
if not done:
    raise SystemExit("no holes generated yet")
first = done[min(done)]
spec = {"name": "Pebble Beach", "holes": [], "files": {},
        "patch": {"E/S/A": {"search": ["files/A/X/K"]}, "E/S/B": {"search": ["files/C/O/U"]},   # card, emblem
                  "E/[A-R]/A": {"prov": True}, "E/[A-R]/B": {"search": ["files/A/Y/J"]}, "E/[A-R]/C": {}}}
for n in range(1, 19):
    f = done.get(n, first)
    yards, back, par = pebble.CARD[n]
    spec["holes"].append({"hole": n, "yards": yards, "back": back, "par": par, **f})
    for p in f.values():
        spec["files"][p] = p
json.dump(spec, open(os.path.join(folder, "course.json"), "w"), indent=1)
print(f"course.json: {len(done)} holes generated" + (f", {missing} borrowed" if missing else ""))
