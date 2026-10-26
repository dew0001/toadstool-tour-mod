"""Toadstool Tour texture files and GameCube texture formats.

Texture file (magic 0x0020AF30, the same layout as a model's texture set at root +0x8C):
  +0 magic  +4 count  +8 0xC  +0xC count x (header offset, 0)
  header (0x24): +0 height << 16 | width  +4 format  +8 data offset (from the file start)  +0xC wrap S  +0x10 wrap T
                 ... +0x20 max LOD << 8
Formats handled: 5 RGB5A3, 14 CMPR (decode and encode), 4 RGB565, 6 RGBA8, 0 I4, 1 I8, 2 IA4, 3 IA8 (decode).
Usage: python -I textures.py <packed or decoded texture file> <out folder>   (writes each texture as PNG)
"""
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import camelot_lz as lz  # noqa: E402

MAGIC = 0x0020AF30
BLOCK = {0: (8, 8, 4), 1: (8, 4, 8), 2: (8, 4, 8), 3: (4, 4, 16), 4: (4, 4, 16), 5: (4, 4, 16), 6: (4, 4, 32),
         14: (8, 8, 4)}   # format -> (block width, block height, bits per pixel)


def u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def headers(blob, base=0):
    """[(header offset, width, height, format, data offset, max LOD)] of a texture set at `base`."""
    out = []
    for i in range(u32(blob, base + 4)):
        h = base + u32(blob, base + 0xC + 8 * i)
        out.append((h, u32(blob, h) & 0xFFFF, u32(blob, h) >> 16, u32(blob, h + 4), u32(blob, h + 8),
                    u32(blob, h + 0x20) >> 8))
    return out


def level_size(w, h, fmt):
    bw, bh, bpp = BLOCK[fmt]
    return ((w + bw - 1) // bw) * ((h + bh - 1) // bh) * bw * bh * bpp // 8


def rgb5a3(v):
    v = v.astype(np.int64)
    opaque = (v & 0x8000) != 0
    r = np.where(opaque, ((v >> 10) & 31) * 255 // 31, ((v >> 8) & 15) * 17)
    g = np.where(opaque, ((v >> 5) & 31) * 255 // 31, ((v >> 4) & 15) * 17)
    b = np.where(opaque, (v & 31) * 255 // 31, (v & 15) * 17)
    a = np.where(opaque, 255, ((v >> 12) & 7) * 255 // 7)
    return np.stack([r, g, b, a], -1)


def decode(data, w, h, fmt):
    """One level as an (h, w, 4) uint8 RGBA array."""
    bw, bh, bpp = BLOCK[fmt]
    bx, by = (w + bw - 1) // bw, (h + bh - 1) // bh
    out = np.zeros((by * bh, bx * bw, 4), np.uint8)
    o = 0
    for ty in range(by):
        for tx in range(bx):
            if fmt == 14:
                for sy, sx in ((0, 0), (0, 4), (4, 0), (4, 4)):
                    c0, c1 = struct.unpack_from(">HH", data, o)
                    e = [((c >> 11) & 31, (c >> 5) & 63, c & 31) for c in (c0, c1)]
                    e = [np.array([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2), 255]) for r, g, b in e]
                    if c0 > c1:
                        pal = [e[0], e[1], (5 * e[0] + 3 * e[1]) // 8, (3 * e[0] + 5 * e[1]) // 8]
                    else:
                        pal = [e[0], e[1], (e[0] + e[1]) // 2, np.zeros(4, np.int64)]
                    for row in range(4):
                        byte = data[o + 4 + row]
                        for col in range(4):
                            out[ty * 8 + sy + row, tx * 8 + sx + col] = pal[(byte >> (6 - 2 * col)) & 3]
                    o += 8
            elif fmt == 6:
                ar = np.frombuffer(data, np.uint8, 32, o).reshape(16, 2)
                gb = np.frombuffer(data, np.uint8, 32, o + 32).reshape(16, 2)
                px = np.stack([ar[:, 1], gb[:, 0], gb[:, 1], ar[:, 0]], -1).reshape(4, 4, 4)
                out[ty * 4:ty * 4 + 4, tx * 4:tx * 4 + 4] = px
                o += 64
            else:
                n = bw * bh * bpp // 8
                raw = np.frombuffer(data, np.uint8, n, o)
                if fmt in (4, 5):
                    v = raw.view(">u2").astype(np.int64)
                    if fmt == 5:
                        px = rgb5a3(v)
                    else:
                        px = np.stack([((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31,
                                       np.full_like(v, 255)], -1)
                elif fmt == 0:
                    v = np.stack([raw >> 4, raw & 15], -1).reshape(-1).astype(np.int64) * 17
                    px = np.stack([v, v, v, np.full_like(v, 255)], -1)
                elif fmt == 1:
                    v = raw.astype(np.int64)
                    px = np.stack([v, v, v, np.full_like(v, 255)], -1)
                elif fmt == 2:
                    i, a = (raw & 15).astype(np.int64) * 17, (raw >> 4).astype(np.int64) * 17
                    px = np.stack([i, i, i, a], -1)
                else:   # 3 IA8
                    a, i = raw[0::2].astype(np.int64), raw[1::2].astype(np.int64)
                    px = np.stack([i, i, i, a], -1)
                out[ty * bh:(ty + 1) * bh, tx * bw:(tx + 1) * bw] = px.reshape(bh, bw, 4)
                o += n
    return out[:h, :w]


def encode_rgb5a3(img):
    """(h, w, 4) RGBA -> RGB5A3 bytes (opaque pixels as RGB555, the rest as ARGB3444)."""
    h, w = img.shape[:2]
    th, tw = -(-h // 4) * 4, -(-w // 4) * 4
    img = np.pad(img.astype(np.int64), ((0, th - h), (0, tw - w), (0, 0)), mode="edge")
    r, g, b, a = (img[..., k] for k in range(4))
    opaque = (1 << 15) | ((r * 31 + 127) // 255 << 10) | ((g * 31 + 127) // 255 << 5) | ((b * 31 + 127) // 255)
    clear = ((a * 7 + 127) // 255 << 12) | ((r * 15 + 127) // 255 << 8) | ((g * 15 + 127) // 255 << 4) | ((b * 15 + 127) // 255)
    v = np.where(a >= 0xF8, opaque, clear).astype(">u2")
    tiles = v.reshape(th // 4, 4, tw // 4, 4).transpose(0, 2, 1, 3)
    return tiles.tobytes()


def put_rgb5a3(blob, at, width, x0, y0, img):
    """Write an RGBA picture into an RGB5A3 texture (data at `at`, `width` wide) at x0, y0 (multiples of 4)."""
    h, w = img.shape[:2]
    if x0 % 4 or y0 % 4 or w % 4 or h % 4:
        raise ValueError("RGB5A3 regions go by whole 4x4 tiles")
    tiles = encode_rgb5a3(img)
    for ty in range(h // 4):
        for tx in range(w // 4):
            src = (ty * (w // 4) + tx) * 32
            dst = at + (((y0 // 4) + ty) * (width // 4) + (x0 // 4) + tx) * 32
            blob[dst:dst + 32] = tiles[src:src + 32]


def load_bytes(raw):
    """A texture file's contents, decoded if it's packed."""
    return lz.decompress(raw)[0] if raw[0] in (1, 2) and u32(raw, 0) != MAGIC else raw


def load(path):
    return load_bytes(open(path, "rb").read())


def main():
    from PIL import Image
    blob = load(sys.argv[1])
    out = sys.argv[2]
    os.makedirs(out, exist_ok=True)
    name = os.path.basename(sys.argv[1])
    for k, (h, w, ht, fmt, at, lod) in enumerate(headers(blob)):
        img = decode(blob[at:at + level_size(w, ht, fmt)], w, ht, fmt)
        Image.fromarray(img).save(os.path.join(out, f"{name}_{k}.png"))
        print(f"{k}: {w}x{ht} format {fmt} at 0x{at:X}, {lod + 1} levels")


if __name__ == "__main__":
    main()
