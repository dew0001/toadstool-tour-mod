"""v27 Football's HUD badge: the bottom left's club picture and name show the shot type in Football.

The golf HUD's FUN_8042f98c loads the badge's two pictures by file ID: the club, 0xA45 + 2 x club + 0x1C x club set
(B/Y/O.., 78x117 CMPR), and its name, 0xA29 + 2 x club (B/Y/A.., 96x54 CMPR: 1W 3W 4W 3I .. 9I PW AW SW PT). In
Football the hooks below (fbpose.py's tail) take them from our own files under a new disc folder, J: J/B/<club> a
football (thrown, or standing on a kicking tee for the field goal) and J/A/<club> the shot type's name, for every
club (a club that isn't a shot type, which fbpose.py's fp_snap changes the frame it shows, gets the nearest pass's).
All drawn here (no game pixels): Arial Rounded MT Bold letters with the game's look (a light gradient, a dark
outline) and a football like fbpose.py's.
"""
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import camelot_lz  # noqa: E402
import football as fb  # noqa: E402
import shyguy  # noqa: E402

FOLDER = 9                                  # J (the courses are E-H, the costumes I)
N_CLUBS = 14


def file_id(sub, club):
    """File ID of J/<sub letter>/<club letter> (odd, like the HUD's own)."""
    return 2 * (676 * FOLDER + 26 * sub + club) + 1


def path_of(sub, club):
    return f"{chr(65 + FOLDER)}/{chr(65 + sub)}/{chr(65 + club)}"


LABEL_BASE, BALL_BASE = file_id(0, 0), file_id(1, 0)
# golf: `addi r4,r4,0xa29` (r4 = 0 from the lis before it; then add r4,r28,r4, r28 = 2 x club): the name's file
LABEL_HOOKS = ((0x8042FBE4, 0x38840A29), (0x8042FD90, 0x38840A29))
# golf: `add r3,r28,r29` (r29 = 0xa45; r3 the preload's file, FUN_8000baac(id, 6); then add r29,r31,r29, r31 = 2 x
# club + 0x1C x club set: the picture's file)
BALL_HOOKS = ((0x8042FB98, 0x7C7CEA14), (0x8042FD44, 0x7C7CEA14))
BADGE_CACHE = 0x80506080      # golf: the picture's (2 x club + 0x1C x set) and the name's (2 x club) last loaded files;
                              # they start at 0 = club 0's (loaded as the HUD starts), so club 0 wouldn't reload

LABEL_SIZE, BALL_SIZE = (54, 96), (117, 78)     # (height, width), as the game's
TOP, BOTTOM = np.array([255, 253, 238]), np.array([246, 160, 146])   # the letters' gradient
OUTLINE = (44, 26, 22)
LEATHER, LEATHER_HI, LEATHER_LO = (156, 86, 40), (196, 122, 64), (104, 54, 26)
LACE = (246, 242, 232)
TEE = (236, 120, 36)


def type_of(club):
    """The shot type a club shows: its own, else the nearest pass's (fbpose.py's fp_snap makes it that one)."""
    for k, (_n, c, _a, _s, _t) in enumerate(fb.SHOT_TYPES):
        if c == club:
            return k
    passes = sorted(fb.SHOT_TYPES[:fb.TYPE_FG], key=lambda t: t[1])
    best = min(passes, key=lambda t: (abs(t[1] - club), -t[1]))
    return fb.SHOT_TYPES.index(best)


BADGE_NAMES = ("Bomb", "Bullet", "Lob", "Kick")     # by shot type (football.SHOT_TYPES' order)


def _fit(scale):
    """The font size that fits every badge name."""
    from PIL import Image, ImageDraw
    import teams
    h, w = LABEL_SIZE
    for size in range(46, 8, -1):
        font = teams._font(size * scale)
        boxes = [ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), t, font=font, stroke_width=3 * scale)
                 for t in BADGE_NAMES]
        if all(b[2] - b[0] <= (w - 4) * scale and b[3] - b[1] <= (h - 4) * scale for b in boxes):
            return size
    raise SystemExit("the badge names don't fit")


def label_image(text, scale=4):
    """The name in the game's style: light letters, top to bottom white to pink, with a thick dark outline."""
    from PIL import Image, ImageDraw
    import teams
    h, w = LABEL_SIZE
    font = teams._font(_fit(scale) * scale)
    stroke = 3 * scale
    box = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=font, stroke_width=stroke)
    big = (w * scale, h * scale)
    x = (big[0] - (box[2] - box[0])) // 2 - box[0]
    y = (big[1] - (box[3] - box[1])) // 2 - box[1]
    outer, inner = Image.new("L", big), Image.new("L", big)
    ImageDraw.Draw(outer).text((x, y), text, font=font, fill=255, stroke_width=stroke, stroke_fill=255)
    ImageDraw.Draw(inner).text((x, y), text, font=font, fill=255)
    o = np.asarray(outer.resize((w, h), Image.BOX), np.float64) / 255
    i = np.asarray(inner.resize((w, h), Image.BOX), np.float64) / 255
    t = np.clip((np.arange(h) - h * 0.2) / (h * 0.6), 0, 1)[:, None, None]
    fill = TOP * (1 - t) + BOTTOM * t
    rgb = np.array(OUTLINE) * (1 - i[..., None]) + fill * i[..., None]
    out = np.zeros((h, w, 4), np.uint8)
    out[..., :3] = np.clip(rgb + 0.5, 0, 255).astype(np.uint8)
    out[..., 3] = np.where(o >= 0.5, 255, 0)
    return out


def ball_image(kick, scale=4):
    """A football: thrown (tilted, nose up and right, with speed lines), or standing on an orange kicking tee."""
    from PIL import Image, ImageDraw
    h, w = BALL_SIZE
    W, H = w * scale, h * scale
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = scale
    if kick:
        d.polygon([(W * 0.30, H * 0.95), (W * 0.70, H * 0.95), (W * 0.58, H * 0.80), (W * 0.42, H * 0.80)],
                  fill=TEE, outline=OUTLINE, width=2 * s)
        cx, cy, angle, length, girth = W * 0.5, H * 0.50, 90, H * 0.62, W * 0.62
    else:
        for dx, dy in ((-0.10, 0.0), (0.02, 0.07), (0.14, 0.14)):   # speed lines behind the ball
            x0, y0 = W * (0.30 + dx), H * (0.66 + dy)
            seg = [(x0, y0), (x0 - W * 0.20, y0 + H * 0.12)]
            d.line(seg, fill=OUTLINE + (255,), width=6 * s)
            d.line(seg, fill=LACE + (255,), width=3 * s)
        cx, cy, angle, length, girth = W * 0.54, H * 0.40, 55, H * 0.62, W * 0.58
    ball = Image.new("RGBA", (int(length) + 8 * s, int(length) + 8 * s), (0, 0, 0, 0))
    b = ImageDraw.Draw(ball)
    bw, bh = ball.size
    box = [bw / 2 - length / 2, bh / 2 - girth / 2, bw / 2 + length / 2, bh / 2 + girth / 2]
    b.ellipse(box, fill=OUTLINE)
    inset = 3 * s
    b.ellipse([box[0] + inset, box[1] + inset, box[2] - inset, box[3] - inset], fill=LEATHER_LO)
    b.ellipse([box[0] + inset, box[1] + inset, box[2] - inset, box[3] - inset - girth * 0.18], fill=LEATHER)
    b.ellipse([bw / 2 - length * 0.30, box[1] + girth * 0.16, bw / 2 + length * 0.18, box[1] + girth * 0.36],
              fill=LEATHER_HI)
    for side in (-1, 1):                    # white stripes near the ends
        xs = bw / 2 + side * length * 0.30
        b.line([(xs, bh / 2 - girth * 0.36), (xs, bh / 2 + girth * 0.36)], fill=LACE, width=3 * s)
    b.line([(bw / 2 - length * 0.17, bh / 2 - girth * 0.10), (bw / 2 + length * 0.17, bh / 2 - girth * 0.10)],
           fill=LACE, width=2 * s)          # the laces
    for k in range(-3, 4):
        x = bw / 2 + k * length * 0.05
        b.line([(x, bh / 2 - girth * 0.20), (x, bh / 2 + girth * 0.0)], fill=LACE, width=2 * s)
    ball = ball.rotate(angle, resample=Image.BICUBIC, expand=False)
    img.alpha_composite(ball, (int(cx - bw / 2), int(cy - bh / 2)))
    out = np.asarray(img.resize((w, h), Image.BOX))
    out = out.copy()
    out[..., 3] = np.where(out[..., 3] >= 128, 255, 0)
    return out


def texture_file(rgba):
    """A one-picture texture set (as the HUD's: magic, count 1, its header at 0x14, the CMPR data at 0x40), packed
    as LZSS type 1 like the game's."""
    h, w = rgba.shape[:2]
    head = struct.pack(">IIII I", 0x0020AF30, 1, 0xC, 0x14, 0)
    head += struct.pack(">9I", h << 16 | w, 14, 0x40, 0, 0, 1, 1, 0, 0)
    head += bytes(0x40 - len(head))
    th, tw = -(-h // 8) * 8, -(-w // 8) * 8
    px = np.pad(rgba, ((0, th - h), (0, tw - w), (0, 0)), mode="edge")
    return camelot_lz.pack(1, head + shyguy.cmpr(px))


def files():
    """{disc path: bytes}: every club's name and picture under J/."""
    names = {k: label_image(BADGE_NAMES[k]) for k in range(len(fb.SHOT_TYPES))}
    balls = {kick: ball_image(kick) for kick in (False, True)}
    out = {}
    for club in range(N_CLUBS):
        k = type_of(club)
        out[path_of(0, club)] = texture_file(names[k])
        out[path_of(1, club)] = texture_file(balls[k == fb.TYPE_FG])
    return out


if __name__ == "__main__":
    from PIL import Image
    pics = [label_image(t) for t in BADGE_NAMES]
    sheet = Image.new("RGBA", (96 * 4 + 78 * 2, 117), (60, 120, 60, 255))
    for k, p in enumerate(pics):
        sheet.alpha_composite(Image.fromarray(p), (96 * k, 0))
    for k, kick in enumerate((False, True)):
        sheet.alpha_composite(Image.fromarray(ball_image(kick)), (96 * 4 + 78 * k, 0))
    out = sys.argv[1] if len(sys.argv) > 1 else "fbhud.png"
    sheet.resize((sheet.width * 2, sheet.height * 2), Image.NEAREST).save(out)
    print(out, {p: len(b) for p, b in list(files().items())[:4]})
