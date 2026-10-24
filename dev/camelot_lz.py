"""Camelot LZSS container used by Mario Golf: Toadstool Tour (GFTE01).

Reimplemented from main.dol:
  FUN_8000b134  load entry: header byte = type, low 24 bits = unpacked size
  FUN_8000a16c  LZSS decoder (below)
  FUN_80009fc8  relocation pass applied to type 2 files after decoding

Stream layout after the 4-byte header:
  flag byte, MSB first: 0 = literal byte, 1 = back-reference
  back-reference: [dddd llll][dddddddd]      length = llll + 1        (2..16)
                  [dddd 0000][dddddddd][n]   length = n + 0x11        (17..272)
                  distance (12 bits) counts back from the output end; distance 0 = end of stream
Type 2 files then carry a relocation table at the next 8-byte boundary:
  8-byte entries (kind << 24 | offset, value), terminated by kind 0xFF.
"""
import struct

RELOC_KINDS = {0: "ADDR32", 1: "REL24", 2: "HA16", 3: "LO16", 8: "SDA21", 9: "REL32"}


def header(data):
    """Return (type byte, unpacked size) from the 4-byte file header."""
    return data[0], int.from_bytes(data[1:4], "big")


def decompress(data, start=4):
    """Decode one LZSS stream. Returns (output bytes, offset just past the end marker)."""
    out = bytearray()
    src = start
    while True:
        flags = data[src]
        src += 1
        if flags == 0:
            out += data[src:src + 8]
            src += 8
            continue
        for bit in range(7, -1, -1):
            if not (flags >> bit) & 1:
                out.append(data[src])
                src += 1
                continue
            b1, b2 = data[src], data[src + 1]
            dist = ((b1 & 0xF0) << 4) | b2
            if dist == 0:
                return bytes(out), src + 2
            if b1 & 0x0F:
                length = (b1 & 0x0F) + 1
                src += 2
            else:
                length = data[src + 2] + 0x11
                src += 3
            pos = len(out) - dist
            if pos < 0:
                raise ValueError(f"back-reference before start of output at src 0x{src:X}")
            if dist >= length:
                out += out[pos:pos + length]
            else:
                for i in range(length):
                    out.append(out[pos + i])


MAX_DIST = 0xFFF
MAX_LEN = 0xFF + 0x11
MIN_LEN = 3


def compress(data, max_chain=48):
    """Encode `data` as an LZSS stream (no header) that decompress() reads back exactly.

    Greedy matching over 3-byte hash chains; the window and lengths match the game's decoder.
    """
    n = len(data)
    out = bytearray()
    head = {}
    prev = [-1] * n
    flags = 0
    count = 0
    group = bytearray()

    def finish_item(is_match):
        nonlocal flags, count, group
        if is_match:
            flags |= 0x80 >> count
        count += 1
        if count == 8:
            out.append(flags)
            out.extend(group)
            flags, count, group = 0, 0, bytearray()

    def insert(pos):
        if pos + 2 < n:
            key = (data[pos] << 16) | (data[pos + 1] << 8) | data[pos + 2]
            prev[pos] = head.get(key, -1)
            head[key] = pos

    i = 0
    while i < n:
        best_len, best_dist = 0, 0
        if i + 2 < n:
            key = (data[i] << 16) | (data[i + 1] << 8) | data[i + 2]
            cand = head.get(key, -1)
            limit = min(MAX_LEN, n - i)
            depth = 0
            while cand >= 0 and i - cand <= MAX_DIST and depth < max_chain:
                if data[cand + best_len] == data[i + best_len] if best_len < limit else False:
                    length = 0
                    while length < limit and data[cand + length] == data[i + length]:
                        length += 1
                    if length > best_len:
                        best_len, best_dist = length, i - cand
                        if length == limit:
                            break
                cand = prev[cand]
                depth += 1
        if best_len >= MIN_LEN:
            if best_len <= 0x10:
                group += bytes([((best_dist >> 8) << 4) | (best_len - 1), best_dist & 0xFF])
            else:
                group += bytes([(best_dist >> 8) << 4, best_dist & 0xFF, best_len - 0x11])
            finish_item(True)
            for p in range(i, i + best_len):
                insert(p)
            i += best_len
        else:
            group.append(data[i])
            finish_item(False)
            insert(i)
            i += 1
    group += b"\x00\x00"  # distance 0 = end of stream
    flags |= 0x80 >> count
    out.append(flags)
    out.extend(group)
    return bytes(out)


def pack(kind, data, reloc_table=b""):
    """Build a complete type 1 or 2 file: header, LZSS stream, and (type 2) relocation table.

    `reloc_table` is the raw 8-byte entries without the terminator, as unpack_all.py writes them.
    """
    if kind not in (1, 2):
        raise ValueError("only types 1 and 2 are LZSS containers")
    if len(data) > 0xFFFFFF:
        raise ValueError("unpacked size does not fit the 24-bit header")
    body = bytearray([kind]) + len(data).to_bytes(3, "big") + compress(data)
    if kind == 2:
        body += b"\x00" * ((-len(body)) % 8)
        body += reloc_table + b"\xFF" * 8
    return bytes(body)


def relocations(data, stream_end):
    """Parse the type 2 relocation table that follows the LZSS stream.

    Returns (list of (kind, external, offset, value), table end offset).
    `external` mirrors the 0x04 kind bit: the value is an absolute address, not module-relative.
    """
    off = (stream_end + 7) & ~7
    entries = []
    while off + 8 <= len(data):
        word, value = struct.unpack_from(">II", data, off)
        off += 8
        kind = word >> 24
        if kind == 0xFF:
            return entries, off
        entries.append((kind & ~0x04, bool(kind & 0x04), word & 0xFFFFFC, value))
    raise ValueError("relocation table has no 0xFF terminator")


def apply_relocations(module, entries, base):
    """Return a copy of `module` relocated to load address `base`, as FUN_80009fc8 does."""
    buf = bytearray(module)
    for kind, external, offset, value in entries:
        addr = base + offset
        local = not external and value < 0x80000000
        target = value + base if local else value
        word = struct.unpack_from(">I", buf, offset)[0]
        if kind == 0:
            word = target
        elif kind == 1:
            word = (word & ~0x3FFFFFC) | ((target - addr) & 0x3FFFFFC)
        elif kind == 2:
            word = (word & 0xFFFF0000) | (((target + 0x8000) >> 16) & 0xFFFF)
        elif kind == 3:
            word = (word & 0xFFFF0000) | (target & 0xFFFF)
        elif kind == 8:
            # Small-data access: rewrite rA to r13 or r2 and the displacement from that base.
            if 0x802D7A60 <= target < 0x802E7A60:
                word = (word & 0xFFF00000) | 0xD0000 | ((target - 0x802DFA60) & 0xFFFF)
            elif 0x802D7480 <= target < 0x802E7480:
                word = (word & 0xFFF00000) | 0x20000 | ((target - 0x802DF480) & 0xFFFF)
            elif target + 0x8000 < 0x10000:
                word = (word & 0xFFF00000) | (target & 0xFFFF)
        elif kind == 9:
            word = (target - addr) & 0xFFFFFFFF
        struct.pack_into(">I", buf, offset, word)
    return bytes(buf)
