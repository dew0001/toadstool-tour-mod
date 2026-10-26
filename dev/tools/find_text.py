"""Find files (decoded and raw) containing given ASCII or UTF-16BE strings."""
import os
import sys
ROOT = os.environ.get("TTMOD_ROOT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))

roots = [os.path.join(ROOT, "unpacked"), os.path.join(ROOT, "disc", "files"), os.path.join(ROOT, "disc", "sys")]
needles = []
for w in sys.argv[1:]:
    needles.append((w, w.encode("latin-1")))
    needles.append((w + " (utf16)", w.encode("utf-16-be")))
for root in roots:
    for dirpath, _, names in os.walk(root):
        for n in names:
            p = os.path.join(dirpath, n)
            if n.endswith(".rel") or os.path.getsize(p) > 64 * 1024 * 1024:
                continue
            d = open(p, "rb").read()
            for label, nb in needles:
                i = d.find(nb)
                if i >= 0:
                    print(f"{os.path.relpath(p, os.path.dirname(root))}: {label} at 0x{i:X} (size {len(d):,})")
