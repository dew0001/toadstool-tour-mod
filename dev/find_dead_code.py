"""Cross-check 'unreferenced' main.dol functions against everything Ghidra didn't analyze.

A candidate survives only if nothing anywhere points at it:
  - no big-endian word equal to its address in main.dol or any decoded file (pointer tables)
  - no b/bl to it from the fixed-address overlays (C/L/V, B/U/C at 0x80400000)
  - no relocation (any kind, any module) whose value is its address
  - no lis/addi (or lis/ori) pair building its address in main.dol or the overlays

Usage: python -I find_dead_code.py <unreferenced.tsv> <main.dol> <unpacked dir>
"""
import os
import struct
import sys

OVERLAYS = {"C/L/V": 0x80400000, "B/U/C": 0x80400000}


def words(blob):
    return struct.unpack_from(f">{len(blob) // 4}I", blob, 0)


def branch_targets(blob, base):
    out = set()
    for i, w in enumerate(words(blob)):
        if w & 0xFC000000 == 0x48000000 and not w & 2:  # b / bl, relative
            off = w & 0x03FFFFFC
            if off & 0x02000000:
                off -= 0x04000000
            out.add(base + 4 * i + off)
    return out


def built_addresses(blob):
    """Addresses formed by lis rX,hi followed within 6 instructions by addi/ori rY,rX,lo."""
    out = set()
    ws = words(blob)
    for i, w in enumerate(ws):
        if w & 0xFC1F0000 != 0x3C000000:  # lis rD, imm (addis rD, 0, imm)
            continue
        rd, hi = (w >> 21) & 31, w & 0xFFFF
        for w2 in ws[i + 1:i + 7]:
            op = w2 >> 26
            if op in (14, 24) and (w2 >> 16) & 31 == rd:  # addi / ori
                lo = w2 & 0xFFFF
                if op == 14 and lo & 0x8000:
                    out.add(((hi << 16) - 0x10000 + lo) & 0xFFFFFFFF)
                else:
                    out.add(((hi << 16) + lo) & 0xFFFFFFFF)
    return out


def main():
    tsv, dol_path, unpacked = sys.argv[1:4]
    cands = []
    for line in open(tsv):
        addr, size, name = line.split("\t")
        cands.append((int(addr, 16), int(size), name.strip()))
    dol = open(dol_path, "rb").read()
    text_off, text_addr, text_size = struct.unpack_from(">I", dol, 0)[0], struct.unpack_from(">I", dol, 0x48)[0], \
        struct.unpack_from(">I", dol, 0x90)[0]
    text = dol[text_off:text_off + text_size]

    word_hits = {}
    blobs = [("main.dol", dol)]
    for dirpath, _, names in os.walk(unpacked):
        for n in names:
            if n.endswith(".bin"):
                p = os.path.join(dirpath, n)
                blobs.append((os.path.relpath(p, unpacked), open(p, "rb").read()))
    cand_set = {a for a, _, _ in cands}
    for label, blob in blobs:
        for a in cand_set:
            if struct.pack(">I", a) in blob:
                word_hits.setdefault(a, []).append(label)

    reloc_hits = {}
    for dirpath, _, names in os.walk(unpacked):
        for n in names:
            if n.endswith(".rel"):
                data = open(os.path.join(dirpath, n), "rb").read()
                for i in range(0, len(data), 8):
                    val = struct.unpack_from(">I", data, i + 4)[0]
                    if val in cand_set:
                        reloc_hits.setdefault(val, []).append(n)

    branches = branch_targets(text, text_addr)
    built = built_addresses(text)
    for rel, base in OVERLAYS.items():
        blob = open(os.path.join(unpacked, *rel.split("/")) + ".bin", "rb").read()
        branches |= branch_targets(blob, base)
        built |= built_addresses(blob)

    print("address     size  verdict")
    for a, size, name in cands:
        why = []
        if a in word_hits:
            why.append("word in " + ",".join(word_hits[a][:3]))
        if a in reloc_hits:
            why.append("reloc in " + ",".join(sorted(set(reloc_hits[a]))[:3]))
        if a in branches:
            why.append("branched to")
        if a in built:
            why.append("address built with lis/addi")
        print(f"0x{a:08X} {size:5}  {'DEAD' if not why else '; '.join(why)}")


if __name__ == "__main__":
    main()
