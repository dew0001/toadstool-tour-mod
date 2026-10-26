# Run the test Dolphin hands-off: its only controller is the virtual DSU pad (dsu_pad.py), background input is on
# so it never needs focus, the screenshot hotkey is the pad's PS button, and its window sits off-screen. Nothing
# goes through the real keyboard, mouse or screen, so the PC stays free for whoever is using it.
#
#   test_dolphin.ps1 start [-Image <main.dol or .iso>] [-Profile <user folder>] [-Dolphin <Dolphin.exe>]
#   test_dolphin.ps1 shot            take a screenshot, print its path (read it with any image viewer/tool)
#   test_dolphin.ps1 stop
#   test_dolphin.ps1 keyboard        switch the profile back to keyboard play in a normal window (to hand it over)
#
# Drive it with: python -I dsu_pad.py press Cross / seq "Share 200; wait 3000; Cross 200" / stick L 0 1 300 ...
param(
	[Parameter(Mandatory, Position = 0)] [ValidateSet('start', 'shot', 'stop', 'keyboard')] [string] $Action,
	[string] $Image = (Join-Path $PSScriptRoot '..\..\..\build\sys\main.dol'),
	[string] $Profile = (Join-Path $PSScriptRoot '..\..\..\mod\test-profile'),
	[string] $Dolphin = (Join-Path $PSScriptRoot '..\..\..\..\dolphin-2606a-x64\Dolphin-x64\Dolphin.exe')
)
$ErrorActionPreference = 'Stop'
$Profile = (Resolve-Path $Profile).Path
$config = Join-Path $Profile 'Config'
$pidFile = Join-Path $Profile 'pid.txt'
$pad = 'DSUClient/0/TestPad'

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
	foreach ($n in 2..4) { $lines += "[GCPad$n]"; $lines += "Device = $($map['Device'])" }
	Set-Content -Path (Join-Path $config 'GCPadNew.ini') -Value $lines -Encoding ascii
}

Add-Type -Namespace TT -Name Win -MemberDefinition @'
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
[DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
[DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
'@

function Stop-Test {
	if (Test-Path $pidFile) {
		$p = Get-Process -Id ([int](Get-Content $pidFile)) -ErrorAction SilentlyContinue
		if ($p -and $p.ProcessName -eq 'Dolphin') { Stop-Process -Id $p.Id -Force; "stopped test Dolphin $($p.Id)" }
	}
}

switch ($Action) {
	'stop' { Stop-Test }
	'keyboard' {
		Write-PadProfile $false
		Set-Ini (Join-Path $config 'Dolphin.ini') 'Input' @{ BackgroundInput = 'False' }
		Set-Ini (Join-Path $config 'Dolphin.ini') 'Display' @{ RenderWindowXPos = '100'; RenderWindowYPos = '100' }
		'keyboard play, normal window (takes effect on the next start)'
	}
	'start' {
		Stop-Test
		Set-Ini (Join-Path $config 'DSUClient.ini') 'Server' @{ Enabled = 'True'; Entries = 'TestPad:127.0.0.1:26760;' }
		Set-Ini (Join-Path $config 'Dolphin.ini') 'Input' @{ BackgroundInput = 'True' }
		Set-Ini (Join-Path $config 'Dolphin.ini') 'Interface' @{ PauseOnFocusLost = 'False'; ConfirmStop = 'False' }
		Set-Ini (Join-Path $config 'Dolphin.ini') 'Display' @{
			Fullscreen = 'False'; RenderToMain = 'False'; KeepWindowOnTop = 'False'; RenderWindowAutoSize = 'False'
			RenderWindowXPos = '-4000'; RenderWindowYPos = '200'; RenderWindowWidth = '960'; RenderWindowHeight = '540'
		}
		Set-Ini (Join-Path $config 'Hotkeys.ini') 'Hotkeys' @{ Device = $pad; 'General/Take Screenshot' = '`PS`' }
		Write-PadProfile $true
		$listening = Get-NetUDPEndpoint -LocalAddress 127.0.0.1 -LocalPort 26760 -ErrorAction SilentlyContinue
		if (-not $listening) {
			Start-Process -FilePath python -ArgumentList '-I', "`"$(Join-Path $PSScriptRoot 'dsu_pad.py')`"", 'serve' -WindowStyle Hidden
			Start-Sleep -Milliseconds 800
		}
		$before = [TT.Win]::GetForegroundWindow()
		$p = Start-Process -FilePath $Dolphin -ArgumentList '-u', "`"$Profile`"", '-b', '-e', "`"$((Resolve-Path $Image).Path)`"" -PassThru
		$p.Id | Set-Content $pidFile
		for ($i = 0; $i -lt 50; $i++) {   # put focus back where it was as soon as Dolphin's window shows up
			Start-Sleep -Milliseconds 200
			$p.Refresh()
			if ($p.MainWindowHandle -ne [IntPtr]::Zero) { break }
		}
		[TT.Win]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero); [TT.Win]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)  # Alt tap lets us hand focus back
		[TT.Win]::SetForegroundWindow($before) | Out-Null
		"test Dolphin $($p.Id) on $Image (hands-off)"
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
