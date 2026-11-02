"""v27 Football: the poses (Andrew: "animations for throwing, running, catching etc. ... found online and mapped to
the characters or built yourself"). Built here as keyframed joint rotations for one canonical body, then put on each
golfer's own skeleton at run time (fbpose.py) through the joints rigmap.py finds.

The canonical body is every golfer's bind pose: model space Y up, facing +Z, its left at +X, a T (arms out along X,
legs down). A key gives each of the 19 joints (rigmap.JOINTS) its rotation D in model space relative to that rest
(composed down the joint tree from per-joint bends, `pose()`), plus the body's pitch (degrees, forward, about the
hips) and drop (a share of the hips' height: 0.8 lies on the ground).

On a golfer, joint j sits on bone b with parent bone p. Bones between joints follow their joint rigidly (rest local
rotations), so the posed model-space rotation of b is D_j R_b (R = the bone's rest rotation in model space) and of p
D_a R_p, with a the nearest joint above b that the golfer has (none: identity). b's local rotation is then
    L_b = conj(R_p) * conj(D_a) * D_j * R_p * l_b       (l_b = b's rest local rotation, the bone's own quaternion)
fbpose.py does this every frame with R_p from `rig_table` (a quaternion per joint) and a's index.

Quaternions are (x, y, z, w), Hamilton products, the game's MTXQuat convention (model.quat34).
`python fbmoves.py` checks the run-time maths against plain forward kinematics and draws stick figures of every golfer
in every key (fbmoves_sheet.png).
"""
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model as mdl  # noqa: E402
import rigmap  # noqa: E402

JOINTS = rigmap.JOINTS
J = {name: k for k, name in enumerate(JOINTS)}
PARENT = {"hips": None, "spine": "hips", "chest": "spine", "neck": "chest", "head": "neck",
          "clav_r": "chest", "uarm_r": "clav_r", "farm_r": "uarm_r", "hand_r": "farm_r",
          "clav_l": "chest", "uarm_l": "clav_l", "farm_l": "uarm_l", "hand_l": "farm_l",
          "thigh_r": "hips", "shin_r": "thigh_r", "foot_r": "shin_r",
          "thigh_l": "hips", "shin_l": "thigh_l", "foot_l": "shin_l"}
CLUB_PARTS = (3, 4, 5, 6, 8, 9, 10, 11, 0x16)   # mesh parts that are clubs (golf FUN_80428e7c)


# ---- quaternions (x, y, z, w)
def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def qconj(a):
    return (-a[0], -a[1], -a[2], a[3])


def qaxis(axis, deg):
    h = math.radians(deg) / 2
    s = math.sin(h)
    n = math.sqrt(sum(c * c for c in axis))
    return (axis[0] / n * s, axis[1] / n * s, axis[2] / n * s, math.cos(h))


def qnorm(a):
    n = math.sqrt(sum(c * c for c in a))
    return tuple(c / n for c in a)


def qnlerp(a, b, u):
    if sum(x * y for x, y in zip(a, b)) < 0:
        b = tuple(-c for c in b)
    return qnorm(tuple(x + (y - x) * u for x, y in zip(a, b)))


def q_of_matrix(m):
    """Rotation quaternion of a 3x4 (rows of 4) matrix's 3x3 part, its columns normalised (bone scales)."""
    cols = [[m[4 * r + c] for r in range(3)] for c in range(3)]
    cols = [[v / math.sqrt(sum(x * x for x in col)) for v in col] for col in cols]
    r = [[cols[c][rr] for c in range(3)] for rr in range(3)]
    t = r[0][0] + r[1][1] + r[2][2]
    if t > 0:
        s = math.sqrt(t + 1) * 2
        return qnorm(((r[2][1] - r[1][2]) / s, (r[0][2] - r[2][0]) / s, (r[1][0] - r[0][1]) / s, s / 4))
    i = max(range(3), key=lambda k: r[k][k])
    j, k = (i + 1) % 3, (i + 2) % 3
    s = math.sqrt(1 + r[i][i] - r[j][j] - r[k][k]) * 2
    q = [0, 0, 0, 0]
    q[i] = s / 4
    q[j] = (r[j][i] + r[i][j]) / s
    q[k] = (r[k][i] + r[i][k]) / s
    q[3] = (r[k][j] - r[j][k]) / s
    return qnorm(tuple(q))


X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)


def R(*turns):
    """Rotation: turns (axis, degrees) applied in order (the first one first)."""
    q = (0, 0, 0, 1)
    for axis, deg in turns:
        q = qmul(qaxis(axis, deg), q)
    return q


# ---- the canonical poses: per-joint bends in the parent's (rest) frame
def pose(pitch=0.0, drop=0.0, **bends):
    """A key: bends {joint: quaternion} relative to the parent joint -> absolute D per joint, + body channels."""
    D = {}
    for name in JOINTS:
        local = bends.get(name, (0, 0, 0, 1))
        par = PARENT[name]
        D[name] = qmul(D[par], local) if par else local
    return {"D": D, "pitch": pitch, "drop": drop}


def arm(side, fwd=0.0, inward=0.0, elbow=0.0, down=90.0):
    """The upper arm lowered from the T `down` degrees (90: hanging), raised forward `fwd` (90: pointing ahead, 180:
    straight up; negative: back), then swung `inward` across the body; the elbow bent `elbow` (forward when hanging).
    side 'r' (-X) or 'l' (+X). With down 0 and fwd 90 the arm stays out to the side, rolled so the elbow bends up."""
    sz = 1 if side == "r" else -1
    return {"uarm_" + side: R((Z, sz * down), (X, -fwd), (Y, sz * inward)), "farm_" + side: R((Y, sz * elbow))}


def leg(side, thigh=0.0, knee=0.0, foot=0.0, spread=0.0):
    """Thigh swung forward `thigh` degrees, the knee bent `knee`, the foot pointed `foot` (toes down +)."""
    sz = 1 if side == "r" else -1
    return {"thigh_" + side: R((Z, -sz * spread), (X, -thigh)), "shin_" + side: R((X, knee)),
            "foot_" + side: R((X, foot))}


def body(lean=0.0, twist=0.0, side=0.0, head=0.0, head_turn=0.0):
    """Spine leaning forward `lean`, the chest turned `twist` (to the left +), the head nodding down `head`."""
    return {"spine": R((X, lean * 0.5), (Y, twist * 0.5), (Z, side * 0.5)), "chest": R((X, lean * 0.5),
            (Y, twist * 0.5), (Z, side * 0.5)), "head": R((X, head), (Y, head_turn))}


def merge(*parts):
    out = {}
    for p in parts:
        out.update(p)
    return out


def ready():
    return pose(**merge(body(lean=12, head=-10), arm("r", 25, 10, 60, down=80), arm("l", 25, 10, 60, down=80),
                        leg("r", 18, 30, -10, 4), leg("l", 18, 30, -10, 4)))


def run_key(t):
    """The run cycle at t in [0, 1): right leg forward at 0.25, left at 0.75."""
    s = math.sin(2 * math.pi * t)
    c = math.cos(2 * math.pi * t)
    def side(sign):
        sw = sign * s                                # +1: this leg forward
        lift = max(0.0, -sign * c)                   # the back leg folds up as it comes through
        return leg("r" if sign > 0 else "l", thigh=10 + 38 * sw, knee=15 + 70 * lift + 20 * max(0.0, sw),
                   foot=-5 + 25 * max(0.0, -sw))
    arms = merge(arm("r", -35 * s + 5, 10, 85), arm("l", 35 * s + 5, 10, 85))
    return pose(drop=0.04 * abs(c), **merge(body(lean=15, twist=-8 * s, head=-12), arms, side(1), side(-1)))


def jump_key(u):
    """0 crouched to spring (arms back), 0.35 rising, 1 at the top, arms reaching up."""
    crouch = max(0.0, 1 - 3 * u)
    reach = min(1.0, u * 1.5)
    f = -30 + 190 * reach                            # arms swung from behind to up and out in a V (straight up,
    v = -35 * reach                                  # big-headed golfers like Mario hid their faces)
    return pose(**merge(body(lean=20 * crouch - 5 * reach, head=-20 * reach), arm("r", f, v, 20 - 10 * reach),
                        arm("l", f, v, 20 - 10 * reach),
                        leg("r", 40 * crouch + 15 * reach, 70 * crouch + 35 * reach, 20 * reach),
                        leg("l", 40 * crouch + 5 * reach, 70 * crouch + 15 * reach, 20 * reach)))


def dive_key(u):
    """Laid out flat, arms stretched ahead: the body pitched forward with the flight."""
    p = 25 + 60 * min(1.0, u * 1.6)
    return pose(pitch=p, drop=0.35 * u, **merge(body(lean=-10, head=-p * 0.8), arm("r", 160, -20, 10),
                                                  arm("l", 160, -20, 10), leg("r", -15, 20, 30), leg("l", -5, 35, 30)))


def down_key():
    return pose(pitch=88, drop=0.82, **merge(body(lean=-15, head=-60), arm("r", 155, -20, 25), arm("l", 155, -20, 25),
                                             leg("r", -10, 25, 40), leg("l", 0, 15, 40)))


def catch_key(u):
    """Hands up together in front for the ball: u 0 ready to 1 reaching high."""
    return pose(**merge(body(lean=8 - 12 * u, head=-10 - 15 * u), arm("r", 65 + 30 * u, 20, 45 - 15 * u),
                        arm("l", 65 + 30 * u, 20, 45 - 15 * u), leg("r", 12, 20, 0, 4), leg("l", 12, 20, 0, 4)))


def hold_key():
    """The ball tucked in: forearms across the chest."""
    return pose(**merge(body(lean=8, head=-5), arm("r", 35, 45, 115), arm("l", 35, 45, 115), leg("r", 8, 10),
                        leg("l", 8, 10)))


def qb_key(stage):
    """The pass from the golf stance (target on the golfer's left, +X): the body turned to face it (hips +90).
    stage 0 set (ball at the chest), 1 cocked (right arm back), 2 release (arm over the top), 3 follow-through."""
    hips = {0: 80, 1: 55, 2: 95, 3: 115}[stage]
    twist = {0: 0, 1: -35, 2: 15, 3: 30}[stage]
    rarm = {0: arm("r", 35, 40, 105), 1: arm("r", 90, -35, 95, down=0), 2: arm("r", 150, 10, 25),
            3: arm("r", 30, 50, 30)}[stage]
    larm = {0: arm("l", 35, 40, 105), 1: arm("l", 85, 10, 10), 2: arm("l", 40, 10, 60), 3: arm("l", -10, 0, 60)}[stage]
    legs = {0: merge(leg("r", 10, 20), leg("l", 10, 20)), 1: merge(leg("r", -15, 25), leg("l", 30, 20)),
            2: merge(leg("r", -25, 30, 20), leg("l", 25, 15)), 3: merge(leg("r", -35, 50, 30), leg("l", 20, 10))}[stage]
    b = body(lean={0: 5, 1: -5, 2: 15, 3: 25}[stage], twist=twist, head=-5, head_turn=-twist)
    return pose(**merge({"hips": R((Y, hips))}, b, rarm, larm, legs))


def kick_key(stage):
    """The field goal from the golf stance (turned to face the target): 0 set, 1 the leg back, 2 contact, 3 follow."""
    rl = {0: leg("r", 5, 10), 1: leg("r", -45, 90, 30), 2: leg("r", 35, 10, 40), 3: leg("r", 85, 5, 40)}[stage]
    ll = {0: leg("l", 5, 10), 1: leg("l", 25, 25), 2: leg("l", 10, 20), 3: leg("l", 0, 15, -10)}[stage]
    arms = {0: merge(arm("r", 10, 0, 20, down=75), arm("l", 10, 0, 20, down=75)),
            1: merge(arm("r", 30, 0, 30, down=50), arm("l", -30, 0, 20, down=40)),
            2: merge(arm("r", -20, 0, 20, down=45), arm("l", 40, 0, 10, down=40)),
            3: merge(arm("r", -30, 0, 20, down=50), arm("l", 50, 0, 10, down=40))}[stage]
    return pose(**merge({"hips": R((Y, 90))}, body(lean={0: 5, 1: -10, 2: -15, 3: -25}[stage], head=10), arms, rl, ll))


RUN_KEYS = 8
CLIPS = [  # name, keys, looping
    ("ready", [ready()], False),
    ("run", [run_key(k / RUN_KEYS) for k in range(RUN_KEYS)], True),
    ("jump", [jump_key(u) for u in (0.0, 0.35, 0.7, 1.0)], False),
    ("dive", [dive_key(u) for u in (0.0, 0.5, 1.0)], False),
    ("down", [down_key()], False),
    ("catch", [catch_key(u) for u in (0.0, 1.0)], False),
    ("hold", [hold_key()], False),
    ("throw", [qb_key(s) for s in range(4)], False),
    ("kick", [kick_key(s) for s in range(4)], False),
]
CLIP = {name: k for k, (name, _, _) in enumerate(CLIPS)}


# ---- a golfer's side
class Rig:
    """A golfer's joints on its skeleton: bone per joint (or -1), the nearest present joint above, R_p and l_b."""

    def __init__(self, m):
        self.m = m
        r = rigmap.rig(m)
        self.parent = [p for p, _ in mdl.bones(m)]
        self.world = mdl.world_bind(m)
        self.rest = [q_of_matrix(w) for w in self.world]
        base = m.p(m.root + 0x64)
        self.local = [struct.unpack_from(">4f", m.blob, base + m.bone_size * i + 0x4C) for i in range(len(self.parent))]
        self.bone = [r.get(name, -1) for name in JOINTS]
        self.anc = []
        for name in JOINTS:
            a = PARENT[name]
            while a and r.get(a, -1) < 0:
                a = PARENT[a]
            self.anc.append(J[a] if a else -1)
        self.rp = [self.rest[self.parent[b]] if b >= 0 and self.parent[b] >= 0 else (0, 0, 0, 1) for b in self.bone]
        hips = r.get("hips", 0)
        self.hips_y = self.world[hips][7]
        self.hide = club_roots(m)

    def locals_for(self, key):
        """{bone: local quaternion} for a key: the run-time formula."""
        out = {}
        D = key["D"]
        for j, b in enumerate(self.bone):
            if b < 0:
                continue
            e = D[JOINTS[j]] if self.anc[j] < 0 else qmul(qconj(D[JOINTS[self.anc[j]]]), D[JOINTS[j]])
            rp = self.rp[j]
            out[b] = qnorm(qmul(qmul(qmul(qconj(rp), e), rp), self.local[b]))
        return out

    def fk(self, locals_):
        """Model-space positions of every bone with these local rotations (rest translations, scales as bound)."""
        base = self.m.p(self.m.root + 0x64)
        world = []
        for i, p in enumerate(self.parent):
            o = base + self.m.bone_size * i
            s = struct.unpack_from(">3f", self.m.blob, o + 0x34)
            t = struct.unpack_from(">3f", self.m.blob, o + 0x40)
            q = locals_.get(i, self.local[i])
            loc = mdl.quat34(*q)
            for r in range(3):
                for c in range(3):
                    loc[4 * r + c] *= 0 if i in self.hide else s[c]
                loc[4 * r + 3] = t[r]
            world.append(loc if p < 0 else mdl.mul34(world[p], loc))
        return world


def club_roots(m):
    """The topmost bones that only club meshes use (their whole subtrees are clubs): fbpose.py shrinks them to
    nothing, so no club shows in the players' hands."""
    body, club = set(), set()
    for i, mo, g, go, mtx, dls in mdl.meshes(m):
        part = m.u32(mo + 0x38)
        bones = {m.u32(go + 8 + 4 * k) for k in range(min(m.u32(go + 4), 10))} if m.u32(go) & 1 else set()
        (club if part in CLUB_PARTS else body).update(bones)
    if any(not (m.u32(go) & 1) for i, mo, g, go, mtx, dls in mdl.meshes(m) if m.u32(mo + 0x38) == 1):
        slots = m.p(m.root + 0x4C)
        body |= {m.blob[slots + k] for k in range(m.u32(m.root + 0x48))}
    parent = [p for p, _ in mdl.bones(m)]
    only = {b for b in club - body if b < len(parent)}
    return sorted(b for b in only if parent[b] < 0 or parent[b] not in only)


def check_rest(rig):
    """With no bends every joint keeps its rest local rotation (the formula reduces to l_b)."""
    loc = rig.locals_for(pose())
    return max(max(abs(a - b) for a, b in zip(q, rig.local[b])) if
               sum(x * y for x, y in zip(q, rig.local[b])) > 0 else max(abs(a + b) for a, b in zip(q, rig.local[b]))
               for b, q in loc.items())


CHAINS = (("hips", "spine", "chest", "neck", "head"), ("chest", "clav_r", "uarm_r", "farm_r", "hand_r"),
          ("chest", "clav_l", "uarm_l", "farm_l", "hand_l"), ("hips", "thigh_r", "shin_r", "foot_r"),
          ("hips", "thigh_l", "shin_l", "foot_l"))


def sheet(codes, out, clips=None):
    """Front and side stick figures of the joints (each chain to its last joint's first child), per golfer and key."""
    from PIL import Image, ImageDraw
    keys = [(name, k, key) for name, ks, _ in CLIPS if not clips or name in clips for k, key in enumerate(ks)]
    cw, ch = (150, 170) if len(codes) * len(keys) > 12 else (300, 360)
    im = Image.new("RGB", (cw * len(keys), ch * len(codes) + 14), (250, 250, 250))
    d = ImageDraw.Draw(im)
    for row, code in enumerate(codes):
        rig = Rig(rigmap.load(code))
        kids = {}
        for i, p in enumerate(rig.parent):
            kids.setdefault(p, []).append(i)
        H = max(rig.hips_y * 2.2, 1)
        for col, (name, k, key) in enumerate(keys):
            world = rig.fk(rig.locals_for(key))
            pc, ps = math.cos(math.radians(key["pitch"])), math.sin(math.radians(key["pitch"]))
            h0 = rig.world[rig.bone[J["hips"]]] if rig.bone[J["hips"]] >= 0 else None
            cx, cz = (h0[3], h0[11]) if h0 else (0, 0)
            def pt(b):
                w = world[b]
                x, y, z = w[3] - cx, w[7] - rig.hips_y, w[11] - cz
                y, z = y * pc - z * ps, y * ps + z * pc
                return x, y + rig.hips_y * (1 - key["drop"]), z
            def tip(b):                              # the end of a chain: the joint's first moved child, or itself
                for c in kids.get(b, []):
                    if c not in rig.hide and sum((world[c][4 * r + 3] - world[b][4 * r + 3]) ** 2 for r in range(3)) > 0.01:
                        return c
                return b
            for view in (0, 1):
                ox = col * cw + (40 if view == 0 else 110)
                oy = 14 + row * ch + ch - 10
                sc = (ch - 30) / H
                P = (lambda v: (ox + v[0] * sc * 0.6, oy - v[1] * sc)) if view == 0 else                     (lambda v: (ox + v[2] * sc * 0.6, oy - v[1] * sc))
                d.line([(ox - 25, oy), (ox + 25, oy)], fill=(180, 180, 180))
                for chain in CHAINS:
                    bones = [rig.bone[J[n]] for n in chain if rig.bone[J[n]] >= 0]
                    if not bones:
                        continue
                    bones.append(tip(bones[-1]))
                    color = (210, 40, 40) if chain[-1].endswith("_r") else (40, 40, 210) if chain[-1].endswith("_l")                         else (30, 30, 30)
                    d.line([P(pt(b)) for b in bones], fill=color, width=2)
            if row == 0:
                d.text((col * cw + 4, 2), f"{name} {k}  front | side", fill=(0, 0, 0))
        d.text((2, 14 + row * ch + 2), rigmap.NAMES[code], fill=(0, 120, 0))
    im.save(out)


if __name__ == "__main__":
    for code in rigmap.MODELS:
        rig = Rig(rigmap.load(code))
        print(f"{code:2d} {rigmap.NAMES[code]:11s} joints {sum(b >= 0 for b in rig.bone):2d} hide {rig.hide}"
              f" hips y {rig.hips_y:.1f} rest error {check_rest(rig):.1e}")
    codes = [int(a) for a in sys.argv[1:] if a.isdigit()] or [0, 1, 4, 9, 11, 12, 15, 17]
    clips = [a for a in sys.argv[1:] if not a.isdigit()]
    sheet(codes, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "screens", "fbmoves_sheet.png"),
          clips)
