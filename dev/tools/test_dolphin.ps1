# Run the test Dolphin hands-off: it starts on its own hidden Windows desktop, so its window never shows up on the
# screen and can't take focus; its only controller is the virtual DSU pad (dsu_pad.py), background input is on so
# it never needs focus, and the screenshot hotkey is the pad's PS button. Nothing goes through the real keyboard,
# mouse or screen, so the PC stays free for whoever is using it.
#
#   test_dolphin.ps1 start [-Image <main.dol or .iso>] [-Profile <user folder>] [-Dolphin <Dolphin.exe>]
#   test_dolphin.ps1 shot            take a screenshot, print its path (read it with any image viewer/tool)
#   test_dolphin.ps1 stop
#   test_dolphin.ps1 play [-Image ...]   start it on the normal desktop for a person to play (their own controller
#                                        mapping from their Dolphin, else keyboard controls)
#
# Drive it with: python -I dsu_pad.py press Cross / seq "Share 200; wait 3000; Cross 200" / stick L 0 1 300 ...
param(
	[Parameter(Mandatory, Position = 0)] [ValidateSet('start', 'shot', 'stop', 'play')] [string] $Action,
	[string] $Image = (Join-Path $PSScriptRoot '..\..\..\build\sys\main.dol'),
	[string] $Profile = (Join-Path $PSScriptRoot '..\..\..\mod\test-profile'),
	[string] $Dolphin = (Join-Path $PSScriptRoot '..\..\..\..\dolphin-2606a-x64\Dolphin-x64\Dolphin.exe')
)
$ErrorActionPreference = 'Stop'
$Profile = (Resolve-Path $Profile).Path
$config = Join-Path $Profile 'Config'
$pidFile = Join-Path $Profile 'pid.txt'
$pad = 'DSUClient/0/TestPad'
$pad2 = 'DSUClient/1/TestPad'
$desktopName = 'TTModTest'

function Set-Ini([string] $Path, [string] $Section, [hashtable] $Values) {
	$lines = [System.Collections.Generic.List[string]]::new()
	if (Test-Path $Path) { foreach ($l in @(Get-Content $Path)) { if ($null -ne $l) { $lines.Add($l) } } }
	$start = $lines.IndexOf("[$Section]")
	if ($start -lt 0) { $lines.Add("[$Section]"); $start = $lines.Count - 1 }
	foreach ($key in $Values.Keys) {
		$end = $start + 1
		while ($end -lt $lines.Count -and -not $lines[$end].StartsWith('[')) { $end++ }
		$found = $false
		for ($i = $start + 1; $i -lt $end; $i++) {
			if ($lines[$i] -match "^\s*$([regex]::Escape($key))\s*=") { $lines[$i] = "$key = $($Values[$key])"; $found = $true }
		}
		if (-not $found) { $lines.Insert($end, "$key = $($Values[$key])") }
	}
	Set-Content -Path $Path -Value $lines -Encoding ascii
}

# Dolphin puts its game window back where it last was (Qt.ini [renderwidget]), over the Dolphin.ini position.
function Clear-SavedWindow {
	$qt = Join-Path $config 'Qt.ini'
	if (-not (Test-Path $qt)) { return }
	$out = [System.Collections.Generic.List[string]]::new()
	$skip = $false
	foreach ($l in @(Get-Content $qt)) {
		if ($l -match '^\[') { $skip = $l -eq '[renderwidget]' }
		if (-not $skip) { $out.Add($l) }
	}
	Set-Content -Path $qt -Value $out -Encoding ascii
}

function Write-PadProfile([bool] $Virtual) {
	if ($Virtual) {
		$map = [ordered]@{
			'Device' = $pad; 'Buttons/A' = '`Cross`'; 'Buttons/B' = '`Circle`'; 'Buttons/X' = '`Square`'; 'Buttons/Y' = '`Triangle`'
			'Buttons/Z' = '`R1`'; 'Buttons/Start' = '`Share`'
			'Main Stick/Up' = '`Left Y+`'; 'Main Stick/Down' = '`Left Y-`'; 'Main Stick/Left' = '`Left X-`'; 'Main Stick/Right' = '`Left X+`'
			'C-Stick/Up' = '`Right Y+`'; 'C-Stick/Down' = '`Right Y-`'; 'C-Stick/Left' = '`Right X-`'; 'C-Stick/Right' = '`Right X+`'
			'Triggers/L' = '`L2`'; 'Triggers/R' = '`R2`'; 'Triggers/L-Analog' = '`L2`'; 'Triggers/R-Analog' = '`R2`'
			'D-Pad/Up' = '`Pad N`'; 'D-Pad/Down' = '`Pad S`'; 'D-Pad/Left' = '`Pad W`'; 'D-Pad/Right' = '`Pad E`'
		}
	}
	else {
		$map = [ordered]@{
			'Device' = 'DInput/0/Keyboard Mouse'; 'Buttons/A' = '`X`'; 'Buttons/B' = '`Z`'; 'Buttons/X' = '`C`'; 'Buttons/Y' = '`S`'
			'Buttons/Z' = '`D`'; 'Buttons/Start' = '`RETURN`'
			'Main Stick/Up' = '`UP`'; 'Main Stick/Down' = '`DOWN`'; 'Main Stick/Left' = '`LEFT`'; 'Main Stick/Right' = '`RIGHT`'
			'C-Stick/Up' = '`I`'; 'C-Stick/Down' = '`K`'; 'C-Stick/Left' = '`J`'; 'C-Stick/Right' = '`L`'
			'Triggers/L' = '`Q`'; 'Triggers/R' = '`W`'; 'Triggers/L-Analog' = ''; 'Triggers/R-Analog' = ''
			'D-Pad/Up' = '`T`'; 'D-Pad/Down' = '`G`'; 'D-Pad/Left' = '`F`'; 'D-Pad/Right' = '`H`'
		}
	}
	$lines = @('[GCPad1]') + ($map.Keys | ForEach-Object { "$_ = $($map[$_])" })
	if ($Virtual) {   # port 2: the second virtual pad (dsu_pad.py "p2 ..."), same buttons
		$map['Device'] = $pad2
		$lines += '[GCPad2]'; $lines += ($map.Keys | ForEach-Object { "$_ = $($map[$_])" })
		foreach ($n in 3..4) { $lines += "[GCPad$n]"; $lines += "Device = $pad" }
	}
	else { foreach ($n in 2..4) { $lines += "[GCPad$n]"; $lines += "Device = $($map['Device'])" } }
	Set-Content -Path (Join-Path $config 'GCPadNew.ini') -Value $lines -Encoding ascii
}

# For a person playing: the controller mapping from their own Dolphin when port 1 there is a controller (it's
# copied into the test profile; their Dolphin is left alone). Returns the device, or nothing for the keyboard keys.
function Use-PlayerPad {
	$own = @((Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Dolphin Emulator\Config\GCPadNew.ini'),
		(Join-Path $env:APPDATA 'Dolphin Emulator\Config\GCPadNew.ini')) | Where-Object { Test-Path $_ } | Select-Object -First 1
	if (-not $own) { return }
	$device = @(Get-Content $own | Where-Object { $_ -match '^Device = ' })[0] -replace '^Device = ', ''
	if (-not $device -or $device -like '*Keyboard*') { return }
	Copy-Item $own (Join-Path $config 'GCPadNew.ini') -Force
	$device
}

Add-Type -Namespace TT -Name Desk -MemberDefinition @'
[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
public struct STARTUPINFO {
	public int cb; public string lpReserved; public string lpDesktop; public string lpTitle;
	public int dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars, dwFillAttribute, dwFlags;
	public short wShowWindow, cbReserved2; public IntPtr lpReserved2, hStdInput, hStdOutput, hStdError;
}
[StructLayout(LayoutKind.Sequential)]
public struct PROCESS_INFORMATION { public IntPtr hProcess, hThread; public int dwProcessId, dwThreadId; }
[DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
public static extern IntPtr CreateDesktop(string name, IntPtr device, IntPtr devmode, int flags, uint access, IntPtr sa);
[DllImport("user32.dll")] public static extern bool CloseDesktop(IntPtr h);
[DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
public static extern bool CreateProcess(string app, System.Text.StringBuilder cmd, IntPtr pa, IntPtr ta, bool inherit,
	uint flags, IntPtr env, string dir, ref STARTUPINFO si, out PROCESS_INFORMATION pi);
[DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr h);
[DllImport("user32.dll")] public static extern uint WaitForInputIdle(IntPtr process, uint ms);

// Start a program on another desktop of this window station: its windows are never on the user's screen.
public static int StartOnDesktop(string desktop, string exe, string args, string dir) {
	IntPtr d = CreateDesktop(desktop, IntPtr.Zero, IntPtr.Zero, 0, 0x10000000, IntPtr.Zero);  // GENERIC_ALL
	if (d == IntPtr.Zero) throw new System.ComponentModel.Win32Exception();
	try {
		STARTUPINFO si = new STARTUPINFO();
		si.cb = Marshal.SizeOf(typeof(STARTUPINFO));
		si.lpDesktop = "WinSta0\\" + desktop;
		PROCESS_INFORMATION pi;
		System.Text.StringBuilder cmd = new System.Text.StringBuilder("\"" + exe + "\" " + args);
		if (!CreateProcess(exe, cmd, IntPtr.Zero, IntPtr.Zero, false, 0, IntPtr.Zero, dir, ref si, out pi))
			throw new System.ComponentModel.Win32Exception();
		WaitForInputIdle(pi.hProcess, 20000);  // until Dolphin is on the desktop; closing it sooner would end it
		CloseHandle(pi.hThread);
		CloseHandle(pi.hProcess);
		return pi.dwProcessId;
	}
	finally { CloseDesktop(d); }  // from here on the desktop lives as long as Dolphin runs on it
}
'@

function Stop-Test {
	if (Test-Path $pidFile) {
		$p = Get-Process -Id ([int](Get-Content $pidFile)) -ErrorAction SilentlyContinue
		if ($p -and $p.ProcessName -eq 'Dolphin') { Stop-Process -Id $p.Id -Force; "stopped test Dolphin $($p.Id)" }
	}
}

switch ($Action) {
	'stop' { Stop-Test }
	'play' {
		Stop-Test
		Clear-SavedWindow
		Write-PadProfile $false
		$device = Use-PlayerPad
		Set-Ini (Join-Path $config 'Dolphin.ini') 'Input' @{ BackgroundInput = 'False' }
		Set-Ini (Join-Path $config 'Dolphin.ini') 'General' @{ HotkeysRequireFocus = 'True' }
		Set-Ini (Join-Path $config 'Dolphin.ini') 'Core' @{ SIDevice1 = '0' }   # one controller
		Set-Ini (Join-Path $config 'Dolphin.ini') 'Display' @{ RenderWindowXPos = '100'; RenderWindowYPos = '100' }
		$p = Start-Process -FilePath $Dolphin -ArgumentList '-u', "`"$Profile`"", '-b', '-e', "`"$((Resolve-Path $Image).Path)`"" -PassThru
		$p.Id | Set-Content $pidFile
		if ($device) { "test Dolphin $($p.Id) on $Image (your controller: $device)" }
		else { "test Dolphin $($p.Id) on $Image (keyboard: x = A, z = B, c = X, s = Y, d = Z, arrows, Enter = Start)" }
	}
	'start' {
		Stop-Test
		Clear-SavedWindow
		Set-Ini (Join-Path $config 'DSUClient.ini') 'Server' @{ Enabled = 'True'; Entries = 'TestPad:127.0.0.1:26760;' }
		Set-Ini (Join-Path $config 'Dolphin.ini') 'Input' @{ BackgroundInput = 'True' }
		Set-Ini (Join-Path $config 'Dolphin.ini') 'Interface' @{ PauseOnFocusLost = 'False'; ConfirmStop = 'False' }
		Set-Ini (Join-Path $config 'Dolphin.ini') 'General' @{ HotkeysRequireFocus = 'False' }   # the screenshot key
		Set-Ini (Join-Path $config 'Dolphin.ini') 'Core' @{ SIDevice1 = '6' }   # port 2: the second virtual pad
		Set-Ini (Join-Path $config 'Dolphin.ini') 'Display' @{
			Fullscreen = 'False'; RenderToMain = 'False'; KeepWindowOnTop = 'False'; RenderWindowAutoSize = 'False'
			RenderWindowXPos = '0'; RenderWindowYPos = '0'; RenderWindowWidth = '960'; RenderWindowHeight = '540'
		}
		Set-Ini (Join-Path $config 'Hotkeys.ini') 'Hotkeys' @{ Device = $pad; 'General/Take Screenshot' = '`PS`' }
		Write-PadProfile $true
		$listening = Get-NetUDPEndpoint -LocalAddress 127.0.0.1 -LocalPort 26760 -ErrorAction SilentlyContinue
		if (-not $listening) {
			Start-Process -FilePath python -ArgumentList '-I', "`"$(Join-Path $PSScriptRoot 'dsu_pad.py')`"", 'serve' -WindowStyle Hidden
			Start-Sleep -Milliseconds 800
		}
		$exe = (Resolve-Path $Dolphin).Path
		$cmdArgs = "-u `"$Profile`" -b -e `"$((Resolve-Path $Image).Path)`""
		$id = [TT.Desk]::StartOnDesktop($desktopName, $exe, $cmdArgs, (Split-Path $exe))
		$id | Set-Content $pidFile
		"test Dolphin $id on $Image (hidden desktop '$desktopName', hands-off)"
	}
	'shot' {
		$dir = Join-Path $Profile 'ScreenShots'
		$last = Get-ChildItem $dir -Recurse -Filter *.png -ErrorAction SilentlyContinue | Where-Object Name -NotLike '*.small.png' | Sort-Object LastWriteTime | Select-Object -Last 1
		python -I (Join-Path $PSScriptRoot 'dsu_pad.py') press PS 120 | Out-Null
		for ($i = 0; $i -lt 30; $i++) {
			Start-Sleep -Milliseconds 200
			$new = Get-ChildItem $dir -Recurse -Filter *.png -ErrorAction SilentlyContinue | Where-Object Name -NotLike '*.small.png' | Sort-Object LastWriteTime | Select-Object -Last 1
			if ($new -and (-not $last -or $new.FullName -ne $last.FullName -or $new.LastWriteTime -gt $last.LastWriteTime)) {
				Start-Sleep -Milliseconds 300   # let Dolphin finish writing it
				$small = $new.FullName -replace '\.png$', '.small.png'   # 960 wide copy, quicker to look at
				python -I -c "from PIL import Image; im = Image.open(r'$($new.FullName)'); im.thumbnail((960, 960)); im.save(r'$small')" 2>$null
				if (Test-Path $small) { $small } else { $new.FullName }
				return
			}
		}
		throw 'no screenshot appeared'
	}
}
