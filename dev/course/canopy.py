"""Where the real trees are: canopy heights at about 1 m from Meta and the World Resources Institute's global canopy height
map ("High Resolution Canopy Height Maps", Tolan et al. 2024; CC BY 4.0; AWS open data, s3://dataforgood-fb-data/forests/
v1/alsgedi_global_v6_float/chm/<quadkey>.tif). Each file is one zoom-9 Web Mercator quadkey tile: a 65536 x 65536
BigTIFF, one byte per pixel (canopy height in metres), one Deflate-compressed row per strip (horizontal predictor),
EPSG:3857 with 1.194 m pixels (about 1.04 m on the ground at Houston's latitude). Only the rows over the course are
downloaded (HTTP ranges: the strip table, then the strips), so a course costs about 20 MB, not the tile's 600 MB.

python -I canopy.py           -> <course data>/chm.npz (TTMOD_COURSE, as the other scripts)
python -I canopy.py trees     -> how many trees it finds, and their heights

trees() finds the tree tops: local maxima of the (lightly smoothed) heights over a window that grows with the tree's
height, at least MIN_HEIGHT tall, each with a crown radius from the pixels round it still at least half its height.
"""
import math
import os
import struct
import sys
import urllib.request
import zlib

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_data  # noqa: E402
import osm  # noqa: E402

URL = "https://dataforgood-fb-data.s3.amazonaws.com/forests/v1/alsgedi_global_v6_float/chm/{}.tif"
ZOOM = 9
SIZE = 65536                  # pixels a side
WORLD = 20037508.342789244    # Web Mercator half width (m)
PIXEL = 2 * WORLD / 2 ** ZOOM / SIZE
MIN_HEIGHT = 4.0              # m: lower is a bush or noise
OUT = os.path.join(osm.DATA, "chm.npz")


def quadkey(tx, ty, z=ZOOM):
    s = ""
    for i in range(z, 0, -1):
        m = 1 << (i - 1)
        s += str((1 if tx & m else 0) + (2 if ty & m else 0))
    return s


def merc(lat, lon):
    x = math.radians(lon) * 6378137.0
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * 6378137.0
    return x, y


def unmerc(x, y):
    lon = np.degrees(np.asarray(x) / 6378137.0)
    lat = np.degrees(2 * np.arctan(np.exp(np.asarray(y) / 6378137.0)) - np.pi / 2)
    return lat, lon


def _range(url, start, end):
    req = urllib.request.Request(url, headers={"User-Agent": fetch_data.AGENT, "Range": f"bytes={start}-{end}"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def _strips(url):
    """The tile's strip table: (offsets, byte counts), and its origin (Mercator x, y of the top left)."""
    head = _range(url, 0, 65535)
    if head[:4] != b"II+\x00":
        raise SystemExit(f"{url}: not a little-endian BigTIFF")
    off = struct.unpack_from("<Q", head, 8)[0]
    n = struct.unpack_from("<Q", head, off)[0]
    tags = {}
    for i in range(n):
        tag, typ, cnt = struct.unpack_from("<HHQ", head, off + 8 + 20 * i)
        tags[tag] = (typ, cnt, head[off + 8 + 20 * i + 12:off + 8 + 20 * i + 20])
    need = {256: SIZE, 257: SIZE, 258: 8, 259: 8, 317: 2}   # width, height, 8 bits, Deflate, horizontal predictor
    for tag, want in need.items():
        typ, cnt, raw = tags[tag]
        if struct.unpack_from("<I" if typ == 4 else "<H", raw)[0] != want:
            raise SystemExit(f"{url}: tag {tag} isn't {want}")
    o_at = struct.unpack_from("<Q", tags[273][2])[0]
    c_at = struct.unpack_from("<Q", tags[279][2])[0]
    t_at = struct.unpack_from("<Q", tags[33922][2])[0]
    lo = min(o_at, c_at, t_at)
    hi = max(o_at, c_at) + 8 * SIZE
    meta = _range(url, lo, max(hi, t_at + 48))
    offs = np.frombuffer(meta, "<u8", SIZE, o_at - lo)
    cnts = np.frombuffer(meta, "<u8", SIZE, c_at - lo)
    tie = struct.unpack_from("<6d", meta, t_at - lo)
    return offs, cnts, (tie[3], tie[4])


def fetch():
    """Heights over the course's OSM box (fetch_data.AREAS) -> OUT."""
    s, w, n, e = fetch_data.OSM_BOX
    x0, y0 = merc(s, w)
    x1, y1 = merc(n, e)
    # global pixel rows / columns (row 0 at the top of the world)
    c0, c1 = int((x0 + WORLD) / PIXEL), int((x1 + WORLD) / PIXEL) + 1
    r0, r1 = int((WORLD - y1) / PIXEL), int((WORLD - y0) / PIXEL) + 1
    out = np.zeros((r1 - r0, c1 - c0), np.uint8)
    for ty in range(r0 // SIZE, (r1 - 1) // SIZE + 1):
        for tx in range(c0 // SIZE, (c1 - 1) // SIZE + 1):
            url = URL.format(quadkey(tx, ty))
            offs, cnts, origin = _strips(url)
            rows = range(max(r0, ty * SIZE), min(r1, (ty + 1) * SIZE))
            cols = slice(max(c0, tx * SIZE) - tx * SIZE, min(c1, (tx + 1) * SIZE) - tx * SIZE)
            local = [r - ty * SIZE for r in rows]
            start, end = int(offs[local[0]]), int(offs[local[-1]] + cnts[local[-1]])
            print(f"{url.rsplit('/', 1)[1]}: rows {local[0]}-{local[-1]}, {end - start:,} bytes")
            blob = _range(url, start, end - 1)
            for r, lr in zip(rows, local):
                a = int(offs[lr]) - start
                row = np.frombuffer(zlib.decompress(blob[a:a + int(cnts[lr])]), np.uint8)
                row = np.cumsum(row, dtype=np.uint64).astype(np.uint8)   # horizontal predictor: running sum mod 256
                out[r - r0, max(c0, tx * SIZE) - c0:min(c1, (tx + 1) * SIZE) - c0] = row[cols]
    np.savez_compressed(OUT, chm=out, x0=-WORLD + c0 * PIXEL, y0=WORLD - r0 * PIXEL, pixel=PIXEL)
    print(f"{OUT}: {out.shape[1]} x {out.shape[0]} pixels, {int((out >= MIN_HEIGHT).sum()):,} at {MIN_HEIGHT:g} m or more")


def load():
    d = np.load(OUT)
    return d["chm"], float(d["x0"]), float(d["y0"]), float(d["pixel"])


def to_local_xy(mx, my):
    lat, lon = unmerc(mx, my)
    x = np.radians(lon - osm.ORIGIN[1]) * osm.R * math.cos(math.radians(osm.ORIGIN[0]))
    y = np.radians(lat - osm.ORIGIN[0]) * osm.R
    return x, y


def trees(min_height=MIN_HEIGHT):
    """[(x, y, height m, crown radius m)] in osm's local frame (x east, y north)."""
    from scipy import ndimage
    chm, x0, y0, px = load()
    h = ndimage.gaussian_filter(chm.astype(np.float32), 0.8)
    ground_m = px * math.cos(math.radians(osm.ORIGIN[0]))     # a pixel on the ground
    peaks = np.zeros(h.shape, bool)
    # the window grows with the tree: small trees 5 m apart, tall ones 9 m (crowns are wider than they are close)
    for lo, hi, size_m in ((min_height, 10, 5.0), (10, 18, 7.0), (18, 999, 9.0)):
        size = max(3, int(round(size_m / ground_m)) | 1)
        mx = ndimage.maximum_filter(h, size=size)
        peaks |= (h == mx) & (h >= lo) & (h < hi)
    rr, cc = np.nonzero(peaks)
    out = []
    for r, c in zip(rr, cc):
        top = float(h[r, c])
        k = int(round(6 / ground_m))
        win = h[max(0, r - k):r + k + 1, max(0, c - k):c + k + 1]
        crown = (win >= top * 0.5).sum() * ground_m ** 2
        out.append((c + 0.5, r + 0.5, top, math.sqrt(crown / math.pi)))
    if not out:
        return []
    a = np.array(out)
    x, y = to_local_xy(x0 + a[:, 0] * px, y0 - a[:, 1] * px)
    return [(float(xx), float(yy), float(t), float(cr)) for xx, yy, t, cr in zip(x, y, a[:, 2], a[:, 3])]


if __name__ == "__main__":
    if sys.argv[1:] == ["trees"]:
        t = trees()
        hs = np.array([q[2] for q in t])
        print(f"{len(t)} trees; height median {np.median(hs):.1f} m, 90% {np.percentile(hs, 90):.1f} m; "
              f"crown radius median {np.median([q[3] for q in t]):.1f} m")
    else:
        fetch()
