"""Convert a GameCube .dol executable into a big-endian PowerPC ELF32.

REA (and Ghidra's stock loaders) don't read .dol, but they do read ELF.
Each non-empty DOL text/data section becomes a PT_LOAD segment plus a named
section header; the BSS range becomes a NOBITS section.

Usage: python -I dol2elf.py main.dol main.elf [blob@0xADDR ...]
Extra blobs (e.g. a decoded overlay: unpacked/C/L/V.bin@0x80400000) become .ovlN sections.
"""
import struct
import sys

EM_PPC = 20
PT_LOAD = 1
SHT_PROGBITS, SHT_STRTAB, SHT_NOBITS = 1, 3, 8
SHF_WRITE, SHF_ALLOC, SHF_EXECINSTR = 0x1, 0x2, 0x4
PF_X, PF_W, PF_R = 1, 2, 4


def read_dol(data):
    u32 = lambda off, n: struct.unpack_from(f">{n}I", data, off)
    offs = u32(0x00, 18)
    addrs = u32(0x48, 18)
    sizes = u32(0x90, 18)
    bss_addr, bss_size, entry = u32(0xD8, 3)
    sections = []
    for i in range(18):
        if sizes[i] == 0:
            continue
        is_text = i < 7
        name = f".text{i}" if is_text else f".data{i - 7}"
        sections.append((name, is_text, addrs[i], data[offs[i]:offs[i] + sizes[i]]))
    sections.sort(key=lambda s: s[2])
    return sections, bss_addr, bss_size, entry


def build_elf(sections, bss_addr, bss_size, entry):
    ehdr_size, phdr_size, shdr_size = 52, 32, 40
    phoff = ehdr_size
    body_off = phoff + phdr_size * len(sections)

    # Section bodies, 32-byte aligned in the file.
    blobs, offsets, cur = [], [], body_off
    for _, _, _, body in sections:
        pad = (-cur) % 32
        blobs.append(b"\0" * pad + body)
        cur += pad
        offsets.append(cur)
        cur += len(body)

    names = [s[0] for s in sections] + [".bss", ".shstrtab"]
    shstrtab, name_off = b"\0", {}
    for n in names:
        name_off[n] = len(shstrtab)
        shstrtab += n.encode() + b"\0"
    shstr_off = cur
    cur += len(shstrtab)
    shoff = cur + ((-cur) % 4)

    phdrs = b""
    for (name, is_text, addr, body), off in zip(sections, offsets):
        flags = PF_R | (PF_X if is_text else PF_W)
        phdrs += struct.pack(">8I", PT_LOAD, off, addr, addr, len(body), len(body), flags, 32)

    shdrs = b"\0" * shdr_size  # SHN_UNDEF
    for (name, is_text, addr, body), off in zip(sections, offsets):
        flags = SHF_ALLOC | (SHF_EXECINSTR if is_text else SHF_WRITE)
        shdrs += struct.pack(">10I", name_off[name], SHT_PROGBITS, flags, addr, off, len(body), 0, 0, 32, 0)
    shdrs += struct.pack(">10I", name_off[".bss"], SHT_NOBITS, SHF_ALLOC | SHF_WRITE, bss_addr, shstr_off, bss_size, 0, 0, 32, 0)
    shdrs += struct.pack(">10I", name_off[".shstrtab"], SHT_STRTAB, 0, 0, shstr_off, len(shstrtab), 0, 0, 1, 0)
    shnum = len(sections) + 3

    ident = b"\x7fELF" + bytes([1, 2, 1, 0]) + b"\0" * 8  # ELFCLASS32, ELFDATA2MSB
    ehdr = ident + struct.pack(">HHIIIIIHHHHHH", 2, EM_PPC, 1, entry, phoff, shoff, 0,
                               ehdr_size, phdr_size, len(sections), shdr_size, shnum, shnum - 1)
    out = ehdr + phdrs + b"".join(blobs) + shstrtab
    out += b"\0" * (shoff - len(out))
    return out + shdrs


def main():
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, "rb") as f:
        sections, bss_addr, bss_size, entry = read_dol(f.read())
    for n, spec in enumerate(sys.argv[3:]):
        path, addr = spec.rsplit("@", 1)
        with open(path, "rb") as f:
            sections.append((f".ovl{n}", True, int(addr, 16), f.read()))
    sections.sort(key=lambda s: s[2])
    with open(dst, "wb") as f:
        f.write(build_elf(sections, bss_addr, bss_size, entry))
    for name, _, addr, body in sections:
        print(f"{name:8} 0x{addr:08X}-0x{addr + len(body):08X} ({len(body):,} bytes)")
    print(f".bss     0x{bss_addr:08X}-0x{bss_addr + bss_size:08X} ({bss_size:,} bytes)")
    print(f"entry    0x{entry:08X}")


if __name__ == "__main__":
    main()
