# Toadstool Tour Mod - shared helpers for Play (friends) and publish (maintainer).
# Windows PowerShell 5.1 compatible.

function Import-TTMod {
	if (-not ('TTMod' -as [type])) {
		Add-Type -TypeDefinition (Get-Content -Raw (Join-Path $PSScriptRoot 'TTMod.cs'))
	}
	[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072
}

function Find-DolphinUserDir {
	# Same order Dolphin uses on Windows: registry override, legacy Documents folder, then AppData.
	$reg = Get-ItemProperty -Path 'HKCU:\Software\Dolphin Emulator' -Name 'UserConfigPath' -ErrorAction SilentlyContinue
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

# ---- Controller layout for the mod (Xbox-style names; SDL and XInput controllers both use them)
# LB/RB pick clubs, LT/RT switch views, left stick left/right aims and up/down sets the power (up moves the
# landing spot farther: the game's L, down closer: its R), right stick left/right still turns the camera
# and up/down also sets the power, View/Back gives side views (the game's Z). The sticks drive the game's
# analog L/R, so the landing spot moves faster the further you tilt; a 25% dead zone keeps aiming from
# nudging it. Full tilt also clicks L/R for the menus that use them.
$ModLayoutVersion = 3
$ModProfileName = 'Toadstool Tour Mod'
$ModLayout = [ordered]@{
	'Main Stick/Up'     = '`Shoulder R`'
	'Main Stick/Down'   = '`Shoulder L`'
	'C-Stick/Up'        = '`Trigger R`'
	'C-Stick/Down'      = '`Trigger L`'
	'Triggers/L'        = ''  # analog only (filled below): a digital L would force full speed
	'Triggers/R'        = ''
	'Triggers/L-Analog' = ''  # stick up: landing spot farther (filled from the player's own stick setup)
	'Triggers/R-Analog' = ''  # stick down: landing spot closer
	'Triggers/Dead Zone' = '25.000000000000000'
	'Buttons/Z'         = '`Back`'
}

# Writes a Dolphin controller profile from the player's own Port 1 setup with the mod layout on top,
# and tells Dolphin to use it for the modded game only. Returns a short status for the player.
function Install-ModControllerProfile($userDir, $gameIni) {
	$pad = Read-IniSection (Join-Path $userDir 'Config\GCPadNew.ini') 'GCPad1'
	if (-not $pad['Device'] -or $pad['Device'] -notmatch '^(SDL|XInput)/') {
		return "Kept your own controls (mod layout needs an Xbox/PlayStation-style controller on Port 1; yours is '$($pad['Device'])')."
	}
	# Up/down come from the player's own stick bindings, since SDL and XInput name "up" differently.
	$stick = @{}
	foreach ($k in 'Main Stick/Up', 'Main Stick/Down', 'C-Stick/Up', 'C-Stick/Down') { $stick[$k] = $pad[$k] }
	if (-not $stick['Main Stick/Up']) { $stick['Main Stick/Up'] = '`Left Y+`' }
	if (-not $stick['Main Stick/Down']) { $stick['Main Stick/Down'] = '`Left Y-`' }
	if (-not $stick['C-Stick/Up']) { $stick['C-Stick/Up'] = '`Right Y+`' }
	if (-not $stick['C-Stick/Down']) { $stick['C-Stick/Down'] = '`Right Y-`' }
	$layout = [ordered]@{}
	foreach ($k in $ModLayout.Keys) { $layout[$k] = $ModLayout[$k] }
	$layout['Triggers/L-Analog'] = "($($stick['Main Stick/Up'])) | ($($stick['C-Stick/Up']))"
	$layout['Triggers/R-Analog'] = "($($stick['Main Stick/Down'])) | ($($stick['C-Stick/Down']))"
	$profile = Join-Path $userDir "Config\Profiles\GCPad\$ModProfileName.ini"
	$lines = New-Object System.Collections.Generic.List[string]
	$lines.Add('[Profile]')
	foreach ($k in $pad.Keys) { if (-not $layout.Contains($k)) { $lines.Add("$k = $($pad[$k])") } }
	foreach ($k in $layout.Keys) { $lines.Add("$k = $($layout[$k])") }
	New-Item -ItemType Directory -Force (Split-Path $profile) | Out-Null
	[IO.File]::WriteAllLines($profile, $lines)
	Set-IniValues $gameIni 'Controls' ([ordered]@{ 'PadProfile1' = $ModProfileName })
	return "Mod controls set for $($pad['Device'] -replace '^\w+/\d+/', ''): LB/RB clubs, LT/RT views, left stick aims and sets power."
}

# ---- Hotkeys for the mod. Fullscreen is Dolphin's, not the game's, so it's switched by a Dolphin hotkey: Alt+Enter
# and, with an Xbox/PlayStation-style controller, clicking both sticks in (the GameCube has no stick buttons, so
# the game never sees them). Esc no longer stops the game: Dolphin left fullscreen to ask "stop?"; Stop is
# Shift+Esc. Dolphin's Hotkeys.ini is shared by every game, so only those two change, and only while they're still
# Dolphin's own (or ours); a missing file is first written with Dolphin's built-in set (HotkeyManager::LoadDefaults,
# Windows), since Dolphin leaves any hotkey the file doesn't list unbound.
$ModHotkeysVersion = 1
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

# Sets the mod's two hotkeys (see above) for the controller on Port 1. Returns a short status for the player.
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
	$ours = $full -eq $DolphinFullscreen -or $full -like "$DolphinFullscreen | (*Thumb L* & *Thumb R*)"
	$sticks = $device -match '^(SDL|XInput)/'
	if ($ours) {
		$set['General/Toggle Fullscreen'] = if ($sticks) {
			"$DolphinFullscreen | (``$($device):Thumb L`` & ``$($device):Thumb R``)"
		} else { $DolphinFullscreen }
	}
	if ($set.Count) { Set-IniValues $path 'Hotkeys' $set }
	$how = if ($ours -and $sticks) { 'click both sticks in, or Alt+Enter' } else { $full }
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
