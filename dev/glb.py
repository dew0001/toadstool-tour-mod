"""Minimal glTF 2.0 binary (.glb) reader: JSON, accessors as numpy arrays, embedded images, node world matrices."""
import json
import struct

import numpy as np

COMPONENT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


class Glb:
    def __init__(self, path):
        b = open(path, "rb").read()
        magic, _, _ = struct.unpack_from("<III", b, 0)
        if magic != 0x46546C67:
            raise SystemExit(f"{path} isn't a .glb file")
        jlen = struct.unpack_from("<I", b, 12)[0]
        self.g = json.loads(b[20:20 + jlen])
        o = 20 + jlen
        blen = struct.unpack_from("<I", b, o)[0]
        self.bin = b[o + 8:o + 8 + blen]

    def view(self, i):
        v = self.g["bufferViews"][i]
        start = v.get("byteOffset", 0)
        return self.bin[start:start + v["byteLength"]], v.get("byteStride")

    def accessor(self, i):
        """Accessor i as a (count, width) array (floats for float and normalized data)."""
        a = self.g["accessors"][i]
        data, stride = self.view(a["bufferView"])
        dt = np.dtype(COMPONENT[a["componentType"]]).newbyteorder("<")
        n = WIDTH[a["type"]]
        off = a.get("byteOffset", 0)
        if stride and stride != n * dt.itemsize:
            arr = np.ndarray((a["count"], n), dt, data, off, (stride, dt.itemsize))
        else:
            arr = np.frombuffer(data, dt, a["count"] * n, off).reshape(a["count"], n)
        if a.get("normalized"):
            return arr.astype(np.float64) / np.iinfo(COMPONENT[a["componentType"]]).max
        return arr.astype(np.float64) if a["componentType"] == 5126 else arr.astype(np.int64)

    def image(self, i):
        """Bytes of embedded image i (PNG or JPEG)."""
        return self.view(self.g["images"][i]["bufferView"])[0]

    def joint_binds(self, skin=0):
        """[(joint node name, bind-pose world position)] of a skin's joints, from its inverse bind matrices."""
        s = self.g["skins"][skin]
        ibm = self.accessor(s["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1)
        return [(self.g["nodes"][j].get("name", str(j)), np.linalg.inv(m)[:3, 3]) for j, m in zip(s["joints"], ibm)]
