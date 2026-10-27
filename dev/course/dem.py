"""Elevation (metres above sea level) from the terrarium tiles in pebble-data/dem15 (fine, course) and dem11
(coarse, the mountains round the bay), sampled in the local metric frame of osm.py."""
import glob
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PIL import Image

import osm

DATA = osm.DATA


class Mosaic:
    def __init__(self, folder):
        tiles = {}
        for p in glob.glob(os.path.join(DATA, folder, "*.png")):
            z, x, y = (int(v) for v in os.path.basename(p)[:-4].split("_"))
            a = np.asarray(Image.open(p).convert("RGB")).astype(np.float64)
            tiles[(x, y)] = a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768
        self.z = z
        xs = sorted({k[0] for k in tiles})
        ys = sorted({k[1] for k in tiles})
        self.tx0, self.ty0 = xs[0], ys[0]
        self.img = np.zeros((256 * len(ys), 256 * len(xs)))
        for (x, y), a in tiles.items():
            self.img[(y - ys[0]) * 256:(y - ys[0] + 1) * 256, (x - xs[0]) * 256:(x - xs[0] + 1) * 256] = a

    def sample(self, x, y):
        """Bilinear elevation at local metres (arrays) in pebble.Course's frame: x east, y south."""
        lat, lon = osm.to_latlon(np.asarray(x, np.float64), -np.asarray(y, np.float64))
        n = 2 ** self.z
        px = ((lon + 180) / 360 * n - self.tx0) * 256 - 0.5
        lat_r = np.radians(lat)
        py = ((1 - np.arcsinh(np.tan(lat_r)) / math.pi) / 2 * n - self.ty0) * 256 - 0.5
        h, w = self.img.shape
        px = np.clip(px, 0, w - 1.001)
        py = np.clip(py, 0, h - 1.001)
        x0, y0 = np.floor(px).astype(int), np.floor(py).astype(int)
        fx, fy = px - x0, py - y0
        a = self.img[y0, x0]
        b = self.img[y0, x0 + 1]
        c = self.img[y0 + 1, x0]
        d = self.img[y0 + 1, x0 + 1]
        return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


_fine = _coarse = None


def fine():
    global _fine
    if _fine is None:
        _fine = Mosaic("dem15")
    return _fine


def coarse():
    global _coarse
    if _coarse is None:
        _coarse = Mosaic("dem11")
    return _coarse
