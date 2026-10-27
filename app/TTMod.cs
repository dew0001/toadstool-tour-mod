// Toadstool Tour Mod - core: disc reading, Camelot LZSS, disc rebuild, MEGA download.
// Compiled at run time by Windows PowerShell 5.1 (C# 5): no string interpolation or newer syntax.
using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

public static class TTMod
{
    public const long DiscSize = 1459978240L; // every GameCube disc image is this size

    // ---------------------------------------------------------------- sources
    public abstract class Source : IDisposable
    {
        public abstract void Read(long offset, byte[] buf, int index, int count);
        public abstract void Dispose();
        public byte[] Read(long offset, int count)
        {
            byte[] b = new byte[count];
            Read(offset, b, 0, count);
            return b;
        }
    }

    class IsoSource : Source
    {
        FileStream fs;
        public IsoSource(string path) { fs = File.OpenRead(path); }
        public override void Read(long offset, byte[] buf, int index, int count)
        {
            fs.Seek(offset, SeekOrigin.Begin);
            int got = 0;
            while (got < count)
            {
                int r = fs.Read(buf, index + got, count - got);
                if (r <= 0) throw new EndOfStreamException("game file is truncated");
                got += r;
            }
        }
        public override void Dispose() { fs.Dispose(); }
    }

    // CISO: "CISO", block size (LE), 0x7FF8-entry map (1 = stored), stored blocks in order from 0x8000.
    class CisoSource : Source
    {
        FileStream fs;
        int bs;
        long[] where;
        public CisoSource(string path)
        {
            fs = File.OpenRead(path);
            byte[] hdr = new byte[0x8000];
            fs.Read(hdr, 0, hdr.Length);
            bs = BitConverter.ToInt32(hdr, 4);
            where = new long[0x7FF8];
            long n = 0;
            for (int i = 0; i < where.Length; i++) where[i] = hdr[8 + i] == 1 ? 0x8000 + (n++) * bs : -1;
        }
        public override void Read(long offset, byte[] buf, int index, int count)
        {
            while (count > 0)
            {
                long block = offset / bs;
                int inBlock = (int)(offset % bs);
                int take = Math.Min(count, bs - inBlock);
                long at = block < where.Length ? where[block] : -1;
                if (at < 0) Array.Clear(buf, index, take);
                else
                {
                    fs.Seek(at + inBlock, SeekOrigin.Begin);
                    int got = 0;
                    while (got < take)
                    {
                        int r = fs.Read(buf, index + got, take - got);
                        if (r <= 0) throw new EndOfStreamException("game file is truncated");
                        got += r;
                    }
                }
                offset += take; index += take; count -= take;
            }
        }
        public override void Dispose() { fs.Dispose(); }
    }

    public static Source Open(string path)
    {
        byte[] magic = new byte[4];
        using (FileStream f = File.OpenRead(path)) f.Read(magic, 0, 4);
        if (Encoding.ASCII.GetString(magic) == "CISO") return new CisoSource(path);
        return new IsoSource(path);
    }

    // "GFTE01" plus revision, or null if this isn't a GameCube disc.
    public static string GameId(Source s)
    {
        byte[] h = s.Read(0, 0x20);
        if (BE32(h, 0x1C) != 0xC2339F3D) return null;
        return Encoding.ASCII.GetString(h, 0, 6) + "-rev" + h[7];
    }

    // ---------------------------------------------------------------- disc structure
    public class Entry
    {
        public string Path;
        public bool IsDir;
        public long Offset;
        public long Length;
        public int Index;
    }

    public class Disc
    {
        public byte[] Boot, Bi2, Apploader, Fst, Dol;
        public long DolOffset, FstOffset;
        public List<Entry> Files = new List<Entry>();
    }

    public static Disc ReadDisc(Source s)
    {
        Disc d = new Disc();
        d.Boot = s.Read(0, 0x440);
        d.Bi2 = s.Read(0x440, 0x2000);
        byte[] ah = s.Read(0x2440, 0x20);
        d.Apploader = s.Read(0x2440, (int)(0x20 + BE32(ah, 0x14) + BE32(ah, 0x18)));
        d.DolOffset = BE32(d.Boot, 0x420);
        d.FstOffset = BE32(d.Boot, 0x424);
        d.Fst = s.Read(d.FstOffset, (int)BE32(d.Boot, 0x428));
        byte[] dh = s.Read(d.DolOffset, 0x100);
        long dolEnd = 0;
        for (int i = 0; i < 18; i++)
        {
            long size = BE32(dh, 0x90 + 4 * i);
            if (size != 0) dolEnd = Math.Max(dolEnd, BE32(dh, 4 * i) + size);
        }
        d.Dol = s.Read(d.DolOffset, (int)dolEnd);

        int n = (int)BE32(d.Fst, 8);
        int strBase = n * 12;
        string[] dirPath = new string[n];
        int[] dirEnd = new int[n];
        List<int> stack = new List<int>();
        stack.Add(0); dirPath[0] = "files"; dirEnd[0] = n;
        for (int i = 1; i < n; i++)
        {
            while (i >= dirEnd[stack[stack.Count - 1]]) stack.RemoveAt(stack.Count - 1);
            int nameOff = (d.Fst[i * 12 + 1] << 16) | (d.Fst[i * 12 + 2] << 8) | d.Fst[i * 12 + 3];
            int z = strBase + nameOff;
            while (d.Fst[z] != 0) z++;
            string name = Encoding.ASCII.GetString(d.Fst, strBase + nameOff, z - strBase - nameOff);
            string path = dirPath[stack[stack.Count - 1]] + "/" + name;
            if (d.Fst[i * 12] != 0)
            {
                dirPath[i] = path; dirEnd[i] = (int)BE32(d.Fst, i * 12 + 8); stack.Add(i);
            }
            else
            {
                Entry e = new Entry();
                e.Path = path; e.Index = i;
                e.Offset = BE32(d.Fst, i * 12 + 4); e.Length = BE32(d.Fst, i * 12 + 8);
                d.Files.Add(e);
            }
        }
        return d;
    }

    // SHA-1 of every disc part and file, keyed "sys/boot.bin", "sys/main.dol", "files/A/B/C", ...
    public static Dictionary<string, string> Manifest(Source s, Disc d)
    {
        Dictionary<string, string> m = new Dictionary<string, string>();
        m["sys/boot.bin"] = Sha1(d.Boot);
        m["sys/bi2.bin"] = Sha1(d.Bi2);
        m["sys/apploader.img"] = Sha1(d.Apploader);
        m["sys/fst.bin"] = Sha1(d.Fst);
        m["sys/main.dol"] = Sha1(d.Dol);
        byte[] buf = new byte[4 << 20];
        foreach (Entry e in d.Files)
        {
            using (SHA1 h = SHA1.Create())
            {
                long left = e.Length, at = e.Offset;
                while (left > 0)
                {
                    int take = (int)Math.Min(buf.Length, left);
                    s.Read(at, buf, 0, take);
                    h.TransformBlock(buf, 0, take, null, 0);
                    at += take; left -= take;
                }
                h.TransformFinalBlock(buf, 0, 0);
                m[e.Path] = Hex(h.Hash);
            }
        }
        return m;
    }

    public static byte[] ReadPart(Source s, Disc d, string path)
    {
        if (path == "sys/boot.bin") return (byte[])d.Boot.Clone();
        if (path == "sys/main.dol") return (byte[])d.Dol.Clone();
        foreach (Entry e in d.Files) if (e.Path == path) return s.Read(e.Offset, (int)e.Length);
        throw new FileNotFoundException(path + " is not on the disc");
    }

    // Files the game doesn't have (the 8th course, under files/E/): new folders and files appended to the file
    // table after everything else, in the same depth-first order the table uses. Returns the new table and each
    // new file's entry number.
    static byte[] AddToFst(byte[] fst, List<string> paths, Dictionary<string, int> index)
    {
        int n = (int)BE32(fst, 8);
        int strBase = n * 12;
        List<byte> strings = new List<byte>();
        for (int i = strBase; i < fst.Length; i++) strings.Add(fst[i]);
        while (strings.Count > 0 && strings[strings.Count - 1] == 0 && strings.Count > 1 && strings[strings.Count - 2] == 0)
            strings.RemoveAt(strings.Count - 1);   // keep one terminator, drop the padding
        List<long[]> entries = new List<long[]>();   // type, name offset, word 1, word 2
        SortedDictionary<string, object> tree = new SortedDictionary<string, object>(StringComparer.Ordinal);
        foreach (string p in paths)
        {
            string[] parts = p.Substring("files/".Length).Split('/');
            SortedDictionary<string, object> node = tree;
            for (int k = 0; k < parts.Length - 1; k++)
            {
                if (!node.ContainsKey(parts[k])) node[parts[k]] = new SortedDictionary<string, object>(StringComparer.Ordinal);
                node = (SortedDictionary<string, object>)node[parts[k]];
            }
            node[parts[parts.Length - 1]] = p;
        }
        Add(tree, 0, n, entries, strings, index);
        int total = n + entries.Count;
        byte[] outp = new byte[Align(total * 12 + strings.Count, 4)];
        Array.Copy(fst, 0, outp, 0, n * 12);
        PutBE32(outp, 8, total);
        for (int i = 0; i < entries.Count; i++)
        {
            long[] e = entries[i];
            int at = (n + i) * 12;
            PutBE32(outp, at, (e[0] << 24) | e[1]);
            PutBE32(outp, at + 4, e[2]);
            PutBE32(outp, at + 8, e[3]);
        }
        for (int i = 0; i < strings.Count; i++) outp[total * 12 + i] = strings[i];
        return outp;
    }

    static void Add(SortedDictionary<string, object> node, int parent, int first, List<long[]> entries, List<byte> strings,
                    Dictionary<string, int> index)
    {
        foreach (KeyValuePair<string, object> kv in node)
        {
            int me = first + entries.Count;
            long name = strings.Count;
            strings.AddRange(Encoding.ASCII.GetBytes(kv.Key)); strings.Add(0);
            if (kv.Value is string)
            {
                entries.Add(new long[] { 0, name, 0, 0 });
                index[(string)kv.Value] = me;
            }
            else
            {
                long[] dir = new long[] { 1, name, parent, 0 };
                entries.Add(dir);
                Add((SortedDictionary<string, object>)kv.Value, me, first, entries, strings, index);
                dir[3] = first + entries.Count;   // the entry after this folder's last one
            }
        }
    }

    // Write a complete disc image: Nintendo's layout kept, changed files rewritten in place or, if
    // they grew, moved into the empty area between the file table and the first file (as are new files).
    // Everything not written is zero, so the result depends only on file contents (identical for every friend).
    public static void Build(Source s, Disc d, Dictionary<string, byte[]> changed, string outPath)
    {
        byte[] boot = changed.ContainsKey("sys/boot.bin") ? changed["sys/boot.bin"] : (byte[])d.Boot.Clone();
        byte[] dol = changed.ContainsKey("sys/main.dol") ? changed["sys/main.dol"] : d.Dol;
        byte[] fst = (byte[])d.Fst.Clone();
        HashSet<string> known = new HashSet<string>();
        foreach (Entry e in d.Files) known.Add(e.Path);
        List<string> added = new List<string>();
        foreach (string p in changed.Keys) if (p.StartsWith("files/") && !known.Contains(p)) added.Add(p);
        added.Sort(StringComparer.Ordinal);
        Dictionary<string, int> addedIndex = new Dictionary<string, int>();
        if (added.Count > 0)
        {
            fst = AddToFst(fst, added, addedIndex);
            PutBE32(boot, 0x428, fst.Length);
            PutBE32(boot, 0x42C, fst.Length);
        }

        long lowest = d.DolOffset;
        foreach (Entry e in d.Files) lowest = Math.Min(lowest, e.Offset);
        long freeAt = Align(Math.Max(0x2440 + d.Apploader.Length, d.FstOffset + fst.Length), 0x8000);

        long dolOffset = d.DolOffset;
        if (dol.Length > d.Dol.Length)
        {
            dolOffset = freeAt; freeAt = Align(freeAt + dol.Length, 0x20);
        }
        Dictionary<string, long> placed = new Dictionary<string, long>();
        foreach (Entry e in d.Files)
        {
            long off = e.Offset, len = e.Length;
            if (e.Offset == d.DolOffset && e.Length == d.Dol.Length) { off = dolOffset; len = dol.Length; } // default.dol alias
            else if (changed.ContainsKey(e.Path))
            {
                len = changed[e.Path].Length;
                if (len > e.Length) { off = freeAt; freeAt = Align(freeAt + len, 0x20); }
            }
            placed[e.Path] = off;
            PutBE32(fst, e.Index * 12 + 4, off);
            PutBE32(fst, e.Index * 12 + 8, len);
        }
        foreach (string p in added)
        {
            long len = changed[p].Length;
            placed[p] = freeAt;
            PutBE32(fst, addedIndex[p] * 12 + 4, freeAt);
            PutBE32(fst, addedIndex[p] * 12 + 8, len);
            freeAt = Align(freeAt + len, 0x20);
        }
        if (freeAt > lowest) throw new InvalidOperationException("mod files don't fit on the disc");
        PutBE32(boot, 0x420, dolOffset);

        string tmp = outPath + ".part";
        if (File.Exists(tmp)) File.Delete(tmp);
        using (FileStream o = new FileStream(tmp, FileMode.CreateNew, FileAccess.Write, FileShare.None, 1 << 20))
        {
            o.SetLength(DiscSize);
            WriteAt(o, 0, boot);
            WriteAt(o, 0x440, d.Bi2);
            WriteAt(o, 0x2440, d.Apploader);
            WriteAt(o, d.FstOffset, fst);
            List<Entry> order = new List<Entry>(d.Files);
            order.Sort(delegate (Entry a, Entry b) { return placed[a.Path].CompareTo(placed[b.Path]); });
            byte[] buf = new byte[4 << 20];
            foreach (Entry e in order)
            {
                if (e.Offset == d.DolOffset && e.Length == d.Dol.Length) continue; // written as main.dol
                long at = placed[e.Path];
                if (changed.ContainsKey(e.Path)) { WriteAt(o, at, changed[e.Path]); continue; }
                long left = e.Length, from = e.Offset;
                o.Seek(at, SeekOrigin.Begin);
                while (left > 0)
                {
                    int take = (int)Math.Min(buf.Length, left);
                    s.Read(from, buf, 0, take);
                    o.Write(buf, 0, take);
                    from += take; left -= take;
                }
            }
            foreach (string p in added) WriteAt(o, placed[p], changed[p]);
            WriteAt(o, dolOffset, dol);
        }
        if (File.Exists(outPath)) File.Delete(outPath);
        File.Move(tmp, outPath);
    }

    // ---------------------------------------------------------------- Camelot LZSS
    public static byte[] Decompress(byte[] data)
    {
        int end;
        return Decompress(data, out end);
    }

    // `end` is the offset just past the stream's end marker (a type 2 file's relocation table follows it).
    public static byte[] Decompress(byte[] data, out int end)
    {
        List<byte> o = new List<byte>(((data[1] << 16) | (data[2] << 8) | data[3]) + 16);
        int src = 4;
        while (true)
        {
            int flags = data[src++];
            for (int bit = 7; bit >= 0; bit--)
            {
                if (((flags >> bit) & 1) == 0) { o.Add(data[src++]); continue; }
                int b1 = data[src], b2 = data[src + 1];
                int dist = ((b1 & 0xF0) << 4) | b2;
                if (dist == 0) { end = src + 2; return o.ToArray(); }
                int len;
                if ((b1 & 0x0F) != 0) { len = (b1 & 0x0F) + 1; src += 2; }
                else { len = data[src + 2] + 0x11; src += 3; }
                int pos = o.Count - dist;
                if (pos < 0) throw new InvalidDataException("bad back-reference");
                for (int i = 0; i < len; i++) o.Add(o[pos + i]);
            }
        }
    }

    // A type 2 file's relocation table: its 8-byte entries without the terminator.
    public static byte[] Relocations(byte[] data)
    {
        int end;
        Decompress(data, out end);
        int at = (end + 7) & ~7, n = at;
        while (data[n] != 0xFF) n += 8;
        byte[] t = new byte[n - at];
        Array.Copy(data, at, t, 0, t.Length);
        return t;
    }

    // Type 2: the LZSS file, then the relocation table at the next 8-byte boundary, ended by 8 x 0xFF.
    public static byte[] Pack(int kind, byte[] data, byte[] relocations)
    {
        byte[] body = Pack(kind, data);
        int at = (int)Align(body.Length, 8);
        byte[] o = new byte[at + relocations.Length + 8];
        Array.Copy(body, o, body.Length);
        Array.Copy(relocations, 0, o, at, relocations.Length);
        for (int i = 0; i < 8; i++) o[at + relocations.Length + i] = 0xFF;
        return o;
    }

    // Same greedy matcher as the mod's Python tools, so output is byte-identical.
    public static byte[] Pack(int kind, byte[] data)
    {
        int n = data.Length;
        MemoryStream outp = new MemoryStream();
        outp.WriteByte((byte)kind);
        outp.WriteByte((byte)(n >> 16)); outp.WriteByte((byte)(n >> 8)); outp.WriteByte((byte)n);
        Dictionary<int, int> head = new Dictionary<int, int>();
        int[] prev = new int[Math.Max(n, 1)];
        int flags = 0, count = 0;
        List<byte> group = new List<byte>(32);
        int i = 0;
        while (i < n)
        {
            int bestLen = 0, bestDist = 0;
            if (i + 2 < n)
            {
                int key = (data[i] << 16) | (data[i + 1] << 8) | data[i + 2];
                int cand;
                if (!head.TryGetValue(key, out cand)) cand = -1;
                int limit = Math.Min(0x110, n - i);
                int depth = 0;
                while (cand >= 0 && i - cand <= 0xFFF && depth < 48)
                {
                    if (bestLen < limit && data[cand + bestLen] == data[i + bestLen])
                    {
                        int len = 0;
                        while (len < limit && data[cand + len] == data[i + len]) len++;
                        if (len > bestLen)
                        {
                            bestLen = len; bestDist = i - cand;
                            if (len == limit) break;
                        }
                    }
                    cand = prev[cand];
                    depth++;
                }
            }
            if (bestLen >= 3)
            {
                if (bestLen <= 0x10) { group.Add((byte)(((bestDist >> 8) << 4) | (bestLen - 1))); group.Add((byte)bestDist); }
                else { group.Add((byte)((bestDist >> 8) << 4)); group.Add((byte)bestDist); group.Add((byte)(bestLen - 0x11)); }
                flags |= 0x80 >> count;
                Finish(outp, ref flags, ref count, group);
                for (int p = i; p < i + bestLen; p++) Insert(data, head, prev, p);
                i += bestLen;
            }
            else
            {
                group.Add(data[i]);
                Finish(outp, ref flags, ref count, group);
                Insert(data, head, prev, i);
                i++;
            }
        }
        group.Add(0); group.Add(0);
        flags |= 0x80 >> count;
        outp.WriteByte((byte)flags);
        foreach (byte b in group) outp.WriteByte(b);
        return outp.ToArray();
    }

    static void Finish(MemoryStream outp, ref int flags, ref int count, List<byte> group)
    {
        count++;
        if (count == 8)
        {
            outp.WriteByte((byte)flags);
            foreach (byte b in group) outp.WriteByte(b);
            flags = 0; count = 0; group.Clear();
        }
    }

    static void Insert(byte[] data, Dictionary<int, int> head, int[] prev, int pos)
    {
        if (pos + 2 < data.Length)
        {
            int key = (data[pos] << 16) | (data[pos + 1] << 8) | data[pos + 2];
            int old;
            prev[pos] = head.TryGetValue(key, out old) ? old : -1;
            head[key] = pos;
        }
    }

    // ---------------------------------------------------------------- MEGA public file download
    // Decrypts with the link key and checks MEGA's integrity MAC (same scheme as MEGA's own client).
    public static void MegaDownload(string link, string outPath)
    {
        ServicePointManager.SecurityProtocol = ServicePointManager.SecurityProtocol | (SecurityProtocolType)3072;
        Match m = Regex.Match(link, @"mega\.nz/file/([^#]+)#(.+)$");
        if (!m.Success) throw new ArgumentException("not a mega.nz/file link");
        byte[] k = B64Url(m.Groups[2].Value);
        byte[] key = new byte[16], nonce = new byte[8], metaMac = new byte[8];
        for (int i = 0; i < 16; i++) key[i] = (byte)(k[i] ^ k[i + 16]);
        Array.Copy(k, 16, nonce, 0, 8);
        Array.Copy(k, 24, metaMac, 0, 8);

        string resp;
        using (WebClient wc = new WebClient())
        {
            wc.Headers[HttpRequestHeader.ContentType] = "application/json";
            resp = wc.UploadString("https://g.api.mega.co.nz/cs?id=1", "[{\"a\":\"g\",\"g\":1,\"p\":\"" + m.Groups[1].Value + "\"}]");
        }
        Match g = Regex.Match(resp, "\"g\"\\s*:\\s*\"([^\"]+)\"");
        if (!g.Success) throw new IOException("MEGA did not return a download link: " + resp);
        byte[] enc;
        using (WebClient wc = new WebClient()) enc = wc.DownloadData(g.Groups[1].Value.Replace("\\/", "/"));

        using (Aes aes = Aes.Create())
        {
            aes.Key = key; aes.Mode = CipherMode.ECB; aes.Padding = PaddingMode.None;
            ICryptoTransform ecb = aes.CreateEncryptor();
            byte[] plain = new byte[enc.Length];
            byte[] ctr = new byte[16], ks = new byte[16];
            Array.Copy(nonce, ctr, 8);
            for (long blk = 0; blk * 16 < enc.Length; blk++)
            {
                for (int j = 0; j < 8; j++) ctr[15 - j] = (byte)(blk >> (8 * j));
                ecb.TransformBlock(ctr, 0, 16, ks, 0);
                int off = (int)(blk * 16);
                for (int j = 0; j < 16 && off + j < enc.Length; j++) plain[off + j] = (byte)(enc[off + j] ^ ks[j]);
            }

            // Chunk MACs: 128 KiB, 256 KiB, ... 1 MiB, then 1 MiB chunks.
            byte[] chunkIv = new byte[16];
            Array.Copy(nonce, 0, chunkIv, 0, 8); Array.Copy(nonce, 0, chunkIv, 8, 8);
            byte[] fileMac = new byte[16], x = new byte[16];
            int pos = 0;
            for (int i = 1; pos < plain.Length; i++)
            {
                int len = Math.Min(i < 8 ? i * 0x20000 : 0x100000, plain.Length - pos);
                byte[] mac = (byte[])chunkIv.Clone();
                for (int o = 0; o < len; o += 16)
                {
                    for (int j = 0; j < 16; j++) x[j] = (byte)(mac[j] ^ (o + j < len ? plain[pos + o + j] : (byte)0));
                    ecb.TransformBlock(x, 0, 16, mac, 0);
                }
                for (int j = 0; j < 16; j++) x[j] = (byte)(fileMac[j] ^ mac[j]);
                ecb.TransformBlock(x, 0, 16, fileMac, 0);
                pos += len;
            }
            for (int j = 0; j < 4; j++)
            {
                if ((byte)(fileMac[j] ^ fileMac[j + 4]) != metaMac[j] || (byte)(fileMac[j + 8] ^ fileMac[j + 12]) != metaMac[j + 4])
                    throw new InvalidDataException("MEGA download failed its integrity check");
            }
            File.WriteAllBytes(outPath, plain);
        }
    }

    // ---------------------------------------------------------------- helpers
    public static uint BE32(byte[] b, long o)
    {
        return ((uint)b[o] << 24) | ((uint)b[o + 1] << 16) | ((uint)b[o + 2] << 8) | b[o + 3];
    }

    static void PutBE32(byte[] b, long o, long v)
    {
        b[o] = (byte)(v >> 24); b[o + 1] = (byte)(v >> 16); b[o + 2] = (byte)(v >> 8); b[o + 3] = (byte)v;
    }

    static long Align(long v, long a) { return (v + a - 1) / a * a; }

    static void WriteAt(Stream s, long offset, byte[] data)
    {
        s.Seek(offset, SeekOrigin.Begin);
        s.Write(data, 0, data.Length);
    }

    static byte[] B64Url(string s)
    {
        s = s.Replace('-', '+').Replace('_', '/');
        while (s.Length % 4 != 0) s += "=";
        return Convert.FromBase64String(s);
    }

    public static string Hex(byte[] b)
    {
        return BitConverter.ToString(b).Replace("-", "").ToLowerInvariant();
    }

    public static string Sha1(byte[] b)
    {
        using (SHA1 h = SHA1.Create()) return Hex(h.ComputeHash(b));
    }

    public static string Sha1File(string path)
    {
        using (SHA1 h = SHA1.Create())
        using (FileStream f = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 1 << 20))
            return Hex(h.ComputeHash(f));
    }

    public static string Sha256File(string path)
    {
        using (SHA256 h = SHA256.Create())
        using (FileStream f = File.OpenRead(path))
            return Hex(h.ComputeHash(f));
    }

    public static byte[] FromHex(string s)
    {
        byte[] b = new byte[s.Length / 2];
        for (int i = 0; i < b.Length; i++) b[i] = Convert.ToByte(s.Substring(2 * i, 2), 16);
        return b;
    }

    // A copy of `b`, cut short or zero-filled to `n` bytes.
    public static byte[] Resize(byte[] b, long n)
    {
        byte[] o = new byte[n];
        Array.Copy(b, o, Math.Min(b.Length, n));
        return o;
    }

    // Move runs of the original file to new places (so the patch never carries game data).
    public static void ApplyCopies(byte[] target, byte[] source, long[] from, long[] to, long[] lengths)
    {
        for (int i = 0; i < from.Length; i++) Array.Copy(source, from[i], target, to[i], lengths[i]);
    }

    public static void ApplyEdits(byte[] target, long[] offsets, string[] hexes)
    {
        for (int i = 0; i < offsets.Length; i++)
        {
            byte[] bytes = FromHex(hexes[i]);
            Array.Copy(bytes, 0, target, offsets[i], bytes.Length);
        }
    }

    // A patch's data file (the bytes of the files the game doesn't have, gzip): its contents.
    public static byte[] Gunzip(string path)
    {
        using (FileStream f = File.OpenRead(path))
        using (GZipStream z = new GZipStream(f, CompressionMode.Decompress))
        using (MemoryStream m = new MemoryStream())
        {
            z.CopyTo(m);
            return m.ToArray();
        }
    }

    // runs: (offset in target, length) pairs, filled in order from data starting at offset.
    public static void ApplyRuns(byte[] target, long[] runs, byte[] data, long offset)
    {
        for (int i = 0; i + 1 < runs.Length; i += 2)
        {
            Array.Copy(data, offset, target, runs[i], runs[i + 1]);
            offset += runs[i + 1];
        }
    }
}
