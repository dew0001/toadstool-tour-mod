"""Which bones of a golfer's in-round model are its hips, spine, chest, neck, head, arms and legs (v27 Football poses).

Every golfer's skeleton is its own (Mario 118 bones, Bowser Jr 178, Boo 57), but they share a build: model space Y up,
the golfer facing +Z, its right side at -X, bind pose a T (arms along X). The joints are found from the bind
positions and the bone tree:
  - the hands are the bones farthest out along -X / +X, the feet the lowest ones out to each side (Boo has none);
  - an arm's chain runs from the hand up to the chest (the bone both arms hang from); its wrist is the deepest bone
    with three or more children (the fingers) or, with mitten hands, the hand's parent; the forearm and upper arm
    are the next bones up that sit somewhere else (twist bones share their child's place); the clavicle is the
    bone between the upper arm and the chest, when there is one;
  - a leg's chain runs from the foot up to the hips; its thigh and shin are the first two bones from the top whose
    segment (to the next bone down) is long and mostly vertical, and the foot is the bone at the shin's bottom;
  - the head is the highest bone near the middle with children (its face), the neck the head chain's bone between
    the chest and the head, the spine those between the hips and the chest; the hips (pelvis) are the bone the legs
    and the chest share, where the legs leave.
`rig(model)` answers {name: bone index}; `python rigmap.py` prints every golfer's.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model as mdl  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
# golfer code -> in-round model ([22]); 16 and 17 are built (Shy Guy on Koopa's skeleton, Tony on Waluigi's)
MODELS = {0: "C/R/T", 1: "C/S/C", 2: "C/S/K", 3: "C/S/S", 4: "C/T/B", 5: "C/T/G", 6: "C/T/P", 7: "C/T/U",
          8: "C/T/Y", 9: "C/U/G", 10: "C/U/P", 11: "C/U/U", 12: "C/U/Z", 13: "C/V/E", 14: "C/V/N", 15: "C/V/S",
          16: "C/W/B", 17: "C/W/G"}
NAMES = ("Mario", "Waluigi", "Peach", "Luigi", "Bowser", "Wario", "Metal Mario", "Birdo", "Yoshi", "DK", "Diddy",
         "Boo", "Petey", "Daisy", "Bowser Jr", "Koopa", "Shy Guy", "Tony")
JOINTS = ("hips", "spine", "chest", "neck", "head",
          "clav_r", "uarm_r", "farm_r", "hand_r", "clav_l", "uarm_l", "farm_l", "hand_l",
          "thigh_r", "shin_r", "foot_r", "thigh_l", "shin_l", "foot_l")


SKELETON_OF = {16: 15, 17: 1}   # Shy Guy is rigged on Koopa's skeleton, Tony on Waluigi's (shyguy.py, tony.py)


def load(code, root=ROOT, built=False):
    """A golfer's in-round model from the clean disc; Shy Guy's and Tony's skeletons (and clubs) are their bases',
    so theirs come from those unless `built` (then from the build tree, which a build writes after the code)."""
    if code in SKELETON_OF and not built:
        code = SKELETON_OF[code]
    top = "build" if code >= 16 else "disc"
    return mdl.Model(os.path.join(root, top, "files", *MODELS[code].split("/")))


def _dist(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def body_bones(m):
    """The bones the body (mesh part 1) moves with: its rigid groups' bones, and the skin's matrix slots (root +0x4C,
    count +0x48) when it has skinned groups. Leaves out the clubs' bones and loose ones (Peach's at y -10)."""
    out, skinned = set(), False
    for i, mo, g, go, mtx, dls in mdl.meshes(m):
        if m.u32(mo + 0x38) != 1:
            continue
        if m.u32(go) & 1:
            out |= {m.u32(go + 8 + 4 * k) for k in range(min(m.u32(go + 4), 10))}
        else:
            skinned = True
    if skinned:
        slots = m.p(m.root + 0x4C)
        out |= {m.blob[slots + k] for k in range(m.u32(m.root + 0x48))}
    return sorted(b for b in out if b < m.u32(m.root + 0x60))


class Skeleton:
    def __init__(self, m):
        self.parent = [p for p, _ in mdl.bones(m)]
        self.pos = [(w[3], w[7], w[11]) for w in mdl.world_bind(m)]
        self.kids = {i: [] for i in range(len(self.parent))}
        for i, p in enumerate(self.parent):
            if p >= 0:
                self.kids[p].append(i)
        used = body_bones(m)
        root = lambda b: self.chain(b)[-1]
        roots = [root(b) for b in used]                 # the body's tree (DK's club bones are a tree of their own)
        main = max(set(roots), key=roots.count)
        self.used = [b for b, r in zip(used, roots) if r == main]
        ys = [self.pos[i][1] for i in self.used]
        self.height = max(ys) - min(ys)

    def chain(self, b):
        """b and its ancestors, up to the root."""
        out = []
        while b >= 0:
            out.append(b)
            b = self.parent[b]
        return out

    def up_moved(self, b):
        """The nearest ancestor of b that sits somewhere else (skips twist bones sharing b's place)."""
        p = self.parent[b]
        while p >= 0 and _dist(self.pos[p], self.pos[b]) < 0.05:
            p = self.parent[p]
        return p

    def subtree(self, b):
        out, todo = [], [b]
        while todo:
            c = todo.pop()
            out.append(c)
            todo += self.kids[c]
        return out


def rig(m):
    s = Skeleton(m)
    n, P, H = len(s.parent), s.pos, s.height
    used = s.used
    out = {}
    # the hands: farthest out to each side
    hand_tip = {"r": min(used, key=lambda i: P[i][0]), "l": max(used, key=lambda i: P[i][0])}
    arm_chain = {k: s.chain(b) for k, b in hand_tip.items()}
    common = [b for b in arm_chain["r"] if b in arm_chain["l"]]
    chest = common[0]
    out["chest"] = chest
    for side, ch in arm_chain.items():
        ch = ch[:ch.index(chest)]                     # tip ... the bone under the chest
        wrist = next((b for b in reversed(ch) if len(s.kids[b]) >= 3), None)   # the first fan from the chest out
        if wrist is None:
            wrist = s.up_moved(ch[0])
        elbow = s.up_moved(wrist)
        shoulder = s.up_moved(elbow)
        if not {wrist, elbow, shoulder} <= set(ch) or len({wrist, elbow, shoulder}) < 3:
            continue                                   # no real arm (Boo's stubs)
        out["hand_" + side], out["farm_" + side], out["uarm_" + side] = wrist, elbow, shoulder
        if ch.index(shoulder) + 1 < len(ch):
            out["clav_" + side] = ch[-1]
    # the head: the highest bone near the middle, then up to the first bone with three or more children (the face)
    cx = P[chest][0]
    tops = [i for i in used if abs(P[i][0] - cx) < 0.15 * H and chest in s.chain(i)[1:]
            and not any(k in out and i in s.subtree(out[k]) for k in ("hand_r", "hand_l"))]
    if tops:                                          # (Boo is all head: none)
        head_chain = s.chain(max(tops, key=lambda i: P[i][1]))
        head_chain = head_chain[:head_chain.index(chest)]  # top ... the bone over the chest
        head = next((b for b in reversed(head_chain) if len(s.kids[b]) >= 3), head_chain[-1])
        out["head"] = head
        between = head_chain[head_chain.index(head) + 1:]
        if between:
            out["neck"] = between[-1]
    # the feet: the lowest bones out to each side (not under a hand)
    arms = {b for k in ("hand_r", "hand_l") if k in out for b in s.subtree(out[k])}
    low = [i for i in used if i not in arms and P[i][1] < 0.15 * H]
    legs = {}
    for side, sign in (("r", -1), ("l", 1)):
        cand = [i for i in low if sign * (P[i][0] - cx) > 0.015 * H]
        if cand:
            legs[side] = s.chain(min(cand, key=lambda i: (P[i][1], -sign * P[i][0])))
    chest_chain = s.chain(chest)
    if len(legs) == 2:
        hips = next(b for b in legs["r"] if b in legs["l"] and b in chest_chain)
        out["hips"] = hips
        for side, ch in legs.items():
            ch = list(reversed(ch[:ch.index(hips)]))    # from the top down
            segs = []
            for b in ch:
                c = next((k for k in ch[ch.index(b) + 1:] if _dist(P[k], P[b]) > 0.05), None)
                if c is None:
                    continue
                v = [P[c][j] - P[b][j] for j in range(3)]
                length = sum(x * x for x in v) ** 0.5
                if length > 0.05 * H and -v[1] > 0.6 * length and abs(P[b][0] - cx) > 0.03 * H:
                    segs.append((b, c))
            if len(segs) >= 2:
                out["thigh_" + side], out["shin_" + side] = segs[0][0], segs[1][0]
                out["foot_" + side] = segs[1][1]
    else:
        out["hips"] = chest_chain[1] if len(chest_chain) > 1 else chest
    spine = chest_chain[1:chest_chain.index(out["hips"])] if out["hips"] in chest_chain else []
    if spine:
        out["spine"] = spine[-1]                       # the lowest bone between the hips and the chest
    return out


if __name__ == "__main__":
    codes = [int(a) for a in sys.argv[1:]] or list(MODELS)
    for code in codes:
        m = load(code)
        r = rig(m)
        s = Skeleton(m)
        f = lambda j: f"{j}={r[j]}({s.pos[r[j]][0]:.1f},{s.pos[r[j]][1]:.1f},{s.pos[r[j]][2]:.1f})" if j in r else f"{j}=-"
        print(f"{code:2d} {NAMES[code]:11s} H {s.height:4.1f} " + " ".join(f(j) for j in JOINTS[:5]))
        print("    " + " ".join(f(j) for j in JOINTS[5:13]))
        print("    " + " ".join(f(j) for j in JOINTS[13:]))
