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

# Turn a patch (parsed JSON) into { disc path -> new bytes }, checking every result hash.
function Get-PatchChanges($src, $disc, $patch) {
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
