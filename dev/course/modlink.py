"""Build Camelot type-2 modules out of pieces of existing ones (a small linker), for new hole models.

A source module is cut into regions at every internal pointer target (ADDR32 relocation values); importing a
region copies its bytes and, recursively, every region its pointers reach, rewriting the relocations. Texture
sets (magic 0x0020AF30) keep their texture data (offsets relative to the set) by extending their region to the
end of the last texture's data.

The output module: the hole model header (three exported stubs: +8 terrain root, +C object count, +10 object
table), then data, then the two empty constructor/destructor lists, like every retail hole model.
"""
import bisect
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import camelot_lz as lz  # noqa: E402
import textures as tx  # noqa: E402

ROOT = os.environ.get("TTMOD_ROOT", os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))
DISC = os.path.join(ROOT, 'disc', 'files')
TEXSET_MAGIC = 0x0020AF30


class Source:
    def __init__(self, rel):
        self.rel = rel
        raw = open(os.path.join(DISC, *rel.split('/')), 'rb').read()
        blob, end = lz.decompress(raw)
        self.blob = blob
        self.relocs, _ = lz.relocations(raw, end)    # (kind, external, offset, value)
        self.ptr = {o: v for k, e, o, v in self.relocs if k == 0 and not e}
        self.ext = {o: v for k, e, o, v in self.relocs if k == 0 and e}
        self.targets = sorted(set(self.ptr.values()))
        self._ends = {}

    def u32(self, o):
        return struct.unpack_from('>I', self.blob, o)[0]

    def stub(self, off):
        """Module offset a header stub (b -> lis/addi or li) returns."""
        tgt = next(v for k, e, o, v in self.relocs if o == off and k == 1)
        w = self.u32(tgt)
        if w >> 26 == 14 and (w >> 16) & 31 == 0:
            return w & 0xFFFF
        return next(v for k, e, o, v in self.relocs if o == tgt and k == 2)

    def region(self, off):
        if off in self._ends:
            return self._ends[off]
        i = bisect.bisect_right(self.targets, off)
        end = self.targets[i] if i < len(self.targets) else len(self.blob)
        if off + 12 <= len(self.blob) and self.u32(off) == TEXSET_MAGIC and self.u32(off + 8) == 0xC:
            data_end = off
            for ho, w, h, f, d, lod in tx.headers(self.blob, off):
                size, lw, lh = 0, w, h
                for _ in range(lod + 1):
                    size += max(tx.level_size(lw, lh, f), 32)
                    lw, lh = max(lw // 2, 1), max(lh // 2, 1)
                data_end = max(data_end, off + d + size)
            end = max(end, (data_end + 31) & ~31)
        self._ends[off] = end
        return end


class Linker:
    HEADER = 0x40

    def __init__(self):
        self.blob = bytearray(self.HEADER)
        self.relocs = []          # (kind byte incl. 0x04 external, offset, value)
        self.memo = {}
        self.prov = []            # (source disc path, source offset, offset here, length): bytes copied from the game

    def alloc(self, data, align=32):
        self.blob += bytes((-len(self.blob)) % align)
        at = len(self.blob)
        self.blob += data
        return at

    def ptr(self, at, target):
        """An internal pointer at `at` to module offset `target`."""
        struct.pack_into('>I', self.blob, at, 0)
        self.relocs.append((0, at, target))

    def import_(self, src, off, align=32):
        """Copy the region at `off` of `src` and everything it points to; returns the new offset."""
        key = (src.rel, off)
        if key in self.memo:
            return self.memo[key]
        work = [off]
        order = []
        while work:
            o = work.pop()
            if (src.rel, o) in self.memo:
                continue
            end = src.region(o)
            new = self.alloc(src.blob[o:end], 4 if end - o < 32 else align)
            self.memo[(src.rel, o)] = new
            if end > o:
                self.prov.append((src.rel, o, new, end - o))
            order.append((o, end, new))
            for p in range(o, end, 4):
                if p in src.ptr and (src.rel, src.ptr[p]) not in self.memo:
                    work.append(src.ptr[p])
        for o, end, new in order:
            for p in range(o, end, 4):
                if p in src.ptr:
                    t = src.ptr[p]
                    region_start = t      # every target starts a region
                    self.ptr(new + p - o, self.memo[(src.rel, region_start)])
                elif p in src.ext:
                    struct.pack_into('>I', self.blob, new + p - o, 0)
                    self.relocs.append((0x04, new + p - o, src.ext[p]))
        return self.memo[key]

    def ptr_end(self, at):
        """A pointer at `at` to the module's end (retail models' terrain root +0xA4)."""
        self.end_ptrs = getattr(self, "end_ptrs", []) + [at]

    def finish(self, root, count, objects):
        """Header stubs and the closing lists; returns the packed type-2 file."""
        b = self.blob
        struct.pack_into('>8I', b, 0x08, 0x48000000, 0x48000000, 0x48000000, 0x3C600000, 0x38630000,
                         0x4E800020, 0x38600000 | count, 0x4E800020)
        struct.pack_into('>3I', b, 0x28, 0x3C600000, 0x38630000, 0x4E800020)
        lists = self.alloc(bytes(8), 8)
        for at in getattr(self, "end_ptrs", []):
            self.ptr(at, lists + 8)
        fixed = [(0, 0x00, lists), (0, 0x04, lists + 4), (1, 0x08, 0x14), (1, 0x0C, 0x20), (1, 0x10, 0x28),
                 (2, 0x14, root), (3, 0x18, root), (2, 0x28, objects), (3, 0x2C, objects)]
        rel = sorted(fixed + self.relocs, key=lambda r: r[1])
        table = b"".join(struct.pack('>II', k << 24 | o, v) for k, o, v in rel)
        self.blob += bytes((-len(self.blob)) % 8)
        return lz.pack(2, bytes(self.blob), table)
