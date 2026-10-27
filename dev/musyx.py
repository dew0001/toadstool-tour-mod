"""MusyX sound groups (Toadstool Tour's character voices) and GameCube DSP ADPCM.

Each MusyX group is four files in a row on the disc (main.dol's group table at 0x80137308 lists them; see
RE-NOTES.md Sound): pool (macros), project (sound effects), sample directory and sample data.

  project: sound effect table of 10-byte entries (sfx ID, macro ID, priority, max voices, velocity, pan, key, 0),
           found as the run of consecutive sfx IDs; ends with 0xFFFFFFFF.
  pool:    +0 -> macros: (u32 size, u16 macro ID, u16 0, 8-byte commands); command 0x10 (low byte of the first word)
           starts the sample in its bytes 1-2.
  sdir:    0x20-byte entries until 0xFFFF: u16 sample ID, u16 0, u32 offset in the sample data, u32 0, u8 key (60),
           u8 0, u16 sample rate, u32 sample count, u32 loop start, u32 loop length, u32 -> 0x28-byte ADPCM block
           (u16 8, u8 first frame header, u8 loop frame header, u16 hist2, u16 hist1, s16 coefficients[16]).
  samp:    each sample's ADPCM frames, starting on a 32-byte boundary.

DSP ADPCM: 8-byte frames of 14 samples. Header byte = predictor << 4 | shift; each 4-bit signed nibble decodes as
clamp16((nibble << shift << 11) + 1024 + c1 * hist1 + c2 * hist2 >> 11) with the predictor's coefficient pair.
"""
import io
import struct
import wave

import numpy as np

FRAME = 14


def u16(b, o):
    return struct.unpack_from(">H", b, o)[0]


def u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def sfx_macros(proj):
    """{sfx ID: macro ID} from a project file."""
    for start in range(0, len(proj) - 20, 2):   # the table is the first run of consecutive sfx IDs
        a, b = proj[start:start + 10], proj[start + 10:start + 20]
        if a[4:] == b[4:] and u16(b, 0) == u16(a, 0) + 1:
            break
    else:
        raise ValueError("no sound effect table")
    out, o = {}, start
    while o + 10 <= len(proj) and proj[o:o + 4] != b"\xff\xff\xff\xff":
        out[u16(proj, o)] = u16(proj, o + 2)
        o += 10
    return out


def macro_samples(pool):
    """{macro ID: sample ID it starts}."""
    out, o = {}, u32(pool, 0)
    while o + 8 <= len(pool) and u32(pool, o) != 0xFFFFFFFF and u32(pool, o):
        size, mid = u32(pool, o), u16(pool, o + 4)
        for c in range(o + 8, o + size, 8):
            if pool[c + 3] == 0x10:
                out[mid] = u16(pool, c + 1)
                break
        o += size
    return out


def sfx_samples(pool, proj):
    """{sfx ID: sample ID}."""
    macros = macro_samples(pool)
    return {sfx: macros[m] for sfx, m in sfx_macros(proj).items() if m in macros}


def sdir_entries(sdir):
    """[(entry offset, sample ID, data offset, rate, sample count, ADPCM block offset)]."""
    out, o = [], 0
    while u16(sdir, o) != 0xFFFF:
        out.append((o, u16(sdir, o), u32(sdir, o + 4), u16(sdir, o + 0xE), u32(sdir, o + 0x10) & 0xFFFFFF,
                    u32(sdir, o + 0x1C)))
        o += 0x20
    return out


def decode(data, coefs, count):
    """DSP ADPCM frames -> int16 samples."""
    out = np.zeros(((count + FRAME - 1) // FRAME) * FRAME, np.int64)
    h1 = h2 = 0
    for f in range(len(out) // FRAME):
        ps = data[8 * f]
        c1, c2 = coefs[2 * (ps >> 4)], coefs[2 * (ps >> 4) + 1]
        for i in range(FRAME):
            byte = data[8 * f + 1 + i // 2]
            nib = (byte >> 4) if i % 2 == 0 else byte & 15
            nib -= 16 * (nib >= 8)
            s = ((nib << (ps & 15)) << 11) + 1024 + c1 * h1 + c2 * h2 >> 11
            s = max(-32768, min(32767, s))
            out[FRAME * f + i], h2, h1 = s, h1, s
    return out[:count].astype(np.int16)


def coefficients(x):
    """Eight Q11 predictor pairs for x: order-2 linear prediction of each frame, clustered by energy (k-means)."""
    x = x.astype(np.float64)
    pad = np.concatenate([np.zeros(2), x, np.zeros((-len(x)) % FRAME)])
    frames, weights = [], []
    for f in range((len(pad) - 2) // FRAME):
        seg = pad[2 + FRAME * f - 2:2 + FRAME * f + FRAME]
        y, a = seg[2:], np.stack([seg[1:-1], seg[:-2]], 1)
        e = float((y * y).sum())
        if e < 1.0:
            continue
        sol = np.linalg.lstsq(a.T @ a + np.eye(2) * 1e-3 * e, a.T @ y, rcond=None)[0]
        frames.append(np.clip(sol, -3.9, 3.9))
        weights.append(e)
    fixed = np.array([[0, 0], [1, 0], [2, -1], [1.5, -0.6], [0.5, 0], [1.8, -0.85], [1.2, -0.3], [1.9, -0.95]])
    if len(frames) < 8:
        cent = fixed
    else:
        p, w = np.array(frames), np.sqrt(np.array(weights))
        cent = fixed.copy()
        for _ in range(30):
            d = ((p[:, None, :] - cent[None]) ** 2).sum(-1)
            lab = d.argmin(1)
            for k in range(8):
                m = lab == k
                if m.any():
                    cent[k] = (p[m] * w[m, None]).sum(0) / w[m].sum()
    return np.clip(np.round(cent * 2048), -32768, 32767).astype(np.int64).reshape(-1)


def encode(x):
    """int16 samples -> (ADPCM frames, 16 coefficients). Each frame tries every predictor and shift."""
    x = np.concatenate([np.asarray(x, np.int64), np.zeros((-len(x)) % FRAME, np.int64)])
    coefs = coefficients(x)
    preds, shifts = np.meshgrid(np.arange(8), np.arange(12), indexing="ij")
    preds, shifts = preds.reshape(-1), shifts.reshape(-1)
    c1, c2, step = coefs[2 * preds], coefs[2 * preds + 1], 1 << shifts
    out = bytearray()
    h1 = h2 = 0
    for f in range(len(x) // FRAME):
        seg = x[FRAME * f:FRAME * f + FRAME]
        a1, a2 = np.full(len(preds), h1, np.int64), np.full(len(preds), h2, np.int64)
        err, nibs = np.zeros(len(preds)), np.zeros((len(preds), FRAME), np.int64)
        for i in range(FRAME):
            p = (1024 + c1 * a1 + c2 * a2) >> 11
            nib = np.clip(np.floor((seg[i] - p) / step + 0.5), -8, 7).astype(np.int64)
            dec = np.clip(nib * step + p, -32768, 32767)
            err += (seg[i] - dec) ** 2
            nibs[:, i] = nib
            a2, a1 = a1, dec
        k = int(err.argmin())
        out.append(int(preds[k]) << 4 | int(shifts[k]))
        q = nibs[k] & 15
        out += bytes(int(q[i] << 4 | q[i + 1]) for i in range(0, FRAME, 2))
        h1, h2 = int(a1[k]), int(a2[k])
    return bytes(out), coefs


def read_wav(data):
    """(float samples in -1..1, mono, rate) from WAV bytes (16-bit PCM)."""
    with wave.open(io.BytesIO(data)) as w:
        if w.getsampwidth() != 2:
            raise ValueError("only 16-bit WAV")
        pcm = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float64) / 32768
        if w.getnchannels() > 1:
            pcm = pcm.reshape(-1, w.getnchannels()).mean(1)
        return pcm, w.getframerate()


def resample(x, src, dst):
    """Band-limited resampling (FFT), so going down in rate filters out what the new rate can't hold."""
    if src == dst:
        return x
    n = len(x)
    pad = n // 4 + 64
    y = np.concatenate([np.zeros(pad), x, np.zeros(pad)])
    m = int(round(len(y) * dst / src))
    spec = np.fft.rfft(y)
    keep = min(len(spec), m // 2 + 1)
    out = np.fft.irfft(np.concatenate([spec[:keep], np.zeros(m // 2 + 1 - keep)]), m) * (m / len(y))
    cut = int(round(pad * dst / src))
    return out[cut:cut + int(round(n * dst / src))]


def rebuild(sdir, sounds):
    """New (sdir, samp) with every sample replaced. sounds: {sample ID: int16 samples at the entry's rate}."""
    sdir = bytearray(sdir)
    samp = bytearray()
    for at, sid, _, rate, _, block in sdir_entries(sdir):
        data, coefs = encode(sounds[sid])
        samp += bytes((-len(samp)) % 32)
        struct.pack_into(">I", sdir, at + 4, len(samp))
        struct.pack_into(">I", sdir, at + 0x10, len(sounds[sid]))
        struct.pack_into(">II", sdir, at + 0x14, 0, 0)
        struct.pack_into(">HBBHH16h", sdir, block, 8, data[0], 0, 0, 0, *(int(c) for c in coefs))
        samp += data
    samp += bytes((-len(samp)) % 32)
    return bytes(sdir), bytes(samp)


def replace_in_place(sdir, samp, sid, pcm):
    """(sdir, samp) with one sample re-encoded where it is, so nothing else moves. Its new frames must fit before
    the next sample's data."""
    sdir, samp = bytearray(sdir), bytearray(samp)
    entries = sdir_entries(sdir)
    at, _, off, _, _, block = next(e for e in entries if e[1] == sid)
    room = min([e[2] for e in entries if e[2] > off] + [len(samp)]) - off
    data, coefs = encode(pcm)
    if len(data) > room:
        raise ValueError(f"sample 0x{sid:X}: {len(data)} bytes, room for {room}")
    samp[off:off + len(data)] = data
    struct.pack_into(">I", sdir, at + 0x10, len(pcm))
    struct.pack_into(">II", sdir, at + 0x14, 0, 0)
    struct.pack_into(">HBBHH16h", sdir, block, 8, data[0], 0, 0, 0, *(int(c) for c in coefs))
    return bytes(sdir), bytes(samp)
