# Bring the test Dolphin's game window to the front by process id; prints every visible window it owns.
param([int]$ProcessId = 0)
. "$PSScriptRoot\gcmem.ps1"
if (-not $ProcessId) { $ProcessId = Get-TestPid }
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class Win {
	delegate bool EnumProc(IntPtr h, IntPtr l);
	[DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f, IntPtr l);
	[DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
	[DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
	[DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
	[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
	[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
	public static List<KeyValuePair<IntPtr, string>> Windows(uint pid) {
		var r = new List<KeyValuePair<IntPtr, string>>();
		EnumWindows((h, l) => {
			uint p; GetWindowThreadProcessId(h, out p);
			if (p == pid && IsWindowVisible(h)) { var s = new StringBuilder(256); GetWindowText(h, s, 256); r.Add(new KeyValuePair<IntPtr, string>(h, s.ToString())); }
			return true;
		}, IntPtr.Zero);
		return r;
	}
}
'@
$wins = [Win]::Windows([uint32]$ProcessId)
$wins | ForEach-Object { "window: $($_.Value)" }
$game = $wins | Where-Object { $_.Value -match 'GFTEMD|Mario Golf' } | Select-Object -First 1
if ($game) { [Win]::ShowWindow($game.Key, 3) | Out-Null; "foreground: $([Win]::SetForegroundWindow($game.Key))" } else { "no game window" }

