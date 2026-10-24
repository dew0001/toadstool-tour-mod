"""Replace one exact string in a file with a same-length or shorter string (padded with NULs).

Python escapes work in both strings, e.g. "\\x13" for the stick icon, "\\x01" for a line break.
Usage: python -I patch_text.py <file> <old> <new>
"""
import sys


def unescape(s):
    return s.encode("latin-1").decode("unicode_escape").encode("latin-1")


def main():
    path, old, new = sys.argv[1], unescape(sys.argv[2]), unescape(sys.argv[3])
    if len(new) > len(old):
        raise SystemExit(f"new text is {len(new)} bytes; it must fit in {len(old)}")
    with open(path, "rb") as f:
        data = f.read()
    count = data.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one match, found {count}")
    at = data.find(old)
    data = data[:at] + new + b"\x00" * (len(old) - len(new)) + data[at + len(old):]
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    import os
    os.replace(tmp, path)
    print(f"patched 0x{at:X}: {old!r} -> {new!r}")


if __name__ == "__main__":
    main()
