"""The golf overlay's tail (v27): room for code and data that only runs in a round, appended to the overlay's image.

C/L/V is a flat image the game loads at 0x80400000 for every round (main.dol `FUN_8000bc14(0xCF7, 0x80400000,
0x150000)`: at most 0x150000 bytes, so up to 0x80550000, where main.dol puts the arena's start, `FUN_80032da0(
0x80550000)`; the movie player reuses 0x80400000..0x80550000 as heap 8 only while no overlay is loaded). The image ends
at 0x804E3604 and the overlay's zero-filled data after it at about 0x80524720 (the highest address its code names is
0x80524668; in a Football round the RAM from 0x8052471C to 0x80550000 stayed zero). So BASE..LIMIT is free while a
round runs: `extend` pads the image with zeros up to BASE (the overlay's data area, zero anyway) and appends the blob.
The image is then 0x128000 + the blob, and LIMIT keeps 32 KB under the load's 0x150000.
Code here can be called only from the golf overlay's own hooks (or main.dol code that runs only in a round).
"""
OVERLAY_BASE = 0x80400000
BASE = 0x80528000
LIMIT = 0x80548000


def extend(buf, blob):
    """Pad the decoded C/L/V (a bytearray) to BASE and append blob."""
    end = OVERLAY_BASE + len(buf)
    if end > BASE:
        raise SystemExit(f"C/L/V: the image already reaches 0x{end:08X}, past the tail's start 0x{BASE:08X}")
    if BASE + len(blob) > LIMIT:
        raise SystemExit(f"golf tail: {len(blob)} bytes; only {LIMIT - BASE} fit")
    buf.extend(bytes(BASE - end))
    buf.extend(blob)
