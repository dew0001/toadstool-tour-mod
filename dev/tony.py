"""Tony the Tiger as golfer 17, the second golfer on the select screen's extra ("More") page, next to Shy Guy.

His model is a rigged Blender export (.glb: one skinned mesh in parts, two 1024x1024 colour maps, plain colours for
the rest). Golfer 17 moves with another golfer's animations (BASE), so his mesh is fitted to that golfer's
skeleton: Tony's own bones are grouped into body segments (SEGMENTS), each segment is moved onto the base's matching
bones (rotated from his A pose into the game's T pose and stretched to the base's bone lengths), and the moves are
blended with his own skin weights so the joints stay smooth. The mesh is simplified to a GameCube-sized one first,
with every corner's texture coordinate and weights sampled back from the original surface.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

import glb as glbmod
import model as mdl

GLB = os.path.join("source", "untitled.glb")

# Tony's bones (names without Blender's "_NNN" suffix) -> body segment. Unlisted bones go by prefix in FACE_PREFIX
# (the head) or FINGER_PREFIX (the hand on their side).
SEGMENTS = {
    "root.x": "pelvis", "spine_01.x": "pelvis", "c_tail_00.x": "pelvis", "c_tail_01.x": "pelvis",
    "c_tail_02.x": "pelvis", "c_tail_03.x": "pelvis",
    "spine_02.x": "spine", "c_spine_02_bend.x": "spine",
    "spine_03.x": "chest", "c_spine_03.x": "chest", "c_spine_03_bend.x": "chest",
    "neck.x": "neck", "head.x": "head",
}
for _s in ("l", "r"):
    SEGMENTS.update({f"shoulder.{_s}": f"clav.{_s}", f"c_arm_twist_offset.{_s}": f"upper.{_s}",
                     f"arm_stretch.{_s}": f"upper.{_s}", f"forearm_stretch.{_s}": f"fore.{_s}",
                     f"forearm_twist.{_s}": f"fore.{_s}", f"hand.{_s}": f"hand.{_s}",
                     f"thigh_twist.{_s}": f"thigh.{_s}", f"thigh_stretch.{_s}": f"thigh.{_s}",
                     f"leg_stretch.{_s}": f"shin.{_s}", f"leg_twist.{_s}": f"shin.{_s}",
                     f"foot.{_s}": f"foot.{_s}", f"toes_01.{_s}": f"toe.{_s}"})
# His fingers: three joints each (thumb1, c_thumb2, c_thumb3; index1, c_index2, c_index3, ...), each its own
# segment ("index2.l"), so they close round the grip with the base's finger bones; the c_*1_base bones are the palm.
FINGERS = ("thumb", "index", "middle", "ring", "pinky")
FINGER_JOINTS = {f: (f"{f}1", f"c_{f}2", f"c_{f}3") for f in FINGERS}
for _s in ("l", "r"):
    for _f, _names in FINGER_JOINTS.items():
        SEGMENTS.update({f"{n}.{_s}": f"{_f}{k + 1}.{_s}" for k, n in enumerate(_names)})
        SEGMENTS[f"c_{_f}1_base.{_s}"] = f"hand.{_s}"
FACE_PREFIX = ("jawbone", "c_lips", "c_teeth", "tong", "c_chin", "c_nose", "c_eye", "c_cheek", "c_ear")
FINGER_PREFIX = ("c_pinky", "pinky", "c_ring", "ring", "c_middle", "middle", "c_index", "index", "thumb", "c_thumb")

# Tony's joints (bone heads, bind pose) that place the segments: (start bone, end bone or None).
LIMBS = {"clav": ("shoulder", "c_arm_twist_offset"), "upper": ("c_arm_twist_offset", "forearm_stretch"),
         "fore": ("forearm_stretch", "hand"), "hand": ("hand", "middle1"),
         "thigh": ("thigh_twist", "leg_stretch"), "shin": ("leg_stretch", "foot"), "foot": ("foot", "toes_01")}

# Bases: golfer code, its in-round model, and its bones for each segment (C/x/x numbers; side: +x = .l).
BASES = {
    "wario": {"golfer": 5, "model": "C/T/G", "pelvis": 104, "spine": 4, "chest": 5, "neck": 6, "head": 8,
              "clav": (38, 57), "upper": (39, 58), "fore": (40, 59), "hand": (41, 60), "hand_tip": (53, 72),
              "thigh": (107, 115), "shin": (108, 116), "foot": (109, 117), "toe": (110, 118)},
    "luigi": {"golfer": 3, "model": "C/S/S", "pelvis": 113, "spine": 16, "chest": 17, "neck": 18, "head": 18,
              "clav": (94, 44), "upper": (95, 45), "fore": (96, 46), "hand": (97, 47), "hand_tip": (103, 53),
              "thigh": (116, 124), "shin": (117, 125), "foot": (118, 126), "toe": (119, 127)},
    "waluigi": {"golfer": 1, "model": "C/S/C", "hide_parts": (7,),     # part 7: the buttons on his overalls
                "pelvis": 3, "spine": 22, "chest": 22, "neck": 23, "head": 24,
                "clav": (47, 66), "upper": (48, 67), "fore": (49, 68), "hand": (50, 69), "hand_tip": (59, 78),
                "thigh": (5, 13), "shin": (6, 14), "foot": (7, 15), "toe": (8, 16),
                # his fingers' three bones (left, right), told apart by how far forward they sit in the T pose
                "fingers": {"thumb": ((51, 52, 53), (70, 71, 72)), "index": ((60, 61, 62), (79, 80, 81)),
                            "middle": ((57, 58, 59), (76, 77, 78)), "ring": ((54, 55, 56), (73, 74, 75)),
                            "pinky": ((63, 64, 65), (82, 83, 84))}},
}
HEAD_SCALE = 1.4      # Tony's head bigger than his body's scale (the cast all have big heads)
HAND_SCALE = 1.4      # and his paws (thickness; with finger bones the palm and fingers take the base's lengths, so
                      # they close round the grip where the base's do)
THICKNESS = {"clav": 1.2, "upper": 1.5, "fore": 1.5, "thigh": 1.7, "shin": 1.7, "foot": 1.3}
                      # arms and legs thicker than the torso's scale: stretched to the base's long limbs they
                      # would otherwise look thin
TORSO_WIDTH = 1.2     # and his chest and hips broader (across and front to back)


def bone_name(n):
    head, _, tail = n.rpartition("_")
    return head if tail.isdigit() else n


def segment_of(name):
    n = bone_name(name)
    if n in SEGMENTS:
        return SEGMENTS[n]
    side = n.rsplit(".", 1)[-1]
    if n.startswith(FINGER_PREFIX) and side in ("l", "r"):
        return f"hand.{side}"
    if n.startswith(FACE_PREFIX):
        return "head"
    return None


class Tony:
    """The .glb's parts: per primitive positions, normals, UVs (TEXCOORD_0), material and segment weights."""

    def __init__(self, folder):
        self.g = glbmod.Glb(os.path.join(folder, GLB))
        g = self.g.g
        joints = self.g.joint_binds()
        self.joint = {bone_name(n): p for n, p in joints}
        names = [n for n, _ in joints]
        segs = sorted({s for s in (segment_of(n) for n in names) if s})
        self.segments = segs
        seg_of_joint = np.array([segs.index(segment_of(n)) if segment_of(n) else -1 for n in names])
        unmapped = sorted({bone_name(n) for n in names if not segment_of(n)})
        self.parts = []
        for mi, m in enumerate(g["meshes"]):
            for p in m["primitives"]:
                a = p["attributes"]
                pos = self.g.accessor(a["POSITION"])
                J, W = self.g.accessor(a["JOINTS_0"]), self.g.accessor(a["WEIGHTS_0"])
                sw = np.zeros((len(pos), len(segs)))
                for k in range(J.shape[1]):
                    s = seg_of_joint[J[:, k]]
                    ok = s >= 0
                    np.add.at(sw, (np.nonzero(ok)[0], s[ok]), W[ok, k])
                lost = sw.sum(1) < 1e-6
                if lost.any():
                    bad = {bone_name(names[j]) for j in np.unique(J[lost])}
                    raise SystemExit(f"Tony: vertices weighted only to unmapped bones {sorted(bad)[:8]}")
                sw /= sw.sum(1, keepdims=True)
                self.parts.append({"mesh": mi, "material": p.get("material", 0), "pos": pos,
                                   "uv": self.g.accessor(a["TEXCOORD_0"]),
                                   "tris": self.g.accessor(p["indices"]).reshape(-1, 3), "weights": sw})
        self.unmapped = unmapped

    def material_colour(self, mat):
        """(texture image or None, plain RGB) of a material."""
        m = self.g.g["materials"][mat]
        pbr = m.get("pbrMetallicRoughness", {})
        if "baseColorTexture" in pbr:
            src = self.g.g["textures"][pbr["baseColorTexture"]["index"]]["source"]
            img = Image.open(io.BytesIO(self.g.image(src))).convert("RGB")
            return img, np.asarray(img, np.float64).reshape(-1, 3).mean(0)
        f = pbr.get("baseColorFactor", [0.8, 0.8, 0.8, 1])
        return None, np.clip(np.array(f[:3]) ** (1 / 2.2) * 255, 0, 255)


# ---------------------------------------------------------------- fitting

def rotation_between(a, b):
    """Smallest rotation taking unit vector a to unit vector b."""
    a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
    v, c = np.cross(a, b), float(a @ b)
    if c < -0.999999:
        axis = np.cross(a, [1, 0, 0]) if abs(a[0]) < 0.9 else np.cross(a, [0, 1, 0])
        axis /= np.linalg.norm(axis)
        return 2 * np.outer(axis, axis) - np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx / (1 + c)


def limb_transform(a_t, b_t, a_w, b_w, across):
    """(3x3, offset) taking Tony's segment a_t->b_t onto the base's a_w->b_w: stretched along it to the base's length,
    scaled by `across` across it."""
    d = b_t - a_t
    u = d / np.linalg.norm(d)
    along = np.linalg.norm(b_w - a_w) / np.linalg.norm(d)
    S = across * np.eye(3) + (along - across) * np.outer(u, u)
    M = rotation_between(d, b_w - a_w) @ S
    return M, a_w - M @ a_t


def base_joints(base, m):
    """Base bone -> bind-pose position for model m (its numbering)."""
    return {i: np.array((w[3], w[7], w[11])) for i, w in enumerate(mdl.world_bind(m))}


def fit_transforms(tony, base, joints, bone_of=lambda b: b):
    """Segment -> (3x3, offset) moving Tony onto a base model whose bone b sits at joints[bone_of(b)]."""
    J = lambda b: joints[bone_of(b)]
    t = tony.joint
    hip_t = (t["thigh_twist.l"] + t["thigh_twist.r"]) / 2
    hip_w = (J(base["thigh"][0]) + J(base["thigh"][1])) / 2
    sh_t = (t["c_arm_twist_offset.l"] + t["c_arm_twist_offset.r"]) / 2
    sh_w = (J(base["upper"][0]) + J(base["upper"][1])) / 2
    scale = (sh_w[1] - hip_w[1]) / (sh_t[1] - hip_t[1])        # the torso: hips to shoulders
    S = scale * np.diag([TORSO_WIDTH, 1, TORSO_WIDTH])
    torso = (S, hip_w - S @ hip_t)
    out = {s: torso for s in ("pelvis", "spine", "chest")}
    neck_t = t["neck.x"]
    neck_w = torso[0] @ neck_t + torso[1]
    hs = scale * HEAD_SCALE
    out["neck"] = out["head"] = (hs * np.eye(3), neck_w - hs * neck_t)
    for side, k in (("l", 0), ("r", 1)):
        for seg, (a, b) in LIMBS.items():
            a_t, b_t = t[f"{a}.{side}"], t[f"{b}.{side}"]
            a_w = J(base[seg][k])
            nxt = {"clav": "upper", "upper": "fore", "fore": "hand", "hand": "hand_tip", "thigh": "shin",
                   "shin": "foot", "foot": "toe"}[seg]
            b_w = J(base[nxt][k])
            if seg == "hand" and "fingers" in base:
                # the palm, wrist to middle knuckle, onto the base's
                b_w = J(base["fingers"]["middle"][k][0])
                out[f"{seg}.{side}"] = limb_transform(a_t, b_t, a_w, b_w, scale * HAND_SCALE)
            elif seg == "hand":
                # no finger bones: his paw at its own length (scaled), pointing the way the base's hand does
                d = J(base["hand_tip"][k]) - a_w
                b_w = a_w + d / np.linalg.norm(d) * np.linalg.norm(t[f"c_middle3.{side}"] - a_t) * scale * HAND_SCALE
                out[f"{seg}.{side}"] = limb_transform(a_t, b_t, a_w, b_w, scale * HAND_SCALE)
            else:
                out[f"{seg}.{side}"] = limb_transform(a_t, b_t, a_w, b_w, scale * THICKNESS[seg])
        out[f"toe.{side}"] = out[f"foot.{side}"]
        for f, names in FINGER_JOINTS.items():
            if "fingers" not in base:
                for k3 in range(3):
                    out[f"{f}{k3 + 1}.{side}"] = out[f"hand.{side}"]
                continue
            jt = [t[f"{n}.{side}"] for n in names]
            jt.append(jt[2] + (jt[2] - jt[1]))            # the fingertip: one more joint's length on
            jw = [J(b) for b in base["fingers"][f][k]]
            jw.append(jw[2] + (jw[2] - jw[1]))
            for k3 in range(3):
                out[f"{f}{k3 + 1}.{side}"] = limb_transform(jt[k3], jt[k3 + 1], jw[k3], jw[k3 + 1],
                                                            scale * HAND_SCALE)
    return out, scale


def fit_points(pos, weights, segments, transforms):
    """Blend each segment's transform by the vertex's segment weights."""
    out = np.zeros_like(pos)
    for k, s in enumerate(segments):
        M, o = transforms[s]
        out += weights[:, k:k + 1] * (pos @ M.T + o)
    return out


def segment_bone(base, seg):
    name, _, side = seg.partition(".")
    k = 0 if side == "l" else 1
    if name[:-1] in FINGERS:
        return base["fingers"][name[:-1]][k][int(name[-1]) - 1] if "fingers" in base else base["hand"][k]
    b = base[name]
    return b[k] if side else b


# ---------------------------------------------------------------- simplifying and texturing

# (group, materials, triangles to keep). Materials in no group are left out: 0 the inside of his mouth, 2 the
# glints in his eyes (a few millimetres across).
GROUPS = [("body", (4, 5), 2900), ("bandana", (3,), 650), ("brows", (6,), 450), ("eyes", (7,), 150),
          ("pupils", (1,), 80)]   # the bandana is cloth with thickness: much under 600 triangles it caves in
PIECEWISE = ("brows",)   # simplified one connected piece at a time; a piece that won't simplify (the whiskers and
                         # the lines round his muzzle are open tubes) becomes a plain tube along its middle
TUBE = (8, 3)            # segments and sides of such a tube
DOUBLE_SIDED = ()             # groups of one-layer surfaces (the GameCube draws one side of a triangle)
ON_BODY = ("bandana",)        # moves with the skin under it (his rig ties it to the chest alone, so the neck
LIFT = 0.02                   # moved over it) and sits this far off it (his units, ~2.8 tall)
ATLAS = (512, 256)                                          # one texture for all of him: the two colour maps
TEXTURED = {4: (0, 0, 256, 240), 5: (256, 0, 256, 240)}    # side by side, (x, y, w, h) each,
PLAIN = (3, 6, 7, 1)                                        # and swatches along the bottom for plain materials
SWATCH = 16
INSET = 2                                                   # texels kept clear of a map's edge (mip levels blur)


def weld(pos, tris, tol=1e-6):
    """Merge positions closer than tol: (positions, triangles on them)."""
    key = np.round(pos / tol).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    return pos[first], inv.reshape(-1)[tris]


def closest_on_triangles(p, a, b, c):
    """Closest point of triangles (a, b, c) to points p, all (n, 3): (barycentric (n, 3), distance (n,))."""
    ab, ac = b - a, c - a
    n = np.cross(ab, ac)
    nn = np.maximum((n * n).sum(1), 1e-30)
    q = p - (((p - a) * n).sum(1) / nn)[:, None] * n
    d00, d01, d11 = (ab * ab).sum(1), (ab * ac).sum(1), (ac * ac).sum(1)
    aq = q - a
    d20, d21 = (aq * ab).sum(1), (aq * ac).sum(1)
    den = np.maximum(d00 * d11 - d01 * d01, 1e-30)
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    bary = np.stack([1 - v - w, v, w], 1)
    inside = (bary >= 0).all(1)
    best = np.where(inside, np.linalg.norm(p - q, axis=1), np.inf)
    out = np.where(inside[:, None], bary, 0)
    for i, j in ((0, 1), (1, 2), (2, 0)):
        s0, s1 = (a, b, c)[i], (a, b, c)[j]
        e = s1 - s0
        t = np.clip(((p - s0) * e).sum(1) / np.maximum((e * e).sum(1), 1e-30), 0, 1)
        d = np.linalg.norm(p - (s0 + t[:, None] * e), axis=1)
        better = ~inside & (d < best)
        best = np.where(better, d, best)
        edge = np.zeros_like(bary)
        edge[:, i], edge[:, j] = 1 - t, t
        out = np.where(better[:, None], edge, out)
    return out, best


class Surface:
    """The original triangles of a group, for finding the nearest point's triangle and barycentric coordinates."""

    def __init__(self, tri_pos, mats, k=16):
        self.T, self.k = tri_pos, k
        self.trees = {None: (cKDTree(tri_pos.mean(1)), np.arange(len(tri_pos)))}
        for m in np.unique(mats):
            sel = np.nonzero(mats == m)[0]
            self.trees[int(m)] = (cKDTree(tri_pos[sel].mean(1)), sel)

    def nearest(self, pts, mat=None):
        """(triangle index, barycentric) of the nearest point of the surface (of material mat) to each point."""
        tree, ids = self.trees[mat]
        k = min(self.k, len(ids))
        _, cand = tree.query(pts, k=k)
        cand = ids[np.asarray(cand).reshape(len(pts), k)]
        T = self.T[cand.reshape(-1)]
        bary, dist = closest_on_triangles(np.repeat(pts, k, axis=0), T[:, 0], T[:, 1], T[:, 2])
        dist, bary = dist.reshape(len(pts), k), bary.reshape(len(pts), k, 3)
        pick = dist.argmin(1)
        r = np.arange(len(pts))
        return cand[r, pick], bary[r, pick]


def atlas_uv(mat, uv):
    """A material's texture coordinates in the atlas (0..1, v down like the GameCube's)."""
    W, H = ATLAS
    if mat in TEXTURED:
        x, y, w, h = TEXTURED[mat]
        u, v = np.clip(uv[..., 0], 0, 1), np.clip(uv[..., 1], 0, 1)
        return np.stack([(x + INSET + u * (w - 2 * INSET)) / W, (y + INSET + v * (h - 2 * INSET)) / H], -1)
    k = PLAIN.index(mat)
    centre = np.array([(k * SWATCH + SWATCH / 2) / W, (H - SWATCH / 2) / H])
    return np.broadcast_to(centre, uv.shape).copy()


def atlas_image(tony):
    """The atlas as an RGB image (ATLAS size)."""
    W, H = ATLAS
    img = np.zeros((H, W, 3))
    for mat, (x, y, w, h) in TEXTURED.items():
        tex, _ = tony.material_colour(mat)
        img[y:y + h, x:x + w] = np.asarray(tex.resize((w, h), Image.LANCZOS), np.float64)
    img[H - SWATCH:, :] = tony.material_colour(min(TEXTURED))[1]      # under and beside the swatches: fur
    for k, mat in enumerate(PLAIN):
        img[H - SWATCH:, k * SWATCH:(k + 1) * SWATCH] = tony.material_colour(mat)[1]
    return Image.fromarray(np.clip(np.round(img), 0, 255).astype(np.uint8))


def decimate(pos, tris, keep):
    import fast_simplification
    if len(tris) <= keep:
        return pos, tris
    p, t = fast_simplification.simplify(pos.astype(np.float32), tris.astype(np.int32),
                                        target_reduction=1 - keep / len(tris))
    return p.astype(np.float64), t


def pieces(pos, tris):
    """[(positions, triangles)] of each connected piece."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    n = len(pos)
    e = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]]])
    _, lab = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n)), directed=False)
    out = []
    for c in np.unique(lab[tris[:, 0]]):
        sel = tris[lab[tris[:, 0]] == c]
        used = np.unique(sel)
        remap = np.full(n, -1)
        remap[used] = np.arange(len(used))
        out.append((pos[used], remap[sel]))
    return out


def tube(P, segments, sides):
    """A plain tube along a thin piece's middle: (positions, triangles)."""
    c = P.mean(0)
    axis = np.linalg.svd(P - c, full_matrices=False)[2][0]
    t = (P - c) @ axis
    edges = np.linspace(t.min(), t.max(), segments + 1)
    mid = [P[(t >= edges[i]) & (t <= edges[i + 1])].mean(0) for i in range(segments)
           if ((t >= edges[i]) & (t <= edges[i + 1])).any()]
    line = np.array([P[t.argmin()]] + mid + [P[t.argmax()]])
    seg_d = np.linalg.norm(P[:, None] - line[None], axis=2).min(1)
    radius = max(float(np.median(seg_d)), 1e-3)
    ring = []
    prev = None
    for i, p in enumerate(line):
        d = line[min(i + 1, len(line) - 1)] - line[max(i - 1, 0)]
        d /= np.linalg.norm(d)
        side = np.cross(d, [0, 1, 0] if abs(d[1]) < 0.9 else [1, 0, 0]) if prev is None else prev - (prev @ d) * d
        side /= np.linalg.norm(side)
        prev = side
        up = np.cross(d, side)
        ring.append([p + radius * (np.cos(a) * side + np.sin(a) * up)
                     for a in np.linspace(0, 2 * np.pi, sides, endpoint=False)])
    pos = np.array(ring).reshape(-1, 3)
    tris = []
    for i in range(len(line) - 1):
        for k in range(sides):
            a, b = i * sides + k, i * sides + (k + 1) % sides
            tris += [(a, b, a + sides), (b, b + sides, a + sides)]
    return pos, np.array(tris)


def simplify(tony, verbose=True):
    """Tony at GameCube size: dict with pos (V, 3), tris (F, 3), corner uv (F, 3, 2) in the atlas, weights (V, S)."""
    allpos, alltris, alluv, allw = [], [], [], []
    base = 0
    for name, mats, keep in GROUPS:
        parts = [p for p in tony.parts if p["material"] in mats]
        tri_pos = np.concatenate([p["pos"][p["tris"]] for p in parts])
        tri_uv = np.concatenate([p["uv"][p["tris"]] for p in parts])
        tri_w = np.concatenate([p["weights"][p["tris"]] for p in parts])
        tri_mat = np.concatenate([np.full(len(p["tris"]), p["material"]) for p in parts])
        pos, tris = weld(tri_pos.reshape(-1, 3), np.arange(3 * len(tri_pos)).reshape(-1, 3))
        if name in PIECEWISE:
            ps, ts = [], []
            for P, F in pieces(pos, tris):
                share = max(24, int(keep * len(F) / len(tris)))
                p2, t2 = decimate(P, F, share)
                if len(t2) > 2 * share:
                    p2, t2 = tube(P, *TUBE)
                ts.append(t2 + sum(len(x) for x in ps))
                ps.append(p2)
            pos, tris = np.concatenate(ps), np.concatenate(ts)
        else:
            pos, tris = decimate(pos, tris, keep)
        tris = tris[(tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 2] != tris[:, 0])]
        surf = Surface(tri_pos, tri_mat)
        # each face's material is the one under its middle; each corner's texture coordinate comes from that
        # material's surface, looked up a little in from the corner so a seam in the texture keeps to this side
        centre = pos[tris].mean(1)
        fid, _ = surf.nearest(centre)
        fmat = tri_mat[fid]
        uv = np.zeros((len(tris), 3, 2))
        for m in np.unique(fmat):
            sel = np.nonzero(fmat == m)[0]
            pts = (0.8 * pos[tris[sel]] + 0.2 * centre[sel, None]).reshape(-1, 3)
            t, bary = surf.nearest(pts, int(m))
            corner = (bary[:, :, None] * tri_uv[t]).sum(1).reshape(len(sel), 3, 2)
            uv[sel] = atlas_uv(int(m), corner)
        t, bary = surf.nearest(pos)
        w = (bary[:, :, None] * tri_w[t]).sum(1)
        w /= w.sum(1, keepdims=True)
        if name == "body":      # the simplified body as drawn, and its weights, for what sits on it
            body = (Surface(pos[tris], np.zeros(len(tris), int)), pos[tris], w[tris])
        if name in ON_BODY:
            b_surf, b_pos, b_w = body
            t, bary = b_surf.nearest(pos)
            w = (bary[:, :, None] * b_w[t]).sum(1)
            w /= w.sum(1, keepdims=True)
            under = (bary[:, :, None] * b_pos[t]).sum(1)
            n = np.cross(b_pos[t, 1] - b_pos[t, 0], b_pos[t, 2] - b_pos[t, 0])
            n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
            gap = ((pos - under) * n).sum(1)
            pos = pos + np.maximum(LIFT - gap, 0)[:, None] * n
        if name in DOUBLE_SIDED:      # the back: its own positions, so their normals face the other way
            tris = np.concatenate([tris, tris[:, ::-1] + len(pos)])
            uv = np.concatenate([uv, uv[:, ::-1]])
            pos, w = np.concatenate([pos, pos]), np.concatenate([w, w])
        if verbose:
            print(f"Tony: {name} {len(tri_pos)} -> {len(tris)} triangles, {len(pos)} positions")
        allpos.append(pos)
        alltris.append(tris + base)
        alluv.append(uv)
        allw.append(w)
        base += len(pos)
    return {"pos": np.concatenate(allpos), "tris": np.concatenate(alltris), "uv": np.concatenate(alluv),
            "weights": np.concatenate(allw)}


def normals(pos, tris):
    """Area-weighted vertex normals."""
    n = np.cross(pos[tris[:, 1]] - pos[tris[:, 0]], pos[tris[:, 2]] - pos[tris[:, 0]])
    out = np.zeros_like(pos)
    for k in range(3):
        np.add.at(out, tris[:, k], n)
    length = np.linalg.norm(out, axis=1, keepdims=True)
    out = np.where(length > 1e-12, out / np.maximum(length, 1e-12), [0.0, 1.0, 0.0])   # unused positions: up
    return out


def as_obj(pos, mesh):
    """(pos, uv, nrm, tris) in shyguy's OBJ convention: corners (position, texcoord, normal), v up. Corners with
    the same position and (nearly) the same texture coordinate share one, so the display lists can strip them."""
    corner_uv = mesh["uv"].reshape(-1, 2)
    key = np.concatenate([mesh["tris"].reshape(-1, 1), np.round(corner_uv * 4096)], 1).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    uv = corner_uv[first] * np.array([1, -1])
    inv = inv.reshape(-1, 3)
    tris = [tuple((int(mesh["tris"][f, k]), int(inv[f, k]), int(mesh["tris"][f, k])) for k in range(3))
            for f in range(len(mesh["tris"]))]
    return pos, uv, normals(pos, mesh["tris"]), tris


# ---------------------------------------------------------------- golfer 17's files

BASE = "waluigi"
# golfer 17's files <- the base's: in-round models, texture bank, select screen model (Waluigi: golfer 1, whose
# methods [22] [23] [24] name C/S/C, C/S/B, C/S/J, and character code 9, whose select screen model is B/V/C)
SOURCES = {"C/W/G": "C/S/C", "C/W/J": "C/S/J", "B/V/L": "B/V/C", "C/W/F": "C/S/B"}
GOLFER_MODEL, BANK = "C/W/G", "C/W/F"
FACE = "C/W/I"            # in-round face beside the score (64x64 RGB5A3)
PLATES = "C/W/H"          # emblem (texture 0) and name plate
ROW, ROW_TEX, ROW_CELL = "B/U/P", 1, 1        # the extra page's 58x58 faces: his is 2nd (Shy Guy's 1st)
FACES, FACES_TEX, FACES_SLOT = "B/U/M", 39, 1  # the extra page's 64x64 faces (the 1P badge): his is 2nd
PORTRAIT = (20, -8, (0, 2.45, 0.1), 0.42)      # face pictures: turn, tilt, centre and half-size (his own units)
EMBLEM_VIEW = (0, -5, (0, 2.47, 0.08), 0.44)
NAME = b"Tony\x00\x00\x00\x00"
# His golfer in the link record's slot 0 (record offsets: the second golfer's entry is at +0x2C, see
# shyguy.RECORD): name twice, body 1 (golfer 17), right-handed, Waluigi's power shot effects (golfer code 1).
# Andrew's trade-off pick, high risk and high reward: 300 yards (the longest regular golfer hits 220, the Star
# versions 230 to 300; the game sizes every other club from the driver), high (3), curve to the default side (0)
# slightly (1), the best control (4) and strong spin (5), but the lowest impact there is (-10, the game's floor; the
# Star versions' lowest is -6), a 5-frame impact zone on his twice-as-fast meter, putts aside (build_mod.py
# TONY_ZONE, POWER_TICK) and no auto swing (build_mod.py POWER_PRESS: only B sets his power).
RECORD = {0x2C: NAME[:4], 0x3C: NAME[:4], 0x44: (300).to_bytes(4, "big"), 0x48: bytes([1, 0, 0, 3]),
          0x4C: bytes([0, 1, 0xF6, 4]), 0x50: bytes([5, 0, 0, 0]), 0x54: bytes([1, 0, 0, 0])}
# The select screen's lines for golfer 17 are the Game Boy Advance girl's (common set: 0x25E the cursor on him,
# 0x271 the pick call of odd link golfers): silent, until he has a voice of his own.
MENU_SILENT = (0x25E, 0x271)
SILENCE = 0.05       # seconds


def texture(img, size, levels):
    """CMPR with mipmaps of an RGB image, (w, h) down to 1 on the longer side."""
    import shyguy
    out = b""
    for k in range(levels):
        w, h = max(1, size[0] >> k), max(1, size[1] >> k)
        out += shyguy.cmpr(np.asarray(img.resize((w, h), Image.BOX), np.float64))
    return out


def tex_levels(size):
    return int(np.log2(max(size))) + 1


# ---------------------------------------------------------------- smooth skinning

MIN_THIRD = 0.06     # a third bone's weight below this is folded into the other two


def bone_weights(seg_weights, segments, bone_of_segment):
    """Per vertex: up to three (bone, weight) with weights summing to 128 (the game's units), strongest first."""
    out = []
    for w in seg_weights:
        by_bone = {}
        for k, s in enumerate(segments):
            if w[k] > 0:
                b = bone_of_segment[s]
                by_bone[b] = by_bone.get(b, 0.0) + float(w[k])
        top = sorted(by_bone.items(), key=lambda kv: -kv[1])[:3]
        if len(top) == 3 and top[2][1] < MIN_THIRD:
            top = top[:2]
        total = sum(v for _, v in top)
        q = [int(round(128 * v / total)) for _, v in top]
        q[0] += 128 - sum(q)
        bones = [b for b, _ in top]
        if len(bones) == 1 or q[1] == 0:            # one bone: the pair is that bone twice
            bones, q = [bones[0], bones[0]], [127, 1]
        elif len(q) == 3 and q[2] == 0:
            bones, q = bones[:2], q[:2]
        q = [min(127, x) for x in q]
        q[-1] += 128 - sum(q)
        out.append(list(zip(bones, q)))
    return out


def skinned_swap(raw, pos, nrm, uv, tris, weights, tex, place, tex_size, levels, hide_parts=()):
    """Rebuild one of the base golfer's models around Tony, smoothly skinned the way the game's own golfers are:
    every vertex blended between its two strongest bones (and a third added where it matters).

    The game's skinning (main.dol FUN_80008bfc, kernels 0x8002E4F8 and 0x8002E5EC): each frame the model's matrix
    slots (one per bone in the list at root +0x4C, count +0x48) get their bones' skin matrices; then each skin block
    (root +0x54, count +0x50, 0x20 each) writes blended vertices into the instance's own position and normal
    buffers (sized root +0x0C and +0x20; their first root +0x14 / +0x28 entries are copies of the source):
      +0x00 / +0x04 first position / normal it writes (in the source arrays root +0x10 / +0x24 and in the buffers)
      +0x0C runs of two-bone vertices at +0x10: (u8 slot a, u8 slot b, u16 count), the next `count` vertices each
            = wa * Ma v + wb * Mb v, with the weight pairs (s8, 1/128ths) in order at +0x08
      +0x18 runs of extra bones at +0x1C: (u16 slot, u16 count): for `count` vertices whose numbers (u16, from the
            block's first) are next in the list at +0x14, add w * M v (the weight bytes follow the pairs)
    A skinned group (flags bit 0 clear) draws from those buffers; its palette entry -1 is the model's own matrix.

    Tony's vertices go in a new block after everything the base model's buffers held (so its face morphs, which
    write there, can't touch them); the base's own blocks are dropped (its body is gone). pos, nrm: per vertex;
    uv: texcoords; tris: corners (vertex, texcoord); weights: bone_weights(); hide_parts: mesh parts (+0x38) of the
    base drawn on its body besides part 1, which go too. Returns the packed file."""
    import struct
    import shyguy
    mod = shyguy.Module(raw)
    root = mod.root
    meshes, count = mod.ptr(root + 0x40), mod.u32(root + 0x3C)
    body = [i for i in range(count) if mod.u32(meshes + 0x3C * i + 0x38) == shyguy.BODY_PART]
    ours = next(i for i in body if mod.u32(meshes + 0x3C * i + 0x34) == 2 and mod.blob[meshes + 0x3C * i + 7] >= 1)
    hidden = body + [i for i in range(count) if mod.u32(meshes + 0x3C * i + 0x38) in hide_parts]
    for i in range(count):      # nothing else may need the base's skinning
        mo = meshes + 0x3C * i
        if i not in hidden and any(not mod.u32(mod.ptr(mo + 0x2C) + 0x38 * g) & 1 for g in range(mod.u32(mo + 0x28))):
            raise SystemExit(f"Tony: mesh {i} of the base model is skinned too")

    nop = mod.alloc(bytes(32), 32)                       # the base's body (and its buttons) draw nothing
    for i in hidden:
        mo = meshes + 0x3C * i
        groups = mod.ptr(mo + 0x2C)
        for g in range(mod.u32(mo + 0x28)):
            go = groups + 0x38 * g
            if mod.u32(go) & 2:
                entries = mod.ptr(go + 0x34)
                for d in range(mod.u32(go + 0x30)):
                    mod.set_ptr(entries + 0x20 * d, nop)
                    mod.put32(entries + 0x20 * d + 4, 32)
            else:
                mod.set_ptr(go + 0x34, nop)
                mod.put32(go + 0x30, 32)

    width = lambda f: struct.calcsize(shyguy.FORMAT[f[0]][0])
    pf = mdl.fmt(mod.u32(root + 4), mod.blob[root + 7])
    nf = mdl.fmt(mod.u32(root + 0x18), mod.blob[root + 0x1B])
    tf = mdl.fmt(mod.u32(root + 0x2C), mod.blob[root + 0x2F])
    skinned = mod.u32(root + 0x50) > 0 or mod.u32(root + 0x14) > 0
    p0 = mod.u32(root + 0x0C) if skinned else 0
    n0 = mod.u32(root + 0x20) if skinned else 0

    # vertices in the order the block writes them: grouped by bone pair
    pair = [(w[0][0], w[1][0]) for w in weights]
    order = sorted(range(len(pos)), key=lambda v: pair[v])
    slot_of = {}
    old_list = mod.ptr(root + 0x4C)
    slots = list(mod.blob[old_list:old_list + mod.u32(root + 0x48)]) if old_list is not None else []
    for w in weights:
        for b, _ in w:
            if b not in slots:
                slots.append(b)
    if len(slots) > 255 or max(slots) > 255:
        raise SystemExit("Tony: too many matrix slots")
    slot_of = {b: k for k, b in enumerate(slots)}
    runs, pairs_w, extra = [], bytearray(), {}
    for k, v in enumerate(order):
        a, b = slot_of[weights[v][0][0]], slot_of[weights[v][1][0]]
        if runs and tuple(runs[-1][:2]) == (a, b):
            runs[-1][2] += 1
        else:
            runs.append([a, b, 1])
        pairs_w += struct.pack(">bb", weights[v][0][1], weights[v][1][1])
        if len(weights[v]) == 3:
            extra.setdefault(slot_of[weights[v][2][0]], []).append((k, weights[v][2][1]))
    extra_runs = sorted(extra.items())
    single_w = b"".join(struct.pack(">b", w) for _, items in extra_runs for _, w in items)
    indices = b"".join(struct.pack(">H", k) for _, items in extra_runs for k, _ in items)

    def grow(field, stride, keep, data):
        """The source array at root + field: its first `keep` entries (padded), then data."""
        old = mod.ptr(root + field)
        have = (shyguy.array_end(mod, old) - old) // stride if old is not None else 0
        head = bytes(mod.blob[old:old + min(have, keep) * stride]) if old is not None else b""
        new = mod.alloc(head + bytes(keep * stride - len(head)) + data, 32)
        mod.set_ptr(root + field, new)

    unit = nrm / np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    grow(0x10, 3 * width(pf), p0, shyguy.pack_array(pos[order], pf, "positions"))
    grow(0x24, 3 * width(nf), n0, shyguy.pack_array(unit[order], nf, "normals"))
    mod.put32(root + 0x0C, max(mod.u32(root + 0x0C), p0 + len(pos)))
    mod.put32(root + 0x20, max(mod.u32(root + 0x20), n0 + len(pos)))
    tex_old = mod.ptr(root + 0x30)
    t_stride = 2 * width(tf)
    t0 = (shyguy.array_end(mod, tex_old) - tex_old) // t_stride
    mod.set_ptr(root + 0x30, mod.alloc(bytes(mod.blob[tex_old:tex_old + t0 * t_stride]) +
                                       shyguy.pack_array(np.stack([uv[:, 0], -uv[:, 1]], 1), tf, "texcoords"), 32))
    if max(p0, n0) + len(pos) > 0x10000 or t0 + len(uv) > 0x10000:
        raise SystemExit("Tony: too many vertices for 16-bit indices")

    lst = mod.alloc(bytes(slots) + bytes((-len(slots)) % 4), 4)
    mod.set_ptr(root + 0x4C, lst)
    mod.put32(root + 0x48, len(slots))
    bone_base = mod.ptr(root + 0x64)       # bit 0 at bone +0x5C skips a bone's matrix in the draw: keep his clear
    for b in {b for w in weights for b, _ in w}:
        mod.put32(bone_base + 0x60 * b + 0x5C, mod.u32(bone_base + 0x60 * b + 0x5C) & ~1)
    weights_at = mod.alloc(bytes(pairs_w) + single_w + bytes((-len(pairs_w) - len(single_w)) % 4), 4)
    runs_at = mod.alloc(b"".join(struct.pack(">BBH", a, b, c) for a, b, c in runs), 4)
    extra_at = mod.alloc(b"".join(struct.pack(">HH", s, len(items)) for s, items in extra_runs) or bytes(4), 4)
    index_at = mod.alloc(indices + bytes((-len(indices)) % 4) or bytes(4), 4)
    block = mod.alloc(struct.pack(">8I", p0, n0, 0, len(runs), 0, 0, len(extra_runs), 0), 32)
    for off, target in ((8, weights_at), (0x10, runs_at), (0x14, index_at), (0x1C, extra_at)):
        mod.set_ptr(block + off, target)
    mod.set_ptr(root + 0x54, block)
    mod.put32(root + 0x50, 1)

    # one skinned group: every corner from the instance's buffers, through the model's own matrix
    where = np.empty(len(pos), int)
    where[order] = np.arange(len(pos))
    gx = [(a, c, b) for a, b, c in tris if len({a[0], b[0], c[0]}) == 3]     # GX winding (clockwise)
    vertex = lambda c: struct.pack(">3H", p0 + where[c[0]], n0 + where[c[0]], t0 + c[1])
    dl = mod.alloc(shyguy.display_list(gx, vertex), 32)
    size = len(mod.blob) - dl
    lo, hi = pos.min(0), pos.max(0)
    ent = mod.alloc(struct.pack(">II6f", 0, size, *lo, *hi), 32)
    mod.set_ptr(ent, dl)
    grp = mod.alloc(struct.pack(">II", 2, 1) + struct.pack(">I", 0xFFFFFFFF) + bytes(36) + struct.pack(">II", 1, 0), 32)
    mod.set_ptr(grp + 0x34, ent)
    mo = meshes + 0x3C * ours
    mod.put32(mo + 0x28, 1)
    mod.set_ptr(mo + 0x2C, grp)
    mod.put32(mo + 4, mod.u32(mo + 4) & ~0x40000000 & ~0xFFFF | 0x0101)   # no colours, one texcoord set, one texture

    m = mdl.Model(raw)                                   # the texture, as shyguy.swap places it
    texset = m.p(m.root + 0x8C)
    head = shyguy.texture_header(m, texset, mod.blob[mo + 10])
    at = place[1] | 0x80000000 if place[0] == "bank" else mod.alloc(tex, 32) - texset
    for k, v in enumerate((tex_size[1] << 16 | tex_size[0], 14, at, 1, 1, 5, 1, 0, (levels - 1) << 8)):
        mod.put32(head + 4 * k, v)
    mod.blob += bytes((-len(mod.blob)) % 32)
    return mod.pack(), len(slots), len(runs), len(extra_runs)


def build(clean_files, folder, current=None, verbose=True):
    """{disc path: new file} for golfer 17: models, texture bank, pictures. current: files already changed by the
    build (Shy Guy's extra page pictures), which his are added to."""
    import camelot_lz as lz
    import shyguy
    read = lambda rel: (current or {}).get(rel) or open(os.path.join(clean_files, *rel.split("/")), "rb").read()
    base = BASES[BASE]
    tony = Tony(folder)
    mesh = simplify(tony, verbose)
    atlas = atlas_image(tony)
    levels = tex_levels(ATLAS)
    tex = texture(atlas, ATLAS, levels)
    ref = mdl.Model(read(SOURCES[GOLFER_MODEL]))

    out = {}
    raw = read(SOURCES[BANK])
    bank = bytearray(lz.decompress(raw)[0])
    bank += bytes((-len(bank)) % 32)
    bank_at = len(bank)
    bank += tex
    seg_index = {s: k for k, s in enumerate(tony.segments)}
    for rel in (GOLFER_MODEL, "C/W/J", "B/V/L"):
        mraw = read(SOURCES[rel])
        m = mdl.Model(mraw)
        # 2.0: the select screen's Waluigi holds his right pinky tip 1.56 from the golf model's
        bmap = {b: b for b in range(len(mdl.bones(m)))} if rel == GOLFER_MODEL else shyguy.bone_map(ref, m, 2.0)
        joints = base_joints(base, m)
        missing = sorted({b for s in tony.segments for b in [segment_bone(base, s)] if b not in bmap})
        if missing:
            raise SystemExit(f"Tony: {SOURCES[rel]} has no bones matching {base['model']} {missing}")
        transforms, scale = fit_transforms(tony, base, joints, lambda b: bmap[b])
        pos = fit_points(mesh["pos"], mesh["weights"], tony.segments, transforms)
        weights = bone_weights(mesh["weights"], tony.segments,
                               {s: bmap[segment_bone(base, s)] for s in tony.segments})
        meshes, count = m.p(m.root + 0x40), m.u32(m.root + 0x3C)
        body = [i for i in range(count) if m.u32(meshes + 0x3C * i + 0x38) == shyguy.BODY_PART]
        texset = m.p(m.root + 0x8C)
        banked = m.u32(shyguy.texture_header(m, texset, m.blob[meshes + 0x3C * body[0] + 10]) + 8) & 0x80000000
        place = ("bank", bank_at) if banked else ("append", None)
        p, uv, nrm, tris = as_obj(pos, mesh)
        out[rel], nslots, nruns, nextra = skinned_swap(mraw, p, nrm, uv, tris, weights, tex, place, ATLAS, levels,
                                                       base.get("hide_parts", ()))
        if verbose:
            print(f"Tony: {rel} (from {SOURCES[rel]}) {len(mraw)} -> {len(out[rel])} bytes, scale {scale:.2f},"
                  f" texture {'in the bank' if banked else 'in the model'}, skinned: {nslots} matrix slots,"
                  f" {nruns} bone pairs, {nextra} third bones")
    out[BANK] = lz.pack(raw[0], bytes(bank))
    if verbose:
        print(f"Tony: {BANK} (from {SOURCES[BANK]}) texture at 0x{bank_at:X} ({ATLAS[0]}x{ATLAS[1]} CMPR,"
              f" {levels} levels, {len(tex)} bytes)")

    obj = as_obj(mesh["pos"], mesh)      # pictures: his own shape
    icon = shyguy.shrink(shyguy.render(obj, atlas, 256, *PORTRAIT), 64)
    out[ROW] = extra_row(read(ROW), obj, atlas)
    out[FACES] = extra_page(read(FACES), icon)
    out[FACE] = shyguy.face_file(read(FACE), icon)
    out[PLATES] = emblem(read(PLATES), obj, atlas)
    out.update(silence_menu(read))
    if verbose:
        print(f"Tony: pictures in {ROW}, {FACES}, {FACE}, {PLATES}")
    return out


def silence_menu(read):
    """The common sound set's sample directory and samples with MENU_SILENT's samples silent (in place)."""
    import musyx
    import shyguy
    pool, proj, sdir, samp = (read(rel) for rel in shyguy.COMMON_SET)
    sample_of = musyx.sfx_samples(pool, proj)
    rates = {sid: rate for _, sid, _, rate, _, _ in musyx.sdir_entries(sdir)}
    for sfx in MENU_SILENT:
        sid = sample_of[sfx]
        sdir, samp = musyx.replace_in_place(sdir, samp, sid, np.zeros(int(rates[sid] * SILENCE), np.int64))
    return {shyguy.COMMON_SET[2]: bytes(sdir), shyguy.COMMON_SET[3]: bytes(samp)}


def extra_row(raw, obj, tex):
    """B/U/P texture 1: his card, 2nd of the extra page's 8 (58x58 on white)."""
    import camelot_lz as lz
    import shyguy
    import textures as tx
    blob = bytearray(tx.load_bytes(raw))
    (w, ht, fmt), old, at = shyguy.picture(blob, ROW_TEX, (464, 58, 14))
    new = old.astype(np.float64)
    x = 58 * ROW_CELL
    new[:58, x:x + 58] = shyguy.on_white(shyguy.shrink(shyguy.render(obj, tex, 232, *PORTRAIT), 58))
    shyguy.put_cmpr(blob, at, old, new)
    return lz.pack(raw[0], bytes(blob))


def extra_page(raw, icon):
    """B/U/M texture 39: his face, 2nd of the extra page's 8 (64x64, clear background)."""
    import camelot_lz as lz
    import shyguy
    import textures as tx
    blob = bytearray(tx.load_bytes(raw))
    (w, ht, fmt), old, at = shyguy.picture(blob, FACES_TEX, (512, 64, 14))
    new = old.astype(np.float64)
    new[:, 64 * FACES_SLOT:64 * FACES_SLOT + 64] = icon
    shyguy.put_cmpr(blob, at, old, new)
    return lz.pack(raw[0], bytes(blob))


def emblem(raw, obj, tex):
    """C/W/H texture 0: his head where the girl's drawing is (on white), like Shy Guy's (shyguy.emblem)."""
    import camelot_lz as lz
    import shyguy
    import textures as tx
    blob = bytearray(tx.load_bytes(raw))
    (w, ht, fmt), old, at = shyguy.picture(blob, 0, None)
    if fmt != 14:
        raise SystemExit("Tony: the emblem isn't a CMPR picture")
    ys, xs = np.nonzero(old[:, :w // 2, :3].min(2) < 200)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    side = int(max(x1 - x0, y1 - y0)) + 1
    new = old.astype(np.float64)
    new[max(0, y0 - 2):y1 + 3, max(0, x0 - 2):x1 + 3, :3] = 255
    head = shyguy.on_white(shyguy.shrink(shyguy.render(obj, tex, 4 * side, *EMBLEM_VIEW), side))
    top, left = (y0 + y1 + 1 - side) // 2, (x0 + x1 + 1 - side) // 2
    rows, cols = slice(max(0, top), top + side), slice(max(0, left), left + side)
    new[rows, cols] = head[rows.start - top:rows.start - top + new[rows, cols].shape[0],
                           cols.start - left:cols.start - left + new[rows, cols].shape[1]]
    shyguy.put_cmpr(blob, at, old, new)
    return lz.pack(raw[0], bytes(blob))
