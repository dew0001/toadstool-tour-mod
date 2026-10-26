# Read GameCube RAM from a running Dolphin: . .\gcmem.ps1; $m = Open-GCMem <pid>; Read-GC32 $m 0x80000000
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class GCMem {
	[DllImport("kernel32.dll")] static extern IntPtr OpenProcess(int access, bool inherit, int pid);
	[DllImport("kernel32.dll")] static extern bool ReadProcessMemory(IntPtr h, IntPtr addr, byte[] buf, IntPtr size, out IntPtr read);
	[DllImport("kernel32.dll")] static extern bool WriteProcessMemory(IntPtr h, IntPtr addr, byte[] buf, IntPtr size, out IntPtr written);
	[DllImport("kernel32.dll")] static extern IntPtr VirtualQueryEx(IntPtr h, IntPtr addr, out MBI info, IntPtr len);
	[StructLayout(LayoutKind.Sequential)]
	public struct MBI { public IntPtr BaseAddress, AllocationBase; public uint AllocationProtect; public IntPtr RegionSize; public uint State, Protect, Type; }
	public static IntPtr Handle;
	public static long Base;
	public static string Open(int pid, string gameId) {
		Handle = OpenProcess(0x0438, false, pid);
		if (Handle == IntPtr.Zero) return "OpenProcess failed";
		long addr = 0;
		MBI m;
		int size = Marshal.SizeOf(typeof(MBI));
		while (VirtualQueryEx(Handle, new IntPtr(addr), out m, new IntPtr(size)) != IntPtr.Zero) {
			long rs = m.RegionSize.ToInt64();
			if (m.State == 0x1000 && rs >= 0x1800000 && (m.Protect & 0x04) != 0) {
				byte[] b = Read(m.BaseAddress.ToInt64(), 0x30);
				if (b != null && System.Text.Encoding.ASCII.GetString(b, 0, 6) == gameId && b[0x28] == 0x01 && b[0x29] == 0x80) {
					Base = m.BaseAddress.ToInt64();
					return "base 0x" + Base.ToString("X");
				}
			}
			addr = m.BaseAddress.ToInt64() + rs;
		}
		return "not found";
	}
	public static byte[] Read(long addr, int n) {
		byte[] b = new byte[n];
		IntPtr r;
		return ReadProcessMemory(Handle, new IntPtr(addr), b, new IntPtr(n), out r) ? b : null;
	}
	public static byte[] ReadGC(long gc, int n) { return Read(Base + ((gc & 0xFFFFFFFFL) - 0x80000000L), n); }
	public static uint U32(long gc) { byte[] b = ReadGC(gc, 4); return (uint)(b[0] << 24 | b[1] << 16 | b[2] << 8 | b[3]); }
	public static byte U8(long gc) { return ReadGC(gc, 1)[0]; }
	public static float F32(long gc) { byte[] b = ReadGC(gc, 4); Array.Reverse(b); return BitConverter.ToSingle(b, 0); }
	public static bool W32(long gc, uint v) { byte[] b = { (byte)(v >> 24), (byte)(v >> 16), (byte)(v >> 8), (byte)v }; IntPtr w; return WriteProcessMemory(Handle, new IntPtr(Base + ((gc & 0xFFFFFFFFL) - 0x80000000L)), b, new IntPtr(4), out w); }
}
'@



# The test Dolphin's process id: $env:TTMOD_PID, else the pid.txt next to the test profile
# (<folder above the repo>\mod\test-profile\pid.txt, written by whoever starts the test Dolphin).
function Get-TestPid {
	if ($env:TTMOD_PID) { return [int]$env:TTMOD_PID }
	[int](Get-Content (Join-Path $PSScriptRoot '..\..\..\mod\test-profile\pid.txt'))
}
