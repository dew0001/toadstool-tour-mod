"""Halloween costumes (v24, Andrew 2026-10-29: "add halloween costumes to every character, make birdo have big
boobs like huge but not in the way of the shot, give daisy a bikini halloween costume", "Make sure birdo chest is
big and round").

Every golfer (codes 0-17: the 16, Shy Guy, Tony) has a costume: copies of its models with pieces of our own added
(hats, horns, capes; Birdo's chest; Daisy's bikini), as new files under the disc folder I (I/<golfer letter>/A the
in-round model, B the second in-round model, D the select screen model). The player picks it with Y on the
character select screen; the normal look stays the default.

The game side (RE-NOTES "Costumes"):
  - Y on the character select (FUN_8040b9ec reads the pad's new presses in r30; Y, 0x800, is never read there):
    flips the picking player's costume word and reshows the golfer the way a cursor move does (cursor sound,
    FUN_8040a76c loads it into the other of the two model slots, the old one unloads), so the model swaps at once.
  - The select screen's model slots (FUN_804031c8, 6 of 0xA8 at 0x804490E4: the character select uses 4 and 5,
    the team and CPU screens 0-3 by player) load 0x804459A0[character code]: a costume player's file is ours.
  - Picking (FUN_8040b56c) writes the player's option byte 0x80176044 + player (bit 0 Star, 1 lefty; the course
    select adds 2 human, 3 CPU): bit 4 (0x10) = costume. The round copies it to 0x804E667C + player.
  - In a round FUN_80426104 makes each player's golfer object (FUN_804074a8 at 0x80426240) and asks its vtable
    methods [22] model, [23] bank and [24] second model for file IDs, each `lis r3,0; addi r3,r3,ID; blr` with
    r3 = the object. Ours: `mr r4,r3; li r3,ID; b costume_map`, which swaps in the costume's ID when the object is
    one a costume player made (costume_obj, filled at its making).
"""
import math
import struct

import numpy as np

import camelot_lz as lz
import model as mdl
import ppc
import shyguy

# ---------------------------------------------------------------- the game side

CAVES = {   # name: (address, size, first word): dead main.dol functions (find_dead_code.py: DEAD)
    "data": (0x80023518, 284, 0x9421FFE0),   # the words, the ID table, the lookup
    "menu": (0x80037EDC, 284, 0x7C0802A6),   # Y, picking, the select screen's model files
    "round": (0x80023188, 280, 0x9421FFE0),  # the golfer objects, the methods' stub
}
GOLF_VTABLES = {0: 0x804C8C50, 1: 0x804C9DA8, 2: 0x804C97C0, 3: 0x804C9A18, 4: 0x804C9C70, 5: 0x804C9EE0,
                6: 0x804CA018, 7: 0x804CA770, 8: 0x804C9B50, 9: 0x804CA500, 10: 0x804CA150, 11: 0x804CA638,
                12: 0x804CA288, 13: 0x804C98E0, 14: 0x804CCC30, 15: 0x804CA3C8, 16: 0x804CC948, 17: 0x804CABC8}
NAMES = ["Mario", "Waluigi", "Peach", "Luigi", "Bowser", "Wario", "Metal Mario", "Birdo", "Yoshi", "Donkey Kong",
         "Diddy Kong", "Boo", "Petey Piranha", "Daisy", "Bowser Jr.", "Koopa Troopa", "Shy Guy", "Tony the Tiger"]
CHAR_OF_GOLFER = [0, 9, 2, 1, 11, 8, 14, 10, 4, 6, 7, 13, 15, 3, 12, 5, 16, 17]   # select grid order (0x80445D34)
SELECT_MODELS = 0x804459A0          # menu overlay: u32 file IDs by character code (16, 17: the More page's)
METHODS = (22, 23, 24)              # vtable methods we swap: model, texture bank, second model
KINDS = {22: 0, 24: 1, 23: 2, "select": 3}  # costume file letter (A, B, C, D) of each
FOLDER = 8                          # I
ROUNDS = 4

Y_HOOK, Y_WORD = 0x8040CC64, 0x801FBAB0     # menu: lwz r0,-17744(r31) (page flag), the lefty check's start
Y_RESHOW = 0x8040D3C0               # li r3,1; li r4,255; bl cursor sound; bl FUN_8040a76c; b frame end
Y_BACK = 0x8040CC68
PICK_HOOK = 0x8040B6B0              # menu: bl FUN_800130f8 at the end of FUN_8040b56c's option byte code
PICK_TARGET = 0x800130F8
SLOT_HOOK, SLOT_WORD = 0x80403224, 0x7C8B482E   # menu: lwzx r4,r11,r9 (r31 = the slot, then bl FUN_8000f044)
SLOTS = 0x804490E4
SLOT_SIZE = 0xA8
PICKER = 0x8044BA44                 # the player picking on the character select
OPTIONS_MENU = 0x80176044           # option byte per player (menus)
OPTIONS_ROUND = 0x804E667C          # the round's copy
COSTUME_BIT = 0x10
NEW_HOOK = 0x80426240               # golf: bl FUN_804074a8 (r31 = the player record) in FUN_80426104
NEW_TARGET = 0x804074A8
PLAYER_INDEX = 0x5160


def costume_id(golfer, kind):
    """File ID of I/<golfer letter>/<kind letter> (odd, like the golfers' own)."""
    return 2 * (676 * FOLDER + 26 * golfer + kind) + 1


def path_of(fid):
    n = fid // 2
    return "/".join(chr(65 + x) for x in (n // 676, n // 26 % 26, n % 26))


def golf_methods(golf):
    """{golfer: {22: (method address, file ID), 24: ...}} from the golf overlay's vtables (simple methods only)."""
    w = lambda a: struct.unpack_from(">I", golf, a - 0x80400000)[0]
    out = {}
    for g, vt in GOLF_VTABLES.items():
        out[g] = {}
        for k in METHODS:
            m = w(vt + 4 * k)
            words = [w(m + 4 * i) for i in range(3)]
            if words[0] == 0x3C600000 and words[1] >> 16 == 0x3863 and words[2] == 0x4E800020:
                out[g][k] = (m, words[1] & 0xFFFF)
    return out


def select_ids(menu):
    return [struct.unpack_from(">I", menu, SELECT_MODELS - 0x80400000 + 4 * c)[0] for c in range(18)]


def table(golf, menu, have):
    """The original file IDs our lookup knows, 4 halfwords a golfer (kind order: model, second, -, select); 0 =
    no costume file. have: {golfer: set of kinds with a costume file}."""
    meth, sel = golf_methods(golf), select_ids(menu)
    out = [0] * (4 * 18)
    for g in range(18):
        for k, kind in KINDS.items():
            if kind not in have.get(g, ()):
                continue
            out[4 * g + kind] = sel[CHAR_OF_GOLFER[g]] if k == "select" else meth[g][k][1]
    return out


def lhzu(rd, d, ra):
    return ppc._d(41, rd, d, ra)


def lbzx(rd, ra, rb):
    return ppc.lbzx(rd, ra, rb)


def data_code(ids):
    a = ppc.Asm(CAVES["data"][0])
    for i in range(ROUNDS):
        a.word(f"on{i}")            # the picking player's costume word (character select)
    for i in range(ROUNDS):
        a.word(f"obj{i}")           # golfer objects of costume players (round)
    a.label("ids")
    for i in range(0, len(ids), 2):
        a(ids[i] << 16 | ids[i + 1])
    # Leaf: r6 = a file ID; if the table has it, r6 = the costume's (r7 = the kinds to look at: a mask of 1 << kind).
    # Uses r0, r7, r8, r10.
    a.label("lookup")
    a.la(8, "ids")
    a(ppc.addi(8, 8, -2), ppc.li(10, 0))
    a.label("lu_next")
    a(lhzu(0, 2, 8), ppc.cmpw(0, 6))
    a.br("bne", "lu_skip")
    a(ppc.rlwinm(0, 10, 0, 30, 31), ppc.li(8, 1))   # kind = k & 3: is it one we look for?
    a(0x7D080030)                                    # slw r8,r8,r0
    a(0x7D083839)                                    # and. r8,r8,r7
    a.br("beq", "lu_none")
    a(ppc.srwi(8, 10, 2), ppc.mulli(8, 8, 52), ppc.slwi(0, 0, 1), ppc.add(8, 8, 0),
      ppc.addi(6, 8, costume_id(0, 0)), ppc.BLR)
    a.label("lu_skip")
    a(ppc.addi(10, 10, 1), ppc.cmpwi(10, len(ids)))
    a.br("blt", "lu_next")
    a.label("lu_none")
    a(ppc.BLR)
    return a


def menu_code(d):
    a = ppc.Asm(CAVES["menu"][0])
    # Replaces Y_WORD (b): Y flips the picking player's costume and shows the golfer again; else the lefty check.
    a.label("y")
    a(ppc.andi_(0, 30, 0x800))
    a.br("beq", "y_none")
    hi, lo = ppc.hi_lo(PICKER)
    a(ppc.lis(9, hi), ppc.lwz(11, lo, 9), ppc.slwi(11, 11, 2))
    hi, lo = ppc.hi_lo(d["on0"])
    a(ppc.lis(9, hi), ppc.addi(9, 9, lo), ppc.add(9, 9, 11), ppc.lwz(0, 0, 9), ppc.cmpwi(0, 0), ppc.li(0, 1))
    a.br("beq", "y_set")
    a(ppc.li(0, 0))
    a.label("y_set")
    a(ppc.stw(0, 0, 9))
    a.b(Y_RESHOW)
    a.label("y_none")
    a(Y_WORD)
    a.b(Y_BACK)

    # Replaces `bl FUN_800130f8` at PICK_HOOK: a costume pick sets bit 4 of the player's option byte.
    a.label("pick")
    hi, lo = ppc.hi_lo(PICKER)
    a(ppc.lis(9, hi), ppc.lwz(11, lo, 9), ppc.slwi(12, 11, 2))
    hi, lo = ppc.hi_lo(d["on0"])
    a(ppc.lis(9, hi), ppc.addi(9, 9, lo), ppc.add(9, 9, 12), ppc.lwz(0, 0, 9), ppc.cmpwi(0, 0))
    a.br("beq", "pick_done")
    hi, lo = ppc.hi_lo(OPTIONS_MENU)
    a(ppc.lis(9, hi), ppc.addi(9, 9, lo), ppc.add(9, 9, 11), ppc.lbz(0, 0, 9), ppc.ori(0, 0, COSTUME_BIT),
      ppc.stb(0, 0, 9))
    a.label("pick_done")
    a.b(PICK_TARGET)

    # Replaces `lwzx r4,r11,r9` at SLOT_HOOK (bl; r3 = r31 = the slot): the model file of a costume player's
    # golfer is the costume's. Slots 4 and 5: the picking player's word; 0-3: that player's option byte.
    a.label("slot")
    a(SLOT_WORD)
    hi, lo = ppc.hi_lo(SLOTS)
    a(ppc.lis(12, hi), ppc.addi(12, 12, lo), ppc.subf(12, 12, 31), ppc.li(0, SLOT_SIZE), ppc.divw(12, 12, 0),
      ppc.cmpwi(12, ROUNDS))
    a.br("blt", "slot_player")
    hi, lo = ppc.hi_lo(PICKER)
    a(ppc.lis(12, hi), ppc.lwz(12, lo, 12), ppc.slwi(12, 12, 2))
    hi, lo = ppc.hi_lo(d["on0"])
    a(ppc.lis(11, hi), ppc.addi(11, 11, lo), ppc.add(11, 11, 12), ppc.lwz(0, 0, 11), ppc.cmpwi(0, 0))
    a.br("beq", "slot_done")
    a.br("b", "slot_map")
    a.label("slot_player")
    hi, lo = ppc.hi_lo(OPTIONS_MENU)
    a(ppc.lis(11, hi), ppc.addi(11, 11, lo), lbzx(0, 11, 12), ppc.andi_(0, 0, COSTUME_BIT))
    a.br("beq", "slot_done")
    a.label("slot_map")
    a(ppc.mflr(5), ppc.mr(6, 4), ppc.li(7, 1 << KINDS["select"]))
    a.bl(d["lookup"])
    a(ppc.mr(4, 6), ppc.mtlr(5))
    a.label("slot_done")
    a(ppc.BLR)
    return a


def round_code(d):
    a = ppc.Asm(CAVES["round"][0])
    # Replaces `bl FUN_804074a8` at NEW_HOOK (r31 = the player record): makes the golfer, then notes it if the
    # player picked the costume (and forgets any old entry at the same address: objects of past rounds).
    a.label("new")
    a(ppc.stwu(1, -16, 1), ppc.mflr(0), ppc.stw(0, 20, 1))
    a.bl(NEW_TARGET)
    a.la(11, "_obj")
    a(ppc.li(12, 0))
    a.label("new_old")
    a(ppc.slwi(0, 12, 2), ppc.add(10, 11, 0), ppc.lwz(0, 0, 10), ppc.cmpw(0, 3))
    a.br("bne", "new_keep")
    a(ppc.li(0, 0), ppc.stw(0, 0, 10))
    a.label("new_keep")
    a(ppc.addi(12, 12, 1), ppc.cmpwi(12, ROUNDS))
    a.br("blt", "new_old")
    a(ppc.lwz(12, PLAYER_INDEX, 31))
    hi, lo = ppc.hi_lo(OPTIONS_ROUND)
    a(ppc.lis(10, hi), ppc.addi(10, 10, lo), lbzx(0, 10, 12), ppc.andi_(0, 0, COSTUME_BIT), ppc.li(0, 0))
    a.br("beq", "new_store")
    a(ppc.mr(0, 3))
    a.label("new_store")
    a(ppc.slwi(12, 12, 2), ppc.add(11, 11, 12), ppc.stw(0, 0, 11))
    a(ppc.lwz(0, 20, 1), ppc.mtlr(0), ppc.addi(1, 1, 16), ppc.BLR)

    # Reached with `b` from a golfer's [22] / [24] method (r3 = its file ID, r4 = the object): a costume player's
    # golfer gets the costume's file.
    a.label("map")
    a.la(11, "_obj")
    a(ppc.li(12, ROUNDS))
    a.label("map_next")
    a(ppc.lwz(0, 0, 11), ppc.cmpw(0, 4))
    a.br("beq", "map_hit")
    a(ppc.addi(11, 11, 4), ppc.addi(12, 12, -1), ppc.cmpwi(12, 0))
    a.br("bne", "map_next")
    a(ppc.BLR)
    a.label("map_hit")
    a(ppc.mflr(5), ppc.mr(6, 3), ppc.li(7, 1 << KINDS[22] | 1 << KINDS[23] | 1 << KINDS[24]))
    a.bl(d["lookup"])
    a(ppc.mr(3, 6), ppc.mtlr(5), ppc.BLR)
    a.labels["_obj"] = d["obj0"]
    return a


class _Labels(dict):
    def __missing__(self, key):
        return CAVES["data"][0]


def caves(golf, menu, have):
    """[(address, first word, bytes)] and the labels. have: {golfer: set of kinds with a costume file}."""
    ids = table(golf, menu, have)
    da = data_code(ids)
    d_code = da.assemble()
    d = da.labels
    m = menu_code(d)
    r = round_code(d)
    r.labels.pop("_obj")
    r.labels["_obj"] = d["obj0"]
    out, sizes = [], {}
    for name, code in (("data", d_code), ("menu", m.assemble()), ("round", r.assemble())):
        at, size, first = CAVES[name]
        if len(code) > size:
            raise SystemExit(f"costumes, cave {name}: {len(code)} bytes; only {size} fit")
        out.append((at, first, code))
        sizes[name] = len(code)
    labels = {**d, **m.labels, **r.labels, "_sizes": sizes, "_methods": golf_methods(golf), "_have": have}
    return out, labels


# ---------------------------------------------------------------- reading a golfer's body

BODY_PART = 1


def skin_bones(m):
    """{skinned position index: dominant bone} from the skin blocks (pairs; extras ignored)."""
    r = m.root
    slots_at, nslots = m.p(r + 0x4C), m.u32(r + 0x48)
    slots = list(m.blob[slots_at:slots_at + nslots]) if slots_at is not None else []
    out = {}
    blk = m.p(r + 0x54)
    for k in range(m.u32(r + 0x50)):
        o = blk + 0x20 * k
        p0, nruns = m.u32(o), m.u32(o + 0xC)
        W, R = m.p(o + 8), m.p(o + 0x10)
        v, wi = p0, W
        for i in range(nruns):
            a, b, c = struct.unpack_from(">BBH", m.blob, R + 4 * i)
            for _ in range(c):
                wa, wb = struct.unpack_from(">bb", m.blob, wi)
                wi += 2
                out[v] = slots[a] if wa >= wb else slots[b]
                v += 1
    return out


def body_points(m, parts=(BODY_PART,)):
    """Every body vertex (meshes of the given parts) in bind pose: (positions Nx3, dominant bone N)."""
    rigid = np.array(mdl.positions(m)) if m.u32(m.root + 0xC) else np.zeros((0, 3))
    # the skin blocks write past the source array's copied head (root +0x14), up to the buffers' size (root +0x0C)
    skinned = np.array(mdl.array(m, 4, 0x10, m.u32(m.root + 0xC), 3)) if m.p(m.root + 0x10) is not None \
        else np.zeros((0, 3))
    sb = skin_bones(m) if len(skinned) else {}
    seen, pts, bones = set(), [], []
    for i, mo, g, go, mtx, dls in mdl.meshes(m):
        if m.u32(mo + 0x38) not in parts:
            continue
        is_rigid = m.u32(go) & 1
        for dl, size in dls:
            try:
                tris = mdl.triangles(m, mo, m.u32(go + 4), dl, size)
            except ValueError:      # a list in a layout this reader doesn't know: skip it
                continue
            for tri in tris:
                for slot, pos, _, _ in tri:
                    key = (is_rigid, pos)
                    if key in seen:
                        continue
                    seen.add(key)
                    if is_rigid:
                        if pos < len(rigid) and slot < len(mtx):
                            pts.append(rigid[pos])
                            bones.append(mtx[slot])
                    elif pos < len(skinned) and pos in sb:
                        pts.append(skinned[pos])
                        bones.append(sb[pos])
    return np.array(pts), np.array(bones)


def body_triangles(m, parts=(BODY_PART,)):
    """The body's triangles in bind pose, (n, 3, 3)."""
    rigid = np.array(mdl.positions(m)) if m.u32(m.root + 0xC) else np.zeros((0, 3))
    skinned = np.array(mdl.array(m, 4, 0x10, m.u32(m.root + 0xC), 3)) if m.p(m.root + 0x10) is not None \
        else np.zeros((0, 3))
    out = []
    for i, mo, g, go, mtx, dls in mdl.meshes(m):
        if m.u32(mo + 0x38) not in parts:
            continue
        src = rigid if m.u32(go) & 1 else skinned
        for dl, size in dls:
            try:
                tris = mdl.triangles(m, mo, m.u32(go + 4), dl, size)
            except ValueError:
                continue
            for tri in tris:
                if all(v[1] < len(src) for v in tri):
                    out.append([src[v[1]] for v in tri])
    return np.array(out)


def front_z(tris, x, y):
    """How far forward (+z) the body's surface is at (x, y), or None (rays along -z, Moller-Trumbore)."""
    o = np.array([x, y, 1e3])
    d = np.array([0.0, 0.0, -1.0])
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    e1, e2 = b - a, c - a
    p = np.cross(d, e2)
    det = (e1 * p).sum(1)
    ok = np.abs(det) > 1e-9
    inv = np.where(ok, 1 / np.where(ok, det, 1), 0)
    s = o - a
    u = (s * p).sum(1) * inv
    q = np.cross(s, e1)
    v = (q * d).sum(1) * inv
    t = (e2 * q).sum(1) * inv
    hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0)
    return float(1e3 - t[hit].min()) if hit.any() else None


def body_points_uv(m, parts=(BODY_PART,)):
    """Every body vertex corner in bind pose with its dominant bone and texcoord: (positions, bones, uvs)."""
    rigid = np.array(mdl.positions(m)) if m.u32(m.root + 0xC) else np.zeros((0, 3))
    skinned = np.array(mdl.array(m, 4, 0x10, m.u32(m.root + 0xC), 3)) if m.p(m.root + 0x10) is not None \
        else np.zeros((0, 3))
    sb = skin_bones(m) if len(skinned) else {}
    uvs = np.array(mdl.texcoords(m))
    seen, P, B, U = set(), [], [], []
    for i, mo, g, go, mtx, dls in mdl.meshes(m):
        if m.u32(mo + 0x38) not in parts:
            continue
        is_rigid = m.u32(go) & 1
        for dl, size in dls:
            try:
                tris = mdl.triangles(m, mo, m.u32(go + 4), dl, size)
            except ValueError:
                continue
            for tri in tris:
                for slot, pos, _, tex in tri:
                    key = (is_rigid, pos, tex)
                    if key in seen or tex is None or tex >= len(uvs):
                        continue
                    seen.add(key)
                    if is_rigid and pos < len(rigid) and slot < len(mtx):
                        P.append(rigid[pos]), B.append(mtx[slot]), U.append(uvs[tex])
                    elif not is_rigid and pos < len(skinned) and pos in sb:
                        P.append(skinned[pos]), B.append(sb[pos]), U.append(uvs[tex])
    return np.array(P), np.array(B), np.array(U)


def kabsch(a, b):
    """Rotation R and shift t with R a + t ~ b (least squares)."""
    ca, cb = a.mean(0), b.mean(0)
    u, _, vt = np.linalg.svd((a - ca).T @ (b - cb))
    d = np.sign(np.linalg.det(vt.T @ u.T))
    R = vt.T @ np.diag([1, 1, d]) @ u.T
    return R, cb - R @ ca


def common_ancestor(m, bones):
    """The deepest bone that all of `bones` are (or descend from): a head's vertices blend its face's bones (lips,
    leaves), which an idle animation moves on their own; the head itself carries a hat steadily."""
    par, _, _ = skeleton(m)
    chain = lambda b: [b] + chain(par[b]) if b >= 0 else []
    common = set(chain(bones[0]))
    for b in bones[1:]:
        common &= set(chain(b))
    return next(b for b in chain(bones[0]) if b in common) if common else bones[0]


def carry_uv(pieces, src, dst):
    """Pieces made on model src carried onto model dst (the same golfer's other model, possibly posed otherwise:
    select screen models): the vertices riding each piece's bone (its own, or its subtree when few) are paired
    with dst's by texcoord (the same mesh in both), a rotation and shift fitted (outliers dropped), and the piece
    rides the deepest bone common to those most of the paired vertices near it ride. None when too few pair
    up."""
    ps, bs, us = body_points_uv(src)
    pd, bd, ud = body_points_uv(dst)
    _, _, ks = skeleton(src)
    off = np.median(pd, 0) - np.median(ps, 0)
    out = []
    for bone, mesh in pieces:
        sel = bs == bone
        if sel.sum() < 12:
            sel = np.isin(bs, subtree(ks, bone))
        A, UA = ps[sel], us[sel]
        pairs = []
        for a, ua in zip(A, UA):
            c = np.where(np.abs(ud - ua).max(1) < 2e-4)[0]
            if len(c):
                j = c[np.argmin(((pd[c] - (a + off)) ** 2).sum(1))]
                pairs.append((a, j))
        if len(pairs) < 8:
            return None
        a = np.array([p for p, _ in pairs])
        j = np.array([k for _, k in pairs])
        b = pd[j]
        R, t = kabsch(a, b)
        for _ in range(2):                      # drop pairs that don't follow (seams matched elsewhere)
            err = np.linalg.norm(a @ R.T + t - b, axis=1)
            keep = err <= max(3 * np.median(err), 0.05)
            if keep.sum() < 8:
                break
            a, b, j = a[keep], b[keep], j[keep]
            R, t = kabsch(a, b)
        near = np.argsort(((a - mesh.pos.mean(0)) ** 2).sum(1))[:max(8, len(a) // 3)]
        bones, counts = np.unique(bd[j[near]], return_counts=True)
        order = np.argsort(-counts)
        main = bones[order[:np.searchsorted(np.cumsum(counts[order]), 0.8 * counts.sum()) + 1]]
        M = np.eye(4)
        M[:3, :3], M[:3, 3] = R, t
        out.append((common_ancestor(dst, [int(b) for b in main]), mesh.moved(M)))
    return out


def skeleton(m):
    """(parents, world bind matrices, children lists)."""
    par = [p for p, _ in mdl.bones(m)]
    kids = [[] for _ in par]
    for b, p in enumerate(par):
        if p >= 0:
            kids[p].append(b)
    return par, mdl.world_bind(m), kids


def subtree(kids, b):
    out, todo = [], [b]
    while todo:
        x = todo.pop()
        out.append(x)
        todo += kids[x]
    return out


def body_info(m):
    """The head bone (most children: the face's), neck and chest (its parent and grandparent), and the head's shape
    from the vertices riding the head and its children: centre, top, radius (bind pose, model space)."""
    par, world, kids = skeleton(m)
    pts, bones = body_points(m)
    head = max(range(len(par)), key=lambda b: (len(kids[b]), world[b][7]))
    sub = set(subtree(kids, head))
    hp = pts[np.isin(bones, list(sub))]
    neck = par[head] if par[head] >= 0 else head
    chest = par[neck] if par[neck] >= 0 else neck
    centre = hp.mean(0) if len(hp) else np.array([world[head][3], world[head][7], world[head][11]])
    top = hp[:, 1].max() if len(hp) else centre[1]
    radius = np.percentile(np.hypot(hp[:, 0] - centre[0], hp[:, 2] - centre[2]), 90) if len(hp) else 1.0
    lo = pts[:, 1].min() if len(pts) else 0.0
    return {"head": head, "neck": neck, "chest": chest, "centre": centre, "top": float(top),
            "radius": float(radius), "height": float(top - lo), "points": len(hp), "all": (pts, bones)}


# ---------------------------------------------------------------- pieces of our own

class Mesh:
    """Triangles of our own: per-vertex positions, normals and atlas texcoords (0..1, v down), triangles as vertex
    index triples counter-clockwise seen from outside (an OBJ's winding; GX's is the other way)."""

    def __init__(self, pos, nrm, uv, tris):
        self.pos, self.nrm = np.asarray(pos, float).reshape(-1, 3), np.asarray(nrm, float).reshape(-1, 3)
        self.uv, self.tris = np.asarray(uv, float).reshape(-1, 2), np.asarray(tris, int).reshape(-1, 3)

    def __add__(self, other):
        return Mesh(np.vstack([self.pos, other.pos]), np.vstack([self.nrm, other.nrm]), np.vstack([self.uv, other.uv]),
                    np.vstack([self.tris, other.tris + len(self.pos)]))

    def moved(self, mtx):
        """Through a 3x4 (or 4x4) affine matrix; normals by its inverse transpose."""
        m = np.asarray(mtx, float).reshape(-1, 4)[:3]
        lin = m[:, :3]
        nrm = self.nrm @ np.linalg.inv(lin)
        nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
        return Mesh(self.pos @ lin.T + m[:, 3], nrm, self.uv, self.tris)

    def two_sided(self):
        back = Mesh(self.pos, -self.nrm, self.uv, self.tris[:, ::-1])
        return self + back


def affine(rot=np.eye(3), move=(0, 0, 0), scale=1.0):
    m = np.eye(4)
    m[:3, :3] = np.asarray(rot, float) * scale
    m[:3, 3] = move
    return m


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def lathe(profile, tile, seg=20, radial=None, bend=None, u_span=1.0):
    """A surface of revolution round +y: profile [(radius, y)] from bottom to top; tile = the atlas rectangle
    (u0, v0, u1, v1) its texcoords span (u round the axis from the front, +z, v down the profile). radial(theta)
    scales the radius (pumpkin ribs); bend(y) = (dx, dz) shifts each ring (a witch hat's bent tip)."""
    u0, v0, u1, v1 = tile
    prof = np.asarray(profile, float)
    lengths = np.concatenate([[0], np.cumsum(np.hypot(np.diff(prof[:, 0]), np.diff(prof[:, 1])))])
    t = lengths / max(lengths[-1], 1e-9)
    pos, uv = [], []
    for i, (r, y) in enumerate(prof):
        dx, dz = bend(y) if bend else (0.0, 0.0)
        for j in range(seg + 1):
            th = 2 * math.pi * j / seg
            rr = r * (radial(th) if radial else 1.0)
            pos.append((dx + rr * math.sin(th), y, dz + rr * math.cos(th)))
            uv.append((u0 + (u1 - u0) * ((j / seg * u_span + 0.5 - u_span / 2) % 1.0 if u_span < 1 else j / seg),
                       v0 + (v1 - v0) * (1 - t[i])))
    pos = np.array(pos)
    tris = []
    w = seg + 1
    for i in range(len(prof) - 1):
        for j in range(seg):
            a, b, c, d = i * w + j, i * w + j + 1, (i + 1) * w + j, (i + 1) * w + j + 1
            tris += [(a, b, d), (a, d, c)]
    nrm = vertex_normals(pos, tris)
    return Mesh(pos, nrm, uv, tris)


def vertex_normals(pos, tris):
    pos = np.asarray(pos, float)
    n = np.zeros_like(pos)
    for a, b, c in tris:
        f = np.cross(pos[b] - pos[a], pos[c] - pos[a])
        n[a] += f
        n[b] += f
        n[c] += f
    # rings that close on themselves (the seam's two copies of a vertex) share their normals
    key = {}
    for i, p in enumerate(np.round(pos, 5)):
        key.setdefault(tuple(p), []).append(i)
    for same in key.values():
        if len(same) > 1:
            n[same] = n[same].sum(0)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)


def ellipsoid(rx, ry, rz, tile, seg=20, rings=12, radial=None):
    prof = [(math.sin(math.pi * k / rings), -math.cos(math.pi * k / rings)) for k in range(rings + 1)]
    m = lathe([(r, y) for r, y in prof], tile, seg, radial=radial)
    m.pos *= (rx, ry, rz)
    m.nrm = vertex_normals(m.pos, m.tris)
    return m


def sheet(width, length, tile, cols=8, rows=8, curve=0.0, flare=0.0):
    """A cape: x across (-width/2..width/2), hanging down from y = 0 to -length, bowed back (-z) by curve at the
    sides and flaring out (wider, further back) by `flare` at the bottom."""
    u0, v0, u1, v1 = tile
    pos, uv, tris = [], [], []
    for i in range(rows + 1):
        s = i / rows
        half = width / 2 * (1 + flare * s)
        for j in range(cols + 1):
            t = j / cols
            x = -half + 2 * half * t
            z = -curve * (2 * t - 1) ** 2 - flare * length * 0.35 * s
            pos.append((x, -length * s, z))
            uv.append((u0 + (u1 - u0) * t, v0 + (v1 - v0) * s))
    w = cols + 1
    for i in range(rows):
        for j in range(cols):
            a, b, c, d = i * w + j, i * w + j + 1, (i + 1) * w + j, (i + 1) * w + j + 1
            tris += [(a, c, d), (a, d, b)]          # outside = the back (-z)
    pos = np.array(pos)
    return Mesh(pos, vertex_normals(pos, tris), uv, tris)


TILE = 32       # atlas tiles: 4 x 4 of 32 pixels in a 128 x 128 texture
ATLAS = 128


def tile_rect(k, inset=2):
    x, y = (k % 4) * TILE, (k // 4) * TILE
    return ((x + inset) / ATLAS, (y + inset) / ATLAS, (x + TILE - inset) / ATLAS, (y + TILE - inset) / ATLAS)


COLOURS = {"black": (28, 24, 34), "orange": (240, 120, 20), "purple": (110, 40, 150), "red": (190, 20, 30),
           "green": (40, 110, 50), "stem": (70, 110, 40), "white": (235, 235, 230), "bone": (230, 222, 200),
           "dark red": (110, 10, 20), "gold": (230, 180, 40)}


def atlas_image(tiles):
    """tiles: {tile index: colour name, or ("pumpkin",), ("stripes", a, b), ...}: the 128 x 128 picture."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (ATLAS, ATLAS), COLOURS["black"])
    d = ImageDraw.Draw(img)
    for k, what in tiles.items():
        x, y = (k % 4) * TILE, (k // 4) * TILE
        box = (x, y, x + TILE - 1, y + TILE - 1)
        if isinstance(what, str):
            d.rectangle(box, fill=COLOURS[what])
        elif what[0] == "pumpkin":      # orange with a jack-o'-lantern face in the middle (the front)
            d.rectangle(box, fill=COLOURS["orange"])
            for i in range(0, TILE, 4):     # ribs
                d.line((x + i, y, x + i, y + TILE - 1), fill=(220, 100, 15))
            cx, cy = x + TILE // 2, y + 13
            d.polygon([(cx - 8, cy - 2), (cx - 4, cy - 2), (cx - 6, cy - 6)], fill=COLOURS["black"])
            d.polygon([(cx + 4, cy - 2), (cx + 8, cy - 2), (cx + 6, cy - 6)], fill=COLOURS["black"])
            d.polygon([(cx - 1, cy + 1), (cx + 1, cy + 1), (cx, cy - 1)], fill=COLOURS["black"])
            d.polygon([(cx - 9, cy + 4), (cx + 9, cy + 4), (cx + 6, cy + 8), (cx + 3, cy + 6), (cx, cy + 9),
                       (cx - 3, cy + 6), (cx - 6, cy + 8)], fill=COLOURS["black"])
        elif what[0] == "stripes":      # horizontal bands
            a, b = COLOURS[what[1]], COLOURS[what[2]]
            for i in range(TILE):
                d.line((x, y + i, x + TILE - 1, y + i), fill=a if (i // 4) % 2 == 0 else b)
        elif what[0] == "trim":         # a colour with a band of another along the bottom
            d.rectangle(box, fill=COLOURS[what[1]])
            d.rectangle((x, y + TILE - 9, x + TILE - 1, y + TILE - 1), fill=COLOURS[what[2]])
    return img


# Pieces of our own on a costume: only Birdo's chest (head, neck and torso bones of her in-round model). The hats,
# pumpkins, horns and capes every golfer first had were dropped (Andrew: "these costumes look awful out of place not
# sitting correctly a bunch of copies"); the looks are repaints now (looks.py). The builders stay for later use.
OUTFITS = {
    7: {"bones": (86, 85, 21), "items": [("chest",)]},                              # Birdo
}


def head_shape(m, head, top=None):
    """Where a hat goes: (top y, centre x, centre z of the top part, radius) of the head and its children's
    vertices (bind pose); top: only the highest part of them, as a share of their height (a head that is a body)."""
    if (id(m), head) in _SHAPES:
        return _SHAPES[(id(m), head)]
    par, world, kids = skeleton(m)
    pts, bones = body_points(m)
    hp = pts[np.isin(bones, subtree(kids, head))]
    if not len(hp):
        raise SystemExit(f"costumes: no vertices on head bone {head}")
    if top:
        hp = hp[hp[:, 1] > hp[:, 1].max() - top * (hp[:, 1].max() - hp[:, 1].min())]
    return shape_of(hp)


_SHAPES = {}    # (model, head bone): a head shape found another way (head_match)


def head_points(m, head, top=None):
    """The vertices of the head and its children (bind pose); top: only the highest share of them."""
    _, _, kids = skeleton(m)
    pts, bones = body_points(m)
    hp = pts[np.isin(bones, subtree(kids, head))]
    if top:
        hp = hp[hp[:, 1] > hp[:, 1].max() - top * (hp[:, 1].max() - hp[:, 1].min())]
    return hp


def seat(hp, cx, cz, lowest, inside, reach):
    """The lowest height (from `lowest` up) a hat's base can sit at so that every head vertex above it is inside
    the hat (inside(dy, d): is a point dy over the base, d off the axis, inside it): hair, crowns and caps stay
    under it instead of poking through (Andrew: Daisy's hair through her hat). Only vertices under the hat's
    reach count: hair further out (Peach's ponytail) is beside it, not through it."""
    d = np.hypot(hp[:, 0] - cx, hp[:, 2] - cz)
    hp, d = hp[d <= reach], d[d <= reach]
    h = lowest
    for _ in range(200):
        up = hp[:, 1] > h
        if not up.any() or inside(hp[up, 1] - h, d[up]).all():
            return h
        h += 0.02 * max(1e-3, float(np.ptp(hp[:, 1])))
    return h


def witch_hat(top, cx, cz, r, crown, band, hp=None):
    """Tiles: 0 crown colour, 1 band."""
    brim_y = top - 0.15 * r      # on top of the head (or its cap), what is above the brim inside the cone
    r *= 0.88
    if hp is not None and len(hp):
        prof_y = np.array([0, 0.32, 0.9, 1.4, 1.85, 2.1]) * r
        prof_r = np.array([0.86, 0.84, 0.62, 0.38, 0.16, 0.02]) * r
        brim_y = seat(hp, cx, cz, brim_y, lambda dy, d: d <= np.interp(dy, prof_y, prof_r, right=0) + 0.02 * r, 1.3 * r)
    hat = lathe([(1.5 * r, 0.0), (1.3 * r, 0.04 * r), (0.85 * r, 0.06 * r)], tile_rect(0), 24)  # brim, top side
    hat += lathe([(0.85 * r, 0.0), (1.5 * r, 0.0)], tile_rect(0), 24)                              # under
    hat += lathe([(0.86 * r, 0.06 * r), (0.84 * r, 0.32 * r)], tile_rect(1), 24)                    # band
    hat += lathe([(0.84 * r, 0.32 * r), (0.62 * r, 0.9 * r), (0.38 * r, 1.4 * r), (0.16 * r, 1.85 * r),
                  (0.02 * r, 2.1 * r)], tile_rect(0), 24,
                 bend=lambda y: (0.0, -0.55 * r * max(0.0, (y / (2.1 * r) - 0.45) / 0.55) ** 2))
    return hat.moved(affine(move=(cx, brim_y, cz))), {0: crown, 1: ("trim", band, "gold")}


def pumpkin_hat(top, cx, cz, r, hp=None):
    """Tiles: 2 the pumpkin (face on the front), 3 the stem."""
    rib = lambda th: 1.0 - 0.07 * (1 - math.cos(10 * th))
    p = ellipsoid(0.95 * r, 0.62 * r, 0.9 * r, tile_rect(2), 30, 12, radial=rib)
    p = p.moved(affine(move=(0, 0.62 * r, 0)))
    stem = lathe([(0.14 * r, 1.15 * r), (0.11 * r, 1.45 * r), (0.0, 1.5 * r)], tile_rect(3), 8)
    base = top - 0.35 * r
    if hp is not None and len(hp):      # inside the pumpkin's lower half (an ellipse round its middle)
        base = seat(hp, cx, cz, base, lambda dy, d: ((dy - 0.62 * r) / (0.62 * r)) ** 2 + (d / (0.9 * r)) ** 2 <= 1.0, 0.9 * r)
    return (p + stem).moved(affine(move=(cx, base, cz))), {2: ("pumpkin",), 3: "stem"}


def horns(top, cx, cz, r, colour):
    out = None
    for side in (-1, 1):
        h = lathe([(0.24 * r, 0.0), (0.18 * r, 0.35 * r), (0.1 * r, 0.7 * r), (0.0, 1.0 * r)], tile_rect(4), 10,
                  bend=lambda y: (side * 0.25 * (y / r) ** 2 * r, 0.1 * (y / r) * r))
        h = h.moved(affine(rot=rot_z(-side * 0.45), move=(cx + side * 0.55 * r, top - 0.42 * r, cz + 0.15 * r)))
        out = h if out is None else out + h
    return out, {4: colour}


def vampire(m, info, outside, inside):
    """A cape on the chest bone, from the shoulders down the back to the hips, as wide as the shoulders (the torso's
    own vertices at shoulder height, arms left out), a little off the back. Tiles: 5 outside, 6 the lining."""
    par, world, kids = skeleton(m)
    head, neck, chest = info["bones"]
    pts, bones = body_points(m)
    limbs = set()
    for k in kids[chest]:
        if k != neck and neck not in subtree(kids, k):
            limbs |= set(subtree(kids, k))
    shoulder = max((world[k][7] for k in kids[chest] if k in limbs), default=world[chest][7])
    torso = pts[~np.isin(bones, list(limbs | set(subtree(kids, neck))))]
    near = torso[np.abs(torso[:, 1] - shoulder) < 0.12 * info["height"]]
    span = float(np.abs(near[:, 0]).max()) if len(near) else 0.2 * info["height"]
    back_z = float(near[:, 2].min()) if len(near) else world[chest][11] - 1.5
    length = 0.42 * info["height"]
    cape = sheet(2.1 * span, length, tile_rect(5), curve=0.3 * span, flare=0.35)
    lining = Mesh(cape.pos, -cape.nrm, np.array(cape.uv) + (tile_rect(6)[0] - tile_rect(5)[0], 0), cape.tris[:, ::-1])
    cape = (cape + lining).moved(affine(move=(0, shoulder + 0.05 * info["height"], back_z - 0.08 * span)))
    return [(chest, cape)], {5: outside, 6: inside}


def chest(m, info):
    """Birdo: a big round chest on her torso. At address her arms hang down across the front of her chest to the
    club (Andrew: "Her boobs are in her arms at address"), so it is big and round seen from the front but shallow:
    each half stands only CHEST_OUT out of her body's surface (measured on her mesh, front_z), staying behind the
    arms (checked from the front with Dolphin's Free Look, scripts\\costume_front.ps1). Tile 8: her own pink."""
    head, neck, torso = info["bones"]
    tris = body_triangles(m)
    p = None
    for side in (-1, 1):
        x = side * CHEST_X
        z = (front_z(tris, x, CHEST_Y) or 1.8) + CHEST_OUT - CHEST_RZ
        s = ellipsoid(CHEST_RX, CHEST_RY, CHEST_RZ, tile_rect(8), 22, 14)
        s = s.moved(affine(move=(x, CHEST_Y, z)))
        p = s if p is None else p + s
    return [(torso, p)], {8: "birdo pink"}


CHEST_RX, CHEST_RY, CHEST_RZ = 1.5, 1.45, 0.9      # Birdo's chest (model units, bind pose): each half's radii,
CHEST_X, CHEST_Y, CHEST_OUT = 1.15, 7.3, 0.72      # its centre, and how far it stands out of her body (0.95 went
                                                   # into her upper arms at address; 0.72 clears them)
COLOURS["birdo pink"] = (250, 78, 180)             # her bank's body texture (C/T/T texture 4)


def outfit_pieces(g, m, bones=None, golf=None):
    """[(bone, Mesh in this model's bind pose)] and the atlas tiles of golfer g's costume on model m (its in-round
    model, or another of its models with `bones` = its head, neck and chest there; `golf` = the in-round model,
    for pieces placed by hand in its space)."""
    spec = OUTFITS[g]
    info = dict(bones=bones or spec["bones"])
    info["height"] = float(body_points(m)[0][:, 1].max())
    pieces, tiles = [], {}
    head = info["bones"][0]
    shape = lambda: head_shape(m, head, spec.get("top"))
    hp = head_points(m, head, spec.get("top")) if (id(m), head) not in _SHAPES else None
    for item in spec["items"]:
        if item[0] == "witch":
            mesh, t = witch_hat(*shape(), item[1], item[2], hp=hp)
            pieces.append((head, mesh))
        elif item[0] == "pumpkin":
            mesh, t = pumpkin_hat(*shape(), hp=hp)
            pieces.append((head, mesh))
        elif item[0] == "horns":
            mesh, t = horns(*shape(), item[1])
            pieces.append((head, mesh))
        elif item[0] == "vampire":
            more, t = vampire(m, info, item[1], item[2])
            pieces += more
        elif item[0] == "chest":
            more, t = chest(golf or m, dict(info, bones=spec["bones"]))
            pieces += carry(more, golf, m) if golf is not None else more
        else:
            continue            # the bikini is a texture change (daisy_bikini)
        tiles.update(t)
    return pieces, tiles


def add_texture(mod, tex, size, levels):
    """One more texture in a model's texture set, its data (CMPR `tex`, size (w, h), `levels` mips) inside the
    module: the header right after the pair list moves to the end to make room for one more pair. Returns its
    index."""
    root = mod.root
    ts = mod.ptr(root + 0x8C)
    ntex = mod.u32(ts + 4)
    if mod.u32(ts + 8) != 0xC:
        raise SystemExit("costumes: texture set with its pairs somewhere else")
    pairs_end = ts + 0xC + 8 * ntex
    for k in range(ntex):
        h = ts + mod.u32(ts + 0xC + 8 * k)
        if h < pairs_end + 8 and h + 0x24 > pairs_end:
            moved = mod.alloc(bytes(mod.blob[h:h + 0x24]), 4)
            mod.put32(ts + 0xC + 8 * k, moved - ts)
    if any(w >> 24 == 0 and pairs_end <= w < pairs_end + 8 for w, _ in mod.relocs):
        raise SystemExit("costumes: a pointer in the way of the new texture pair")
    data = mod.alloc(tex, 32)
    head = mod.alloc(struct.pack(">9I", size[1] << 16 | size[0], 14, data - ts, 1, 1, 5, 1, 0, (levels - 1) << 8), 4)
    mod.put32(pairs_end, head - ts)
    mod.put32(pairs_end + 4, 0)
    mod.put32(ts + 4, ntex + 1)
    return ntex


def add_pieces(raw, pieces, tex, size, levels):
    """A model file with one more mesh: our pieces as rigid groups (one bone each, model-space bind-pose positions),
    drawn with a texture of our own inside the module (CMPR `tex`, size (w, h), `levels` mips). Everything of the
    golfer's own stays as it was."""
    mod = shyguy.Module(raw)
    root = mod.root
    meshes, count = mod.ptr(root + 0x40), mod.u32(root + 0x3C)
    body = [i for i in range(count) if mod.u32(meshes + 0x3C * i + 0x38) == BODY_PART]
    tpl = next(i for i in body if mod.u32(meshes + 0x3C * i + 0x34) == 2 and mod.blob[meshes + 0x3C * i + 7] >= 1)
    # a rigid vertex is drawn through its bone's animated matrix times the bone's +0x04 matrix; in most models that
    # is the inverse of the bone's rest pose (so vertices are in model space), but some select screen models store
    # another (Petey's B/V/J, Tony's B/V/L, DK's B/U/Z): ours go into the space that matrix expects
    m = mdl.Model(raw)
    world = mdl.world_bind(m)
    bb = m.p(m.root + 0x64)
    fixed = []
    for bone, piece in pieces:
        m04 = np.vstack([np.array(struct.unpack_from(">12f", m.blob, bb + m.bone_size * bone + 4)).reshape(3, 4),
                         [0, 0, 0, 1]])
        wb = np.vstack([np.array(world[bone]).reshape(3, 4), [0, 0, 0, 1]])
        to = np.linalg.inv(m04) @ np.linalg.inv(wb)
        fixed.append((bone, piece if np.abs(to - np.eye(4)).max() < 1e-4 else piece.moved(to)))
    pieces = fixed

    width = lambda f: struct.calcsize(shyguy.FORMAT[f[0]][0])
    pf = mdl.fmt(mod.u32(root + 4), mod.blob[root + 7])
    nf = mdl.fmt(mod.u32(root + 0x18), mod.blob[root + 0x1B])
    tf = mdl.fmt(mod.u32(root + 0x2C), mod.blob[root + 0x2F])

    def grow_array(field, stride, data):
        old = mod.ptr(root + field)
        n = (shyguy.array_end(mod, old) - old) // stride if old is not None else 0
        new = mod.alloc((bytes(mod.blob[old:old + n * stride]) if n else b"") + data, 32)
        mod.set_ptr(root + field, new)
        return n

    pos = np.vstack([p.pos for _, p in pieces])
    nrm = np.vstack([p.nrm for _, p in pieces])
    uv = np.vstack([p.uv for _, p in pieces])
    p0 = grow_array(0x08, 3 * width(pf), shyguy.pack_array(pos, pf, "positions"))
    n0 = grow_array(0x1C, 3 * width(nf), shyguy.pack_array(nrm, nf, "normals"))
    t0 = grow_array(0x30, 2 * width(tf), shyguy.pack_array(uv, tf, "texcoords"))
    if max(p0, n0, t0) + len(pos) > 0x10000:
        raise SystemExit("costumes: too many vertices for 16-bit indices")

    # one rigid group per bone
    by_bone = {}
    base = 0
    for bone, piece in pieces:
        by_bone.setdefault(bone, []).extend([tuple(base + t) for t in piece.tris])
        base += len(piece.pos)
    recs, entries = bytearray(), []
    for bone, tris in by_bone.items():
        gx = [((a, a, a), (c, c, c), (b, b, b)) for a, b, c in tris]     # GX winding (clockwise)
        vertex = lambda c: struct.pack(">3H", p0 + c[0], n0 + c[2], t0 + c[1])
        dl = mod.alloc(shyguy.display_list(gx, vertex), 32)
        pts = pos[[c for t in tris for c in t]]
        entries.append((dl, len(mod.blob) - dl, pts.min(0), pts.max(0)))
        recs += struct.pack(">II", 3, 1) + struct.pack(">I", bone) + bytes(36) + struct.pack(">II", 1, 0)
    ent = mod.alloc(b"".join(struct.pack(">II6f", 0, s, *lo, *hi) for dl, s, lo, hi in entries), 32)
    for k, (dl, s, lo, hi) in enumerate(entries):
        mod.set_ptr(ent + 0x20 * k, dl)
    grp = mod.alloc(bytes(recs), 32)
    for k in range(len(entries)):
        mod.set_ptr(grp + 0x38 * k + 0x34, ent + 0x20 * k)
    bone_base = mod.ptr(root + 0x64)            # the draw works out matrices only for bones without bit 0
    for bone in by_bone:
        mod.put32(bone_base + 0x60 * bone + 0x5C, mod.u32(bone_base + 0x60 * bone + 0x5C) & ~1)

    ntex = add_texture(mod, tex, size, levels)

    # the mesh: a copy of a body mesh's record drawing our groups with our texture, after all the others
    new = mod.alloc(bytes(mod.blob[meshes:meshes + 0x3C * count]) + bytes(mod.blob[meshes + 0x3C * tpl:
                                                                                      meshes + 0x3C * tpl + 0x3C]), 4)
    for w, v in list(mod.relocs):
        if w >> 24 == 0 and meshes <= w < meshes + 0x3C * count:
            mod.relocs.append([new + (w - meshes), v])
    mo = new + 0x3C * count
    mod.put32(mo + 4, mod.u32(mo + 4) & ~0x40000000 & ~0xFFFF | 0x0101)    # no colours, one texcoord set and texture
    mod.blob[mo + 10] = ntex
    mod.put32(mo + 0x28, len(entries))
    mod.set_ptr(mo + 0x2C, grp)
    mod.put32(mo + 0x38, BODY_PART)
    mod.set_ptr(root + 0x40, new)
    mod.put32(root + 0x3C, count + 1)
    mod.blob += bytes((-len(mod.blob)) % 32)
    return mod.pack()


def bone_frames(m):
    return [np.vstack([np.asarray(w, float).reshape(3, 4), [0, 0, 0, 1]]) for w in mdl.world_bind(m)]


def carry(pieces, src, dst, tol=2.0):
    """Pieces made on model src, moved onto model dst (the same golfer's other model): each rides the matching
    bone (shyguy.bone_map) at the same place relative to it."""
    bmap = shyguy.bone_map(src, dst, tol)
    fs, fd = bone_frames(src), bone_frames(dst)
    _, _, ks = skeleton(src)
    _, _, kd = skeleton(dst)

    def norm(frames):       # bone places from the root, in skeleton heights (select screen models can sit elsewhere)
        P = np.array([f[:3, 3] for f in frames])
        h = P[:, 1].max() - P[:, 1].min()
        return (P - P[0]) / h, h

    ns, hs = norm(fs)
    nd, hd = norm(fd)
    ratio = hd / hs
    out = []
    for bone, mesh in pieces:
        b2 = bmap.get(bone)
        if b2 is None:      # skeletons laid out differently (select screen models skip bones): by place, then by
            d = np.linalg.norm(nd - ns[bone], axis=1)   # how alike the bones' child counts are (a head has its face's)
            near = [j for j in range(len(fd)) if d[j] < d.min() + 0.04]
            b2 = min(near, key=lambda j: (abs(len(kd[j]) - len(ks[bone])), d[j]))
            if d[b2] > 0.15:
                raise SystemExit(f"costumes: bone {bone} has no match in the other model")
        if abs(ratio - 1) > 0.03:   # a smaller or bigger model: the piece scales with it round its bone
            mesh = mesh.moved(fs[bone] @ affine(scale=ratio) @ np.linalg.inv(fs[bone]))
        out.append((b2, mesh.moved(fd[b2] @ np.linalg.inv(fs[bone]))))
    return out


def top_chain(m):
    """The bones from the root to the one riding the topmost body vertex."""
    par, _, _ = skeleton(m)
    pts, bones = body_points(m)
    chain, b = [], int(bones[np.argmax(pts[:, 1])])
    while b >= 0:
        chain.append(b)
        b = par[b]
    return chain[::-1]


def match_bone(src, dst, bone, bmap):
    """bone of model src in model dst (the same golfer's other model): the bone map; else, if it is on the path to
    the top of the head, the bone as far down that path in dst; else by place (from the root, in skeleton
    heights; select screen skeletons can be laid out and posed differently)."""
    if bone in bmap:
        return bmap[bone]
    cs, cd = top_chain(src), top_chain(dst)
    _, _, k_s = skeleton(src)
    _, _, k_d = skeleton(dst)
    if bone in cs and len(k_s[bone]) == max(len(k_s[b]) for b in cs):     # the head (its face's bones)
        return max(cd, key=lambda b: len(k_d[b]))
    if bone in cs and len(cd) >= len(cs) - cs.index(bone):
        return cd[len(cd) - (len(cs) - cs.index(bone))]
    fs, fd = bone_frames(src), bone_frames(dst)
    P = lambda fr: (lambda a: (a - a[0]) / (a[:, 1].max() - a[:, 1].min()))(np.array([f[:3, 3] for f in fr]))
    ns, nd = P(fs), P(fd)
    _, _, ks = skeleton(src)
    _, _, kd = skeleton(dst)
    d = np.linalg.norm(nd - ns[bone], axis=1)
    near = [j for j in range(len(fd)) if d[j] < d.min() + 0.04]
    return min(near, key=lambda j: (abs(len(kd[j]) - len(ks[bone])), d[j]))


def shape_of(hp):
    """(top, centre x, centre z of the top part, radius) of a head's vertices (as head_shape). A narrow crown on
    top (Peach's, Daisy's: under 0.55 of the radius across for more than a quarter of it) doesn't count as the
    top: the hair under it does (the hat then covers the crown)."""
    top = hp[:, 1].max()
    radius = float(np.percentile(np.hypot(hp[:, 0] - hp[:, 0].mean(), hp[:, 2] - hp[:, 2].mean()), 85))
    cap = hp[hp[:, 1] > top - 0.6 * radius]
    cx, cz = float(cap[:, 0].mean()), float(cap[:, 2].mean())
    depth = 0.0
    while depth < radius:
        band = hp[(hp[:, 1] <= top - depth) & (hp[:, 1] > top - depth - 0.05 * radius)]
        if len(band) and np.hypot(band[:, 0] - cx, band[:, 2] - cz).max() > 0.55 * radius:
            break
        depth += 0.05 * radius
    if depth > 0.25 * radius:
        top -= depth
    return float(top), cx, cz, radius


def head_match(src, dst, head, top=None):
    """The head of model src found in model dst (the same golfer's other model) through its vertices: each of the
    head's vertices (moved by the bodies' median offset: select screen models can sit elsewhere) to dst's nearest;
    the bone most of the top part's ride (where a hat or horns go: a select screen pose can carry the head's top on
    another bone than its middle), and the head's shape there."""
    ps, bs = body_points(src)
    pd, bd = body_points(dst)
    _, _, ks = skeleton(src)
    off = np.median(pd, 0) - np.median(ps, 0)
    lo, hi = ps.min(0) + off - 2, ps.max(0) + off + 2
    keep = np.all((pd >= lo) & (pd <= hi), 1)          # garbage past the arrays' ends stays out
    pd, bd = pd[keep], bd[keep]
    q = ps[np.isin(bs, subtree(ks, head))]
    if top:
        q = q[q[:, 1] > q[:, 1].max() - top * (q[:, 1].max() - q[:, 1].min())]
    q = q + off
    idx = np.array([np.argmin(((pd - p) ** 2).sum(1)) for p in q])
    shape = shape_of(pd[np.unique(idx)])
    cap = idx[q[:, 1] > q[:, 1].max() - 0.6 * shape[3]]
    bones, counts = np.unique(bd[cap if len(cap) else idx], return_counts=True)
    return int(bones[counts.argmax()]), shape


def fit_range(pieces, raw):
    """Pieces that would pass the model's position format's range (fixed point: a select screen model can have
    more fraction bits) shrink towards their lowest point until they fit."""
    m = mdl.Model(raw)
    comp, frac = mdl.fmt(m.u32(m.root + 4), m.blob[m.root + 7])
    if comp not in shyguy.FORMAT or shyguy.FORMAT[comp][2] is None:
        return pieces
    lim = (shyguy.FORMAT[comp][2] - 2) / (1 << frac)
    out = []
    for bone, mesh in pieces:
        big = np.abs(mesh.pos).max()
        if big > lim:
            base = mesh.pos[np.argmin(mesh.pos[:, 1])]
            far = np.abs(mesh.pos - base).max() + 1e-9
            s = max(0.3, 1 - (big - lim) / far - 0.02)
            mesh = mesh.moved(affine(scale=s, move=base * (1 - s)))
        out.append((bone, mesh))
    return out


def costume_pieces(g, golf_raw, second_raw, select_raw):
    """{kind: (pieces in that model's bind pose, atlas tiles)} for golfer g's models: made on its in-round model,
    carried onto the others by their matched vertices (carry_uv), or built there from its own head when they
    don't pair up."""
    m = mdl.Model(golf_raw)
    pieces, tiles = outfit_pieces(g, m)
    out = {KINDS[22]: (fit_range(pieces, golf_raw), tiles)}
    for kind, raw in ((KINDS[24], second_raw), (KINDS["select"], select_raw)):
        if raw is None:
            continue
        other = mdl.Model(raw)
        moved = carry_uv(pieces, m, other)
        if moved is None:
            bmap = shyguy.bone_map(m, other, 2.0)
            head, neck, chest_bone = OUTFITS[g]["bones"]
            par, _, _ = skeleton(other)
            h2, shape = head_match(m, other, head, OUTFITS[g].get("top"))
            if head in bmap:
                h2 = bmap[head]
            r_golf = head_shape(m, head, OUTFITS[g].get("top"))[3]
            if not 0.6 * r_golf <= shape[3] <= 1.6 * r_golf:
                shape = shape[:3] + (r_golf,)
            _SHAPES[(id(other), h2)] = shape
            n2 = bmap.get(neck, par[h2] if par[h2] >= 0 else h2)
            c2 = bmap.get(chest_bone, par[n2] if par[n2] >= 0 else n2)
            moved, _ = outfit_pieces(g, other, (h2, n2, c2), golf=m)
        out[kind] = (fit_range(moved, raw), tiles)
    return out


def costume_files(g, golf_raw, second_raw, select_raw):
    """{kind: new file} for golfer g: its in-round model (A), second model (B) and select screen model (D) with
    the costume. Raw files as the game (or the mod, for Shy Guy and Tony) has them."""
    import tony
    out = {}
    levels = tony.tex_levels((ATLAS, ATLAS))
    for kind, (pieces, tiles) in costume_pieces(g, golf_raw, second_raw, select_raw).items():
        tex = tony.texture(atlas_image(tiles), (ATLAS, ATLAS), levels)
        out[kind] = add_pieces({KINDS[22]: golf_raw, KINDS[24]: second_raw, KINDS["select"]: select_raw}[kind],
                               pieces, tex, (ATLAS, ATLAS), levels)
    return out


STEPS_FILE = "costume_recolours.json"     # next to the build: the recolour steps of every costume file (make_patch.py)
TABLES_FILE = "costume_tables.bin"        # and the colour tables (64K x u16 each; the .json lists their golfers)
LINK_BASES = {16: 15, 17: 1}      # Shy Guy is built from Koopa Troopa's files, Tony from Waluigi's (shyguy, tony)


def kinds_of(golf):
    """{golfer: costume file kinds}: the in-round model, the select screen model, and the second model and the
    texture bank where the golfer has them (Peach and Yoshi have neither)."""
    meth = golf_methods(golf)
    return {g: {KINDS[22], KINDS["select"]} | {KINDS[k] for k in (23, 24) if k in meth[g]} for g in range(18)}


def originals(golf, menu):
    """{golfer: {kind: disc path of the file the costume starts from}}."""
    meth, sel = golf_methods(golf), select_ids(menu)
    out = {}
    for g in range(18):
        out[g] = {KINDS[k]: path_of(meth[g][k][1]) for k in METHODS if k in meth[g]}
        out[g][KINDS["select"]] = path_of(sel[CHAR_OF_GOLFER[g]])
    return out


def costume_path(g, kind):
    return path_of(costume_id(g, kind))


def costume_set(g, raw):
    """Golfer g's costume files and their recolour steps. raw: {kind: the file the costume starts from} (0 the
    in-round model, 1 the second, 2 the texture bank, 3 the select screen model). Returns ({kind: new file},
    {kind: [(from, to, length)]}: ranges of the decoded new file that are its start file's bytes through the
    golfer's colour table, looks.LOOKS[g]). Every body texture but eyes goes through the table (the bank's from the
    in-round model's mesh list, the models' own from theirs; [(from, to, length, texture format, 1 for the eyes'
    table)]); a pattern
    paints blocks of its colours on the
    textures the table changed most; Daisy's bikini and Birdo's chest come after."""
    import looks
    look = looks.LOOKS[g]
    lut = looks.make_lut(look["rules"]) if look["rules"] else None
    lut5 = looks.make_lut5a3(look["rules"]) if look["rules"] else None
    eyes = look.get("eye_rules")           # eyes have their own rules (Dry Bones' hollow sockets), else stay
    eye_lut = looks.make_lut(eyes) if eyes else None
    eye_lut5 = looks.make_lut5a3(eyes) if eyes else None
    pattern = looks.PATTERNS.get(look.get("pattern"))
    golf = mdl.Model(raw[KINDS[22]])
    out, ops = {}, {k: [] for k in raw}

    painted = {}                           # original picture bytes -> painted block offsets and bytes
    heights = {}

    def on_head(m, meshes):
        """The meshes sit in the top third of the body (eyes do; a shell's white rim, eye-like too, doesn't)."""
        if id(m) not in heights:
            pts, _ = body_points(m)
            heights[id(m)] = (pts[:, 1].min(), pts[:, 1].max())
        lo, hi = heights[id(m)]
        ys = [mesh_surface(m, i)[0] for i in meshes]
        ys = np.concatenate([P[..., 1].ravel() for P in ys if len(P)]) if any(len(P) for P in ys) else np.array([hi])
        return (ys.min() - lo) / max(hi - lo, 1e-6) > 0.6

    def treat(m, data, idx, off, length, fmt, w, h, levels, meshes, ops_list, anatomy=None):
        if fmt not in (14, 5) or lut is None:
            return
        img = looks.image(data, off, fmt, w, h)
        if looks.eye_like(img) and on_head(m, meshes):
            if look.get("eye_paint") and fmt == 14:   # an eye of our own (Dry Bones' sockets)
                data[off:off + length] = looks.encode_levels(look["eye_paint"](img), w, h, levels)
                return
            if eye_lut is not None:
                if fmt == 5:
                    looks.recolour5a3(data, off, length, eye_lut5)
                else:
                    looks.recolour(data, off, length, eye_lut)
                ops_list.append((off, off, length, fmt, 1))
            return
        original = bytes(data[off:off + length])
        if fmt == 5:                       # RGB5A3 (Donkey Kong's select screen fur): texel by texel, no pattern
            looks.recolour5a3(data, off, length, lut5)
            ops_list.append((off, off, length, 5, 0))
            return
        looks.recolour(data, off, length, lut)
        ops_list.append((off, off, length, 14, 0))
        if pattern is None:
            return
        if original in painted:            # the same picture as one painted already: the same blocks
            for o, blk in painted[original]:
                data[off + o:off + o + 8] = blk
            return
        if anatomy is None:
            return
        after = looks.image(data, off, fmt, w, h)
        changed = np.abs(after[..., :3].astype(int) - img[..., :3].astype(int)).sum(-1) > 30
        surfaces = [mesh_surface_bones(m, i) for i in meshes]
        surfaces = [sf for sf in surfaces if len(sf[0])]
        pts, bone = looks.rasterise_bones(surfaces, w, h)
        cov = bone >= 0
        ids = np.where(cov & changed, pattern[0](anatomy, pts, bone), 0)
        before = bytes(data[off:off + length])
        looks.paint_blocks(data, off, w, h, levels, cov & changed, ids, pattern[1])
        painted[original] = [(o, bytes(data[off + o:off + o + 8])) for o in range(0, length, 8)
                             if data[off + o:off + o + 8] != before[o:o + 8]]

    anatomy = None
    if pattern is not None:
        chest, pelvis, neck = looks.PATTERN_BONES[g]
        anatomy = looks.Anatomy(golf, chest, pelvis, neck, skeleton, body_points)

    if KINDS[23] in raw:                   # the bank: the textures the in-round model draws its body with
        bank = bytearray(lz.decompress(raw[KINDS[23]])[0])
        users = looks.body_textures(golf)
        for idx, banked, off, length, fmt, w, h, levels in looks.textures_of(golf):
            if banked and idx in users:
                treat(golf, bank, idx, off, length, fmt, w, h, levels, users[idx], ops[KINDS[23]], anatomy)
        if g == 13:
            daisy_bank(golf, bank)
        out[KINDS[23]] = lz.pack(raw[KINDS[23]][0], bytes(bank))
    for kind in (KINDS[22], KINDS[24], KINDS["select"]):
        if kind not in raw:
            continue
        mod = shyguy.Module(raw[kind])
        m = mdl.Model(raw[kind])
        users = looks.body_textures(m)
        for idx, banked, off, length, fmt, w, h, levels in looks.textures_of(m):
            if not banked and idx in users:
                treat(m, mod.blob, idx, off, length, fmt, w, h, levels, users[idx], ops[kind],
                      anatomy if kind == KINDS[22] else None)
        if g == 13:
            daisy_model(m, mod.blob, golf, raw)
        mod.blob += bytes((-len(mod.blob)) % 32)
        out[kind] = mod.pack()
    if g in OUTFITS:                       # Birdo's chest
        import tony
        per = costume_pieces(g, out[KINDS[22]], out.get(KINDS[24]), out[KINDS["select"]])
        levels = tony.tex_levels((ATLAS, ATLAS))
        for kind, (pieces, tiles) in per.items():
            tex = tony.texture(atlas_image(tiles), (ATLAS, ATLAS), levels)
            out[kind] = add_pieces(out[kind], pieces, tex, (ATLAS, ATLAS), levels)
    return out, ops


def build(clean_files, golf, menu, current=None):
    """Every golfer's costume: ({disc path: new file}, {disc path: [(source disc path, from, to, length, (golfer,
    texture format))]} recolour steps, {(golfer, format): colour table as the patch carries it}). current: files
    the mod already changed (Shy Guy's and Tony's), read before the game's."""
    import os
    import looks
    current = current or {}
    files, steps, tables = {}, {}, {}
    for g, paths in originals(golf, menu).items():
        if g in LINK_BASES and paths[KINDS[22]] not in current:
            continue                # no Shy Guy / Tony in this build
        raw = {k: current.get(p) or open(os.path.join(clean_files, *p.split("/")), "rb").read() for k, p in paths.items()}
        made, ops = costume_set(g, raw)
        for kind, data in made.items():
            files[costume_path(g, kind)] = data
            if not ops.get(kind):
                continue
            src, found = paths[kind], None
            if g in LINK_BASES:     # Shy Guy's and Tony's files are the mod's own: a step reads the game file theirs
                import tony         # was built from, where its bytes are there (else they're ours: no step)
                src = {**shyguy.SOURCES, **tony.SOURCES}[paths[kind]]
                base = open(os.path.join(clean_files, *src.split("/")), "rb").read()
                base, start = lz.decompress(base)[0] if base[0] in (1, 2) else base, lz.decompress(raw[kind])[0]
                found = {a: base.find(start[a:a + n]) for a, b, n, f, e in ops[kind]}
            steps[costume_path(g, kind)] = [(src, found[a] if found else a, b, n, (g, f, e))
                                            for a, b, n, f, e in ops[kind] if not found or found[a] >= 0]
        for variant, rules in ((0, looks.LOOKS[g]["rules"]), (1, looks.LOOKS[g].get("eye_rules"))):
            if rules:
                tables[(g, 14, variant)] = looks.lut_bytes(looks.make_lut(rules))
                tables[(g, 5, variant)] = looks.lut_bytes(looks.make_lut5a3(rules))
    return files, steps, tables


def sources(golf, menu):
    """{disc path of a costume file: [game files make_patch copies its bytes from, the first giving the relocation
    table]}: the golfer's own file (for Shy Guy and Tony, the one theirs is built from)."""
    import shyguy as sg
    import tony
    built = {**{f"{k}": v for k, v in sg.SOURCES.items()}, **tony.SOURCES}
    out = {}
    for g, files in originals(golf, menu).items():
        for kind, p in files.items():
            src = built.get(p, p) if g in LINK_BASES else p
            out[f"files/{costume_path(g, kind)}"] = [f"files/{src}"] + ([f"files/{DAISY_BANK}"] if g == 13 else [])
            # (Daisy's repainted textures start from her bank's: the untouched texels come from the player's disc)
    return out


# ---------------------------------------------------------------- Daisy's bikini

# Her golf outfit is a top (in-round model C/V/E mesh 38, texture 33, from her waist up to her shoulders) and a skirt
# (mesh 30, texture 25, over her hips), both skinned on her body, with bare arms and legs. The costume repaints those
# two textures by where each texel sits on her (rasterised through the meshes' triangles in texture space): a black
# bandeau top with orange trim and straps, and a black bottom with orange trim dipping in a V at the front, skin
# (her own, texture 26) everywhere else. The new textures go inside her costume models; her bank stays as it is.
DAISY_TOP, DAISY_SKIRT, DAISY_SKIN = 33, 25, 26     # texture indexes in C/V/E
DAISY_BANK = "C/V/D"
TOP_BAND = (0.514, 0.792)       # the bandeau, as shares of the top mesh's height (9.1..12.7: 10.95..11.95)
TOP_STRAPS = (0.28, 0.48)       # straps above it, as shares of the mesh's half width
BOTTOM_EDGE = (0.44, 0.23)      # the bottom's lower edge on the skirt mesh: share of its height at the front middle,
                                # plus this much more at the sides
TRIM = 0.035                    # orange trim width, as a share of the mesh's height


def mesh_surface(m, index):
    """A mesh's triangles: positions (n, 3, 3) in bind pose and texcoords (n, 3, 2)."""
    rigid = np.array(mdl.positions(m)) if m.u32(m.root + 0xC) else np.zeros((0, 3))
    skinned = np.array(mdl.array(m, 4, 0x10, m.u32(m.root + 0xC), 3)) if m.p(m.root + 0x10) is not None \
        else np.zeros((0, 3))
    uv = np.array(mdl.texcoords(m))
    P, T = [], []
    for i, mo, g, go, mtx, dls in mdl.meshes(m):
        if i != index:
            continue
        src = rigid if m.u32(go) & 1 else skinned
        for dl, size in dls:
            try:
                tris = mdl.triangles(m, mo, m.u32(go + 4), dl, size)
            except ValueError:
                continue
            for tri in tris:
                if all(v[1] < len(src) and v[3] is not None and v[3] < len(uv) for v in tri):
                    P.append([src[v[1]] for v in tri])
                    T.append([uv[v[3]] for v in tri])
    return np.array(P), np.array(T)


def mesh_surface_bones(m, index):
    """A mesh's triangles: positions (n, 3, 3), texcoords (n, 3, 2) and each corner's bone (n, 3)."""
    rigid = np.array(mdl.positions(m)) if m.u32(m.root + 0xC) else np.zeros((0, 3))
    skinned = np.array(mdl.array(m, 4, 0x10, m.u32(m.root + 0xC), 3)) if m.p(m.root + 0x10) is not None \
        else np.zeros((0, 3))
    sb = skin_bones(m) if len(skinned) else {}
    uv = np.array(mdl.texcoords(m))
    P, T, B = [], [], []
    for i, mo, g, go, mtx, dls in mdl.meshes(m):
        if i != index:
            continue
        rig = m.u32(go) & 1
        src = rigid if rig else skinned
        for dl, size in dls:
            try:
                tris = mdl.triangles(m, mo, m.u32(go + 4), dl, size)
            except ValueError:
                continue
            for tri in tris:
                if all(v[1] < len(src) and v[3] is not None and v[3] < len(uv) for v in tri):
                    bones = [mtx[v[0]] if rig and v[0] < len(mtx) else sb.get(v[1], -1) for v in tri]
                    P.append([src[v[1]] for v in tri])
                    T.append([uv[v[3]] for v in tri])
                    B.append(bones)
    return np.array(P), np.array(T), np.array(B)


def texture_image(m, bank, index):
    """(RGBA picture, (w, h), mip levels) of a model's texture (in the model or its bank)."""
    import textures as tx
    ts = m.p(m.root + 0x8C)
    h, w, ht, fmt, at, lod = tx.headers(m.blob, ts)[index]
    src, off = (bank, at & 0x7FFFFFFF) if at & 0x80000000 else (m.blob, ts + at)
    return tx.decode(bytes(src[off:off + tx.level_size(w, ht, fmt)]), w, ht, fmt)[:ht, :w], (w, ht), lod + 1


def like_mesh(m, bank, ref):
    """The body mesh whose texture looks most like picture ref (another of the golfer's models)."""
    from PIL import Image
    small = lambda a: np.asarray(Image.fromarray(a[..., :3]).resize((16, 16), Image.BOX), float)
    r = small(ref)
    best = None
    meshes, count = m.p(m.root + 0x40), m.u32(m.root + 0x3C)
    for i in range(count):
        o = meshes + 0x3C * i
        if m.u32(o + 0x38) != BODY_PART or not m.blob[o + 7]:
            continue
        try:
            img = texture_image(m, bank, m.blob[o + 10])[0]
        except Exception:
            continue
        d = ((small(img) - r) ** 2).mean()
        if best is None or d < best[0]:
            best = (d, i)
    return best[1]


def repaint(img, P, T, colour):
    """img with every texel the triangles cover painted colour(point on the body, (x, y, z) shares of the mesh's
    size): None keeps it."""
    H, W = img.shape[:2]
    out = img.copy()
    lo, hi = P.reshape(-1, 3).min(0), P.reshape(-1, 3).max(0)
    for tri, uv in zip(P, T):
        uv = uv - np.floor(uv.min(0))
        px = uv * (W, H)
        x0, y0 = np.floor(px.min(0)).astype(int)
        x1, y1 = np.ceil(px.max(0)).astype(int)
        a, b, c = px
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                q = (x + 0.5, y + 0.5)
                l1 = ((b[1] - c[1]) * (q[0] - c[0]) + (c[0] - b[0]) * (q[1] - c[1])) / den
                l2 = ((c[1] - a[1]) * (q[0] - c[0]) + (a[0] - c[0]) * (q[1] - c[1])) / den
                l3 = 1 - l1 - l2
                if min(l1, l2, l3) < -0.02:
                    continue
                pt = l1 * tri[0] + l2 * tri[1] + l3 * tri[2]
                f = (abs(pt[0]) / max(abs(lo[0]), abs(hi[0])), (pt[1] - lo[1]) / (hi[1] - lo[1]), pt[2])
                col = colour(f)
                if col is not None:
                    out[y % H, x % W, :3] = col
    return out


def daisy_top(skin):
    black, orange = COLOURS["black"], COLOURS["orange"]

    def colour(f):
        ax, fy, z = f
        a, b = TOP_BAND
        if a <= fy <= b:
            return orange if fy - a < TRIM or b - fy < TRIM else black
        if fy > b and TOP_STRAPS[0] <= ax <= TOP_STRAPS[1]:
            return black
        return skin
    return colour


def daisy_bottom(skin):
    black, orange = COLOURS["black"], COLOURS["orange"]

    def colour(f):
        ax, fy, z = f
        edge = BOTTOM_EDGE[0] + BOTTOM_EDGE[1] * min(1.0, ax / 0.8) if z > 0 else BOTTOM_EDGE[0] + BOTTOM_EDGE[1]
        if fy >= edge:
            return orange if fy - edge < TRIM or fy > 1 - TRIM else black
        return skin
    return colour


def daisy_bank(golf, bank):
    """Daisy's bikini in her costume bank: her top and skirt textures repainted with colours of our own."""
    import looks
    skin = tuple(int(v) for v in texture_image(golf, bank, DAISY_SKIN)[0][..., :3].reshape(-1, 3).mean(0))
    heads = {t[0]: t for t in looks.textures_of(golf)}
    for idx, paint in ((DAISY_TOP, daisy_top(skin)), (DAISY_SKIRT, daisy_bottom(skin))):
        _, banked, off, length, fmt, w, h, levels = heads[idx]
        meshes = looks.body_textures(golf)[idx]
        surf = [mesh_surface(golf, i) for i in meshes]
        P = np.vstack([a for a, _ in surf])
        pts, cov = looks.rasterise(surf, w, h, P.reshape(-1, 3).min(0), P.reshape(-1, 3).max(0))
        looks.paint_ours(bank, off, w, h, levels, pts, cov, lambda f: paint((abs(f[0]), f[1], f[2])))


def daisy_model(m, blob, golf, raw):
    """Daisy's bikini on a model's own copies of her top and skirt textures (her select screen model's)."""
    import looks
    bank = lz.decompress(raw[KINDS[23]])[0]
    skin = tuple(int(v) for v in texture_image(golf, bank, DAISY_SKIN)[0][..., :3].reshape(-1, 3).mean(0))
    heads = {t[0]: t for t in looks.textures_of(m)}
    for ref_idx, paint in ((DAISY_TOP, daisy_top(skin)), (DAISY_SKIRT, daisy_bottom(skin))):
        ref = texture_image(golf, bank, ref_idx)[0]
        i = like_mesh(m, bank, ref)
        idx = m.blob[m.p(m.root + 0x40) + 0x3C * i + 10]
        _, banked, off, length, fmt, w, h, levels = heads[idx]
        if banked or fmt != 14:
            continue
        surf = [mesh_surface(m, i)]
        P = surf[0][0]
        pts, cov = looks.rasterise(surf, w, h, P.reshape(-1, 3).min(0), P.reshape(-1, 3).max(0))
        looks.paint_ours(blob, off, w, h, levels, pts, cov, lambda f: paint((abs(f[0]), f[1], f[2])))


def overlay_patches(rel, labels, word):
    """[(address, new word, expected word)] for the golf (C/L/V) or menu (B/U/C) overlay."""
    out = []
    if rel == "C/L/V":
        out.append((NEW_HOOK, ppc.bl(NEW_HOOK, labels["new"]), ppc.bl(NEW_HOOK, NEW_TARGET)))
        for g, methods in labels["_methods"].items():
            for k, (at, fid) in methods.items():
                if KINDS[k] not in labels["_have"].get(g, ()):
                    continue
                out += [(at, ppc.mr(4, 3), 0x3C600000), (at + 4, ppc.li(3, fid), 0x38630000 | fid),
                        (at + 8, ppc.b(at + 8, labels["map"]), ppc.BLR)]
    elif rel == "B/U/C":
        out += [(Y_HOOK, ppc.b(Y_HOOK, labels["y"]), Y_WORD),
                (PICK_HOOK, ppc.bl(PICK_HOOK, labels["pick"]), ppc.bl(PICK_HOOK, PICK_TARGET)),
                (SLOT_HOOK, ppc.bl(SLOT_HOOK, labels["slot"]), SLOT_WORD)]
    return out
