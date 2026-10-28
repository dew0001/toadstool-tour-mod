# Toadstool Tour Mod - shared helpers for Play (friends) and publish (maintainer).
# Windows PowerShell 5.1 compatible.

function Import-TTMod {
	if (-not ('TTMod' -as [type])) {
		Add-Type -TypeDefinition (Get-Content -Raw (Join-Path $PSScriptRoot 'TTMod.cs'))
	}
	[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072
}

function Find-DolphinUserDir($exe) {
	# Same order Dolphin uses on Windows: a portable Dolphin (portable.txt next to Dolphin.exe, or the registry's
	# LocalUserConfig) keeps its settings in the User folder next to Dolphin.exe; then the registry's UserConfigPath,
	# the legacy Documents folder, then AppData.
	$reg = Get-ItemProperty -Path 'HKCU:\Software\Dolphin Emulator' -ErrorAction SilentlyContinue
	if ($exe -and (Test-Path $exe)) {
		$exeDir = Split-Path $exe
		if ((Test-Path (Join-Path $exeDir 'portable.txt')) -or ($reg -and $reg.LocalUserConfig)) { return Join-Path $exeDir 'User' }
	}
	if ($reg -and $reg.UserConfigPath -and (Test-Path $reg.UserConfigPath)) { return $reg.UserConfigPath }
	$docs = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Dolphin Emulator'
	if (Test-Path $docs) { return $docs }
	$appdata = Join-Path $env:APPDATA 'Dolphin Emulator'
	if (Test-Path $appdata) { return $appdata }
	return $null
}

# Folders Dolphin lists games from (Options > Configuration > Paths), and whether to search subfolders.
function Get-DolphinGameFolders($userDir) {
	$ini = Join-Path $userDir 'Config\Dolphin.ini'
	$folders = @()
	$recursive = $false
	if (Test-Path $ini) {
		foreach ($line in Get-Content $ini) {
			if ($line -match '^\s*ISOPath\d+\s*=\s*(.+?)\s*$') { $folders += ($Matches[1] -replace '/', '\') }
			if ($line -match '^\s*RecursiveISOPaths\s*=\s*True') { $recursive = $true }
		}
	}
	return @{ Folders = @($folders | Where-Object { Test-Path $_ }); Recursive = $recursive }
}

# Dolphin.exe has no version resource, but its title string "Dolphin 2606a" is in the program file.
function Get-DolphinVersion($exe) {
	if (-not $exe -or -not (Test-Path $exe)) { return $null }
	$text = [Text.Encoding]::GetEncoding(28591).GetString([IO.File]::ReadAllBytes($exe))
	$m = [regex]::Match($text, 'Dolphin (\d{4}[a-z]?(?:-\d+)?)\x00')
	if ($m.Success) { return $m.Groups[1].Value }
	return $null
}

# Dolphin.exe: a running Dolphin, the usual install folders, then Windows' own record of programs that have
# run (a portable Dolphin lives wherever it was unzipped). Prefers the group's Dolphin version when given.
function Find-DolphinExe($wantVersion) {
	$found = @(Get-Process Dolphin -ErrorAction SilentlyContinue | Where-Object { $_.Path } | ForEach-Object { $_.Path })
	$found += @((Join-Path $env:ProgramFiles 'Dolphin-x64\Dolphin.exe'), (Join-Path $env:ProgramFiles 'Dolphin\Dolphin.exe'))
	$mui = 'HKCU:\Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\MuiCache'
	if (Test-Path $mui) {
		$found += @((Get-Item $mui).Property | Where-Object { $_ -match '\\Dolphin\.exe\.FriendlyAppName$' } | ForEach-Object { $_ -replace '\.FriendlyAppName$', '' })
	}
	$store = 'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Compatibility Assistant\Store'
	if (Test-Path $store) { $found += @((Get-Item $store).Property | Where-Object { $_ -match '\\Dolphin\.exe$' }) }
	$found = @($found | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique)
	if ($wantVersion) {
		$match = $found | Where-Object { (Get-DolphinVersion $_) -eq $wantVersion } | Select-Object -First 1
		if ($match) { return $match }
	}
	return $found | Select-Object -First 1
}

function Test-CleanGame($path) {
	try {
		$s = [TTMod]::Open($path)
		try { return ([TTMod]::GameId($s) -eq 'GFTE01-rev0') } finally { $s.Dispose() }
	}
	catch { return $false }
}

function Find-CleanGame($userDir) {
	$where = Get-DolphinGameFolders $userDir
	foreach ($folder in $where.Folders) {
		$files = if ($where.Recursive) { Get-ChildItem -Path $folder -File -Recurse -ErrorAction SilentlyContinue } else { Get-ChildItem -Path $folder -File -ErrorAction SilentlyContinue }
		foreach ($f in $files) {
			if ($f.Extension -match '^\.(iso|gcm|ciso)$' -and $f.Length -gt 100MB -and (Test-CleanGame $f.FullName)) { return $f.FullName }
		}
	}
	return $null
}

function Pick-File($title, $filter) {
	Add-Type -AssemblyName System.Windows.Forms
	$dlg = New-Object System.Windows.Forms.OpenFileDialog
	$dlg.Title = $title
	$dlg.Filter = $filter
	if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { return $dlg.FileName }
	return $null
}

# ---- Dolphin INI editing (keeps every other line as it was)

function Read-IniSection($path, $section) {
	$values = [ordered]@{}
	if (-not (Test-Path $path)) { return $values }
	$inside = $false
	foreach ($line in Get-Content $path) {
		if ($line -match '^\s*\[(.+)\]\s*$') { $inside = ($Matches[1] -eq $section); continue }
		if ($inside -and $line -match '^\s*([^#;=][^=]*?)\s*=\s*(.*?)\s*$') { $values[$Matches[1]] = $Matches[2] }
	}
	return $values
}

function Set-IniValues($path, $section, $values) {
	$lines = New-Object System.Collections.Generic.List[string]
	if (Test-Path $path) { foreach ($l in Get-Content $path) { $lines.Add($l) } }
	$start = -1
	for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i] -match "^\s*\[$([regex]::Escape($section))\]\s*$") { $start = $i; break } }
	if ($start -lt 0) {
		if ($lines.Count -and $lines[$lines.Count - 1] -ne '') { $lines.Add('') }
		$lines.Add("[$section]"); $start = $lines.Count - 1
	}
	$end = $lines.Count
	for ($i = $start + 1; $i -lt $lines.Count; $i++) { if ($lines[$i] -match '^\s*\[.+\]\s*$') { $end = $i; break } }
	foreach ($key in $values.Keys) {
		$set = "$key = $($values[$key])"
		$found = $false
		for ($i = $start + 1; $i -lt $end; $i++) {
			if ($lines[$i] -match "^\s*$([regex]::Escape($key))\s*=") { $lines[$i] = $set; $found = $true; break }
		}
		if (-not $found) {
			$at = $end
			while ($at -gt $start + 1 -and $lines[$at - 1] -eq '') { $at-- }
			$lines.Insert($at, $set); $end++
		}
	}
	New-Item -ItemType Directory -Force (Split-Path $path) | Out-Null
	[IO.File]::WriteAllLines($path, $lines)
}

# ---- Controller layout for the mod, the same on every controller
# LB/RB pick clubs, LT/RT switch views, left stick left/right aims and up/down sets the power (up moves the
# landing spot farther: the game's analog L, down closer: its analog R), right stick left/right still turns the
# camera and up/down also sets the power, View/Back gives side views (the game's Z). The sticks drive the game's
# analog L/R, so the landing spot moves faster the further you tilt; a 25% dead zone keeps aiming from nudging
# it. Clicking a stick in is the game's L or R button (lefty and Star on the character select screen).
# v12: the layout no longer depends on the player's Port 1 setup, which could name a controller that isn't plugged
# in (then nothing worked). Every binding names each controller Dolphin may see: XInput (Xbox controllers, most PC
# pads, and PlayStation/Switch controllers through Steam or DS4Windows) and SDL (Dolphin's default, any controller
# SDL knows, buttons by position: Xbox A = PlayStation Cross = Switch B). Whichever is plugged in works.
# v14 (app 8): friends' controllers still misbehaved, so the layout is forced harder: all four XInput slots and the
# second of each SDL model too (a virtual pad from Steam or DS4Windows can take the first), every XInput/SDL
# controller the player's own Dolphin settings name, a non-Xbox-style Port 1 controller keeps its own buttons
# alongside, Port 1 is a Standard Controller for the modded game, and Play rewrites it all on every run.
$ModLayoutVersion = 5
$ModProfileName = 'Toadstool Tour Mod'
$ModLayout = [ordered]@{   # face buttons by position (A south, B east, X west, Y north); both stick dialects use the rest
	'Buttons/A'         = 'A'
	'Buttons/B'         = 'B'
	'Buttons/X'         = 'X'
	'Buttons/Y'         = 'Y'
	'Buttons/Z'         = 'Back'
	'Buttons/Start'     = 'Start'
	'Main Stick/Up'     = 'Shoulder R'
	'Main Stick/Down'   = 'Shoulder L'
	'Main Stick/Left'   = 'Left X-'
	'Main Stick/Right'  = 'Left X+'
	'C-Stick/Up'        = 'Trigger R'
	'C-Stick/Down'      = 'Trigger L'
	'C-Stick/Left'      = 'Right X-'
	'C-Stick/Right'     = 'Right X+'
	'Triggers/L'        = 'Thumb L'   # pressed L/R also push the analog all the way (Dolphin), as a GameCube's do
	'Triggers/R'        = 'Thumb R'
	'Triggers/L-Analog' = 'Left Y+', 'Right Y+'   # stick up (Y+ is up in both dialects): landing spot farther
	'Triggers/R-Analog' = 'Left Y-', 'Right Y-'   # stick down: closer
	'D-Pad/Up'          = 'Pad N'
	'D-Pad/Down'        = 'Pad S'
	'D-Pad/Left'        = 'Pad W'
	'D-Pad/Right'       = 'Pad E'
}
$ModFaceNames = @{
	'XInput' = @{ 'A' = 'Button A'; 'B' = 'Button B'; 'X' = 'Button X'; 'Y' = 'Button Y' }
	'SDL'    = @{ 'A' = 'Button S'; 'B' = 'Button E'; 'X' = 'Button W'; 'Y' = 'Button N' }
}
# SDL names controllers by model (SDL/0/<name> is the first of that model); these are the ones SDL itself names.
$ModSdlNames = 'Xbox 360 Controller', 'Xbox 360 Wireless Controller', 'Xbox One Controller', 'Xbox One S Controller',
	'Xbox One Elite Controller', 'Xbox One Elite 2 Controller', 'Xbox Series X Controller', 'Xbox Adaptive Controller',
	'PS3 Controller', 'PS4 Controller', 'PS5 Controller', 'DualSense Wireless Controller',
	'DualSense Edge Wireless Controller', 'Nintendo Switch Pro Controller', 'Steam Controller'
# Dolphin's own keyboard layout for Port 1, for players without a GCPadNew.ini (Dolphin then uses these).
$DolphinKeyboardDefaults = [ordered]@{
	'Buttons/A' = '`X`'; 'Buttons/B' = '`Z`'; 'Buttons/X' = '`C`'; 'Buttons/Y' = '`S`'; 'Buttons/Z' = '`D`'
	'Buttons/Start' = '`RETURN`'; 'Main Stick/Up' = '`UP`'; 'Main Stick/Down' = '`DOWN`'; 'Main Stick/Left' = '`LEFT`'
	'Main Stick/Right' = '`RIGHT`'; 'Main Stick/Modifier' = '`LSHIFT`'; 'C-Stick/Up' = '`I`'; 'C-Stick/Down' = '`K`'
	'C-Stick/Left' = '`J`'; 'C-Stick/Right' = '`L`'; 'C-Stick/Modifier' = '`LCONTROL`'; 'Triggers/L' = '`Q`'
	'Triggers/R' = '`W`'; 'D-Pad/Up' = '`T`'; 'D-Pad/Down' = '`G`'; 'D-Pad/Left' = '`F`'; 'D-Pad/Right' = '`H`'
}

# Every XInput/SDL controller named anywhere in the player's Dolphin controller settings (any port, any profile but
# the mod's), e.g. an 8BitDo pad SDL names by its own model.
function Get-DolphinPads($userDir) {
	if (-not $userDir) { return @() }
	$files = @((Join-Path $userDir 'Config\GCPadNew.ini'), (Join-Path $userDir 'Config\WiimoteNew.ini'))
	$files += @(Get-ChildItem (Join-Path $userDir 'Config\Profiles') -Recurse -Filter '*.ini' -ErrorAction SilentlyContinue |
		Where-Object { $_.BaseName -ne $ModProfileName } | ForEach-Object { $_.FullName })
	$found = foreach ($f in $files) {
		if (Test-Path $f) { [regex]::Matches([IO.File]::ReadAllText($f), '(?:SDL|XInput)/\d+/[^`:\r\n|&()]+') | ForEach-Object { $_.Value.Trim() } }
	}
	return @($found | Where-Object { $_ } | Select-Object -Unique)
}

# The controllers the mod's bindings name: XInput's first and every SDL model above, the player's own Port 1
# controller when it's another XInput/SDL one, then the other XInput slots, the second of each SDL model and every
# XInput/SDL controller the player's Dolphin settings name, less any that Ports 2-4 use (two players on one PC).
function Get-ModPads($device, $userDir) {
	$pads = @('XInput/0/Gamepad') + @($ModSdlNames | ForEach-Object { "SDL/0/$_" })
	if ($device -match '^(SDL|XInput)/\d+/[^:]+$' -and $pads -notcontains $device) { $pads += $device }
	$more = @(1..3 | ForEach-Object { "XInput/$_/Gamepad" }) + @($ModSdlNames | ForEach-Object { "SDL/1/$_" }) + @(Get-DolphinPads $userDir)
	$taken = @()
	if ($userDir) {
		$core = Read-IniSection (Join-Path $userDir 'Config\Dolphin.ini') 'Core'
		foreach ($n in 2..4) {
			if ($core["SIDevice$($n - 1)"] -and $core["SIDevice$($n - 1)"] -ne '0') {
				$port = Read-IniSection (Join-Path $userDir 'Config\GCPadNew.ini') "GCPad$n"
				$text = ($port.Keys | ForEach-Object { $port[$_] }) -join "`n"
				$taken += @([regex]::Matches($text, '(?:SDL|XInput)/\d+/[^`:\r\n|&()]+') | ForEach-Object { $_.Value.Trim() })
			}
		}
	}
	foreach ($d in $more) { if ($pads -notcontains $d -and $taken -notcontains $d) { $pads += $d } }
	return $pads
}

# One control on every mod controller: `XInput/0/Gamepad:Button A` | `SDL/0/PS4 Controller:Button S` | ...
function Get-ModBinding($names, $pads) {
	$parts = foreach ($d in $pads) {
		$dialect = $d -replace '/.*$', ''
		foreach ($n in @($names)) {
			$name = if ($ModFaceNames[$dialect].ContainsKey($n)) { $ModFaceNames[$dialect][$n] } else { $n }
			"``$($d):$name``"
		}
	}
	return $parts -join ' | '
}

# Writes the mod's Dolphin controller profile and tells Dolphin to use it on Port 1, as a Standard Controller, for
# the modded game only (a GameCube controller adapter on Port 1 stays one). A Port 1 controller that isn't an
# XInput/SDL one (a keyboard, or a DirectInput pad whose buttons go by number) keeps its own bindings alongside (or
# Dolphin's keys, without a GCPadNew.ini); an XInput/SDL one's own bindings are left out, so they can't fight the
# layout. Returns a short status for the player, or nothing when it was all in place already.
function Install-ModControllerProfile($userDir, $gameIni) {
	$pad = Read-IniSection (Join-Path $userDir 'Config\GCPadNew.ini') 'GCPad1'
	if (-not $pad['Device']) {
		$pad = [ordered]@{ 'Device' = 'DInput/0/Keyboard Mouse' }
		foreach ($k in $DolphinKeyboardDefaults.Keys) { $pad[$k] = $DolphinKeyboardDefaults[$k] }
	}
	$keyboard = $pad['Device'] -like '*/Keyboard Mouse'
	$own = $pad['Device'] -notmatch '^(SDL|XInput)/'
	$pads = Get-ModPads $pad['Device'] $userDir
	$lines = New-Object System.Collections.Generic.List[string]
	$lines.Add('[Profile]')
	$lines.Add("Device = $(if ($own) { $pad['Device'] } else { $pads[0] })")
	if ($own) {
		foreach ($k in $pad.Keys) {
			if ($k -notin 'Device', 'Triggers/Dead Zone' -and -not $ModLayout.Contains($k)) { $lines.Add("$k = $($pad[$k])") }
		}
	}
	foreach ($k in $ModLayout.Keys) {
		$expr = Get-ModBinding $ModLayout[$k] $pads
		if ($own -and $pad[$k]) { $expr = "($($pad[$k])) | $expr" }
		$lines.Add("$k = $expr")
	}
	$lines.Add('Triggers/Dead Zone = 25.000000000000000')
	$profile = Join-Path $userDir "Config\Profiles\GCPad\$ModProfileName.ini"
	$before = if (Test-Path $profile) { [IO.File]::ReadAllText($profile) } else { '' }
	$was = (Read-IniSection $gameIni 'Controls')['PadProfile1'], (Read-IniSection $gameIni 'Core')['SIDevice0']
	New-Item -ItemType Directory -Force (Split-Path $profile) | Out-Null
	[IO.File]::WriteAllLines($profile, $lines)
	Set-IniValues $gameIni 'Controls' ([ordered]@{ 'PadProfile1' = $ModProfileName })
	# 6 = Standard Controller, 12 = GameCube controller adapter (real GameCube controllers; no mapping to set)
	$port = if ((Read-IniSection (Join-Path $userDir 'Config\Dolphin.ini') 'Core')['SIDevice0'] -eq '12') { '12' } else { '6' }
	Set-IniValues $gameIni 'Core' ([ordered]@{ 'SIDevice0' = $port })
	if ($before -eq [IO.File]::ReadAllText($profile) -and $was[0] -eq $ModProfileName -and $was[1] -eq $port) { return }
	$also = if ($keyboard) { ' Your keyboard keys work too.' } elseif ($own) { " Your controller's own buttons work too." } else { '' }
	return "Mod controls set for any Xbox, PlayStation or Switch controller: LB/RB clubs, LT/RT views, left stick aims and sets power, click a stick for lefty (left) or Star (right) on the character screen.$also"
}

# ---- Hotkeys for the mod. Fullscreen is Dolphin's, not the game's, so it's switched by a Dolphin hotkey: Alt+Enter
# and, with an Xbox/PlayStation-style controller, clicking both sticks in (the GameCube has no stick buttons, so
# the game never sees them). Esc no longer stops the game: Dolphin left fullscreen to ask "stop?"; Stop is
# Shift+Esc. Dolphin's Hotkeys.ini is shared by every game, so only those two change, and only while they're still
# Dolphin's own (or ours); a missing file is first written with Dolphin's built-in set (HotkeyManager::LoadDefaults,
# Windows), since Dolphin leaves any hotkey the file doesn't list unbound.
$ModHotkeysVersion = 3   # v3: the fullscreen click on every controller Get-ModPads names (app 8)
$DolphinStop = 'ESCAPE'
$ModStop = '@(Shift+ESCAPE)'
$DolphinFullscreen = '@(Alt+RETURN)'
$DolphinHotkeyDefaults = [ordered]@{
	'General/Open' = '@(Ctrl+O)'
	'General/Toggle Pause' = 'F10'
	'General/Stop' = $DolphinStop
	'General/Toggle Fullscreen' = $DolphinFullscreen
	'General/Take Screenshot' = 'F9'
	'General/Open Achievements' = '@(Alt+A)'
	'Emulation Speed/Disable Emulation Speed Limit' = 'TAB'
	'Stepping/Step Into' = 'F11'
	'Stepping/Step Over' = '@(Shift+F10)'
	'Stepping/Step Out' = '@(Shift+F11)'
	'Breakpoint/Toggle Breakpoint' = '@(Shift+F9)'
	'Wii/Connect Wii Remote 1' = '@(Alt+F5)'
	'Wii/Connect Wii Remote 2' = '@(Alt+F6)'
	'Wii/Connect Wii Remote 3' = '@(Alt+F7)'
	'Wii/Connect Wii Remote 4' = '@(Alt+F8)'
	'Wii/Connect Balance Board' = '@(Alt+F9)'
	'Other State Hotkeys/Undo Load State' = 'F12'
	'Other State Hotkeys/Undo Save State' = '@(Shift+F12)'
	'GBA Core/Load ROM' = '@(`Ctrl`+`Shift`+`O`)'
	'GBA Core/Unload ROM' = '@(`Ctrl`+`Shift`+`W`)'
	'GBA Core/Reset' = '@(`Ctrl`+`Shift`+`R`)'
	'GBA Volume/Volume Down' = '`SUBTRACT`'
	'GBA Volume/Volume Up' = '`ADD`'
	'GBA Volume/Volume Toggle Mute' = '`M`'
	'GBA Window Size/1x' = '`NUMPAD1`'
	'GBA Window Size/2x' = '`NUMPAD2`'
	'GBA Window Size/3x' = '`NUMPAD3`'
	'GBA Window Size/4x' = '`NUMPAD4`'
	'USB Emulation Devices/Show Skylanders Portal' = '@(Ctrl+P)'
	'USB Emulation Devices/Show Infinity Base' = '@(Ctrl+I)'
}
foreach ($i in 1..8) {
	$DolphinHotkeyDefaults["Load State/Load State Slot $i"] = "F$i"
	$DolphinHotkeyDefaults["Save State/Save State Slot $i"] = "@(Shift+F$i)"
}

# Sets the mod's two hotkeys (see above). Returns a short status for the player.
function Install-ModHotkeys($userDir, $device) {
	$path = Join-Path $userDir 'Config\Hotkeys.ini'
	if (-not (Test-Path $path)) {
		$lines = New-Object System.Collections.Generic.List[string]
		$lines.Add('[Hotkeys]')
		$lines.Add('Device = DInput/0/Keyboard Mouse')
		foreach ($k in $DolphinHotkeyDefaults.Keys) { $lines.Add("$k = $($DolphinHotkeyDefaults[$k])") }
		New-Item -ItemType Directory -Force (Split-Path $path) | Out-Null
		[IO.File]::WriteAllLines($path, $lines)
	}
	$keys = Read-IniSection $path 'Hotkeys'
	$set = [ordered]@{}
	if ($keys['General/Stop'] -eq $DolphinStop) { $set['General/Stop'] = $ModStop }
	$full = $keys['General/Toggle Fullscreen']
	$ours = $full -eq $DolphinFullscreen -or $full -like "$DolphinFullscreen | (*Thumb L* & *Thumb R*)*"
	if ($ours) {   # v2: on every mod controller (Get-ModPads), not just the one Port 1 names
		$both = foreach ($d in (Get-ModPads $device $userDir)) { "(``$($d):Thumb L`` & ``$($d):Thumb R``)" }
		$set['General/Toggle Fullscreen'] = "$DolphinFullscreen | $($both -join ' | ')"
	}
	if ($set.Count) { Set-IniValues $path 'Hotkeys' $set }
	$how = if ($ours) { 'click both sticks in, or Alt+Enter' } else { $full }
	$stop = if ($keys['General/Stop'] -eq $DolphinStop -or $keys['General/Stop'] -eq $ModStop) { ' Stop the game: Shift+Esc.' } else { '' }
	return "Fullscreen on/off: $how.$stop"
}

# A patch's data file (from v11: the bytes of the files the game doesn't have), checked and unpacked; $null when the
# patch has none.
function Get-PatchData($patch, $file) {
	if ($null -eq $patch.data) { return $null }
	if ([TTMod]::Sha256File($file) -ne $patch.data.sha256) { throw 'The course data download was corrupted; try again.' }
	$bytes = [TTMod]::Gunzip($file)
	if ($bytes.Length -ne [long]$patch.data.size) { throw 'The course data download was corrupted; try again.' }
	return , $bytes
}

# Turn a patch (parsed JSON) and its data file's bytes into { disc path -> new bytes }, checking every result hash.
function Get-PatchChanges($src, $disc, $patch, $data) {
	$changed = New-Object 'System.Collections.Generic.Dictionary[string,byte[]]'
	foreach ($f in $patch.files) {
		if ($f.op -eq 'edit') {
			$orig = [TTMod]::ReadPart($src, $disc, $f.path)
			if ($f.compressed) { $work = [TTMod]::Decompress($orig) } else { $work = $orig }
			[long[]]$at = @($f.edits | ForEach-Object { [long]$_.at })
			[string[]]$hex = @($f.edits | ForEach-Object { [string]$_.hex })
			[TTMod]::ApplyEdits($work, $at, $hex)
			if ($f.compressed) { $new = [TTMod]::Pack([int]$f.type, $work) } else { $new = $work }
		}
		elseif ($f.op -eq 'rebuild') {
			# A compressed file that changes size and/or relocation table: runs of the original are moved (copies),
			# the mod's own bytes are written over them (edits), then it's packed again with its relocations.
			$basePath = $f.path
			if ($f.base) { $basePath = $f.base }   # built from another file of the game
			$orig = [TTMod]::ReadPart($src, $disc, $basePath)
			$base = [TTMod]::Decompress($orig)
			$work = [TTMod]::Resize($base, [long]$f.size)
			[long[]]$from = @($f.copies | ForEach-Object { [long]$_.from })
			[long[]]$to = @($f.copies | ForEach-Object { [long]$_.to })
			[long[]]$len = @($f.copies | ForEach-Object { [long]$_.len })
			[TTMod]::ApplyCopies($work, $base, $from, $to, $len)
			[long[]]$at = @($f.edits | ForEach-Object { [long]$_.at })
			[string[]]$hex = @($f.edits | ForEach-Object { [string]$_.hex })
			[TTMod]::ApplyEdits($work, $at, $hex)
			if ($null -ne $f.relocs) {
				$table = [TTMod]::Resize([TTMod]::Relocations($orig), 8 * [long]$f.relocs.count)
				[long[]]$at = @($f.relocs.edits | ForEach-Object { [long]$_.at })
				[string[]]$hex = @($f.relocs.edits | ForEach-Object { [string]$_.hex })
				[TTMod]::ApplyEdits($table, $at, $hex)
				$new = [TTMod]::Pack([int]$f.type, $work, $table)
			}
			else { $new = [TTMod]::Pack([int]$f.type, $work) }
		}
		elseif ($f.op -eq 'create') {
			# A file the game doesn't have (the 8th course): copies of runs from other game files (decoded), the
			# mod's own bytes over zeros, then packed with its relocation table. The disc build adds it to the
			# file table.
			$work = New-Object byte[] ([long]$f.size)
			$sources = @{}
			for ($i = 0; $i -lt @($f.sources).Count; $i++) {
				$raw = [TTMod]::ReadPart($src, $disc, @($f.sources)[$i])
				if ($raw[0] -eq 1 -or $raw[0] -eq 2) { $sources[$i] = [TTMod]::Decompress($raw) } else { $sources[$i] = $raw }
			}
			foreach ($group in @($f.copies | Group-Object src)) {
				[long[]]$from = @($group.Group | ForEach-Object { [long]$_.from })
				[long[]]$to = @($group.Group | ForEach-Object { [long]$_.to })
				[long[]]$len = @($group.Group | ForEach-Object { [long]$_.len })
				[TTMod]::ApplyCopies($work, $sources[[int]$group.Name], $from, $to, $len)
			}
			if ($null -ne $f.data) {   # its own bytes are in the patch's data file
				if ($null -eq $data) { throw "$($f.path): the patch's data file is missing" }
				[TTMod]::ApplyRuns($work, [long[]]@($f.data.runs), $data, [long]$f.data.offset)
			}
			else {
				[long[]]$at = @($f.edits | ForEach-Object { [long]$_.at })
				[string[]]$hex = @($f.edits | ForEach-Object { [string]$_.hex })
				[TTMod]::ApplyEdits($work, $at, $hex)
			}
			if (-not $f.compressed) { $new = $work }
			elseif ($null -ne $f.relocs) {
				$table = New-Object byte[] (8 * [long]$f.relocs.count)
				[long[]]$at = @($f.relocs.edits | ForEach-Object { [long]$_.at })
				[string[]]$hex = @($f.relocs.edits | ForEach-Object { [string]$_.hex })
				[TTMod]::ApplyEdits($table, $at, $hex)
				$new = [TTMod]::Pack([int]$f.type, $work, $table)
			}
			else { $new = [TTMod]::Pack([int]$f.type, $work) }
		}
		elseif ($f.op -eq 'replace') {
			$new = [Convert]::FromBase64String($f.data)  # the mod's own data, never the game's
		}
		else { throw "This mod version needs a newer Play.bat (unknown change type '$($f.op)')." }
		if ([TTMod]::Sha1($new) -ne $f.result_sha1) { throw "$($f.path) came out different from the official build." }
		$changed[$f.path] = $new
	}
	return , $changed
}

# Check a copy against the clean-game hash list; returns the names of files that differ.
function Compare-CleanManifest($src, $disc, $patch) {
	$man = [TTMod]::Manifest($src, $disc)
	$bad = @()
	foreach ($p in $patch.clean_manifest.psobject.Properties) {
		if (-not $man.ContainsKey($p.Name) -or $man[$p.Name] -ne $p.Value) { $bad += $p.Name }
	}
	return , $bad
}
