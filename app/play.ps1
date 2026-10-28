# Toadstool Tour Mod - Play: keeps the modded game up to date, then starts it in Dolphin.
# Builds the mod from YOUR OWN copy of Mario Golf: Toadstool Tour (USA); the mod files hold no game data.
param(
	[switch]$NoLaunch,         # update only (e.g. right before a NetPlay session)
	[string]$Source,           # where latest.json and patches come from: URL base or local folder (testing)
	[string]$DolphinUserDir,   # override Dolphin's user folder (testing)
	[string]$GamePath          # override: your own Toadstool Tour copy
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
Import-TTMod

$root = Split-Path -Parent $PSScriptRoot
$dataDir = Join-Path $root 'data'
New-Item -ItemType Directory -Force $dataDir | Out-Null
$configPath = Join-Path $dataDir 'config.json'
if (-not $Source) { $Source = 'https://raw.githubusercontent.com/dew0001/toadstool-tour-mod/main' }
$OutName = 'Mario Golf - Toadstool Tour (Mod).iso'

function Say($msg, $color = 'Gray') { Write-Host $msg -ForegroundColor $color }

function Get-RepoFile($rel, $dest) {
	if ($Source -match '^https?://') {
		$wc = New-Object Net.WebClient
		$url = "$Source/$rel" + '?t=' + [DateTime]::UtcNow.Ticks  # skip stale caches
		if ($dest) { $wc.DownloadFile($url, $dest); return }
		return $wc.DownloadString($url)
	}
	$p = Join-Path $Source $rel
	if ($dest) { Copy-Item $p $dest -Force; return }
	return Get-Content -Raw $p
}

$config = @{}
if (Test-Path $configPath) {
	(Get-Content -Raw $configPath | ConvertFrom-Json).psobject.Properties | ForEach-Object { $config[$_.Name] = $_.Value }
}
function Save-Config { $config | ConvertTo-Json | Set-Content -Path $configPath -Encoding UTF8 }

Say ''
Say 'Toadstool Tour Mod' Cyan
Say '------------------'

# 1. What's the newest version?
$latest = $null
try { $latest = Get-RepoFile 'mod/latest.json' | ConvertFrom-Json }
catch { Say "Couldn't check for updates ($($_.Exception.Message))." Yellow }

# 2. Update these tools first if the repo has newer ones, then start over with them.
$verFile = Join-Path $PSScriptRoot 'version.txt'
$appVersion = if (Test-Path $verFile) { [int](Get-Content $verFile) } else { 0 }
if ($latest -and [int]$latest.app_version -gt $appVersion) {
	Say 'Updating the mod tools...'
	$stage = Join-Path $dataDir 'app-update'
	Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue
	New-Item -ItemType Directory -Force $stage | Out-Null
	$names = @($latest.app_files.psobject.Properties)
	foreach ($p in $names) {
		$tmp = Join-Path $stage ($p.Name -replace '[\\/ ]', '_')
		Get-RepoFile $p.Name $tmp
		if ([TTMod]::Sha256File($tmp) -ne $p.Value) { throw "Download of $($p.Name) was corrupted; try again." }
	}
	foreach ($p in $names) {
		Copy-Item (Join-Path $stage ($p.Name -replace '[\\/ ]', '_')) (Join-Path $root $p.Name) -Force
	}
	Say 'Restarting with the new tools...'
	$again = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath)
	if ($NoLaunch) { $again += '-NoLaunch' }
	if ($PSBoundParameters.ContainsKey('Source')) { $again += @('-Source', $Source) }
	if ($PSBoundParameters.ContainsKey('DolphinUserDir')) { $again += @('-DolphinUserDir', $DolphinUserDir) }
	if ($PSBoundParameters.ContainsKey('GamePath')) { $again += @('-GamePath', $GamePath) }
	& powershell.exe @again
	exit $LASTEXITCODE
}

# 3. Find Dolphin and your copy of the game (remembered after the first run).
if (-not $DolphinUserDir) { $DolphinUserDir = $config['dolphin_user'] }
if (-not $DolphinUserDir -or -not (Test-Path $DolphinUserDir)) { $DolphinUserDir = Find-DolphinUserDir }
if (-not $DolphinUserDir) {
	Say "Can't find Dolphin's settings folder. Open Dolphin once, close it, then run Play again." Yellow
	Say 'Using a portable Dolphin? Paste the full path of the "User" folder next to Dolphin.exe.'
	$DolphinUserDir = Read-Host 'User folder (or Enter to cancel)'
	if (-not $DolphinUserDir -or -not (Test-Path $DolphinUserDir)) { exit 1 }
}
$config['dolphin_user'] = $DolphinUserDir

if (-not $GamePath) { $GamePath = $config['game'] }
if (-not $GamePath -or -not (Test-Path $GamePath) -or -not (Test-CleanGame $GamePath)) {
	Say 'Looking for your copy of Toadstool Tour in your Dolphin game folders...'
	$GamePath = Find-CleanGame $DolphinUserDir
}
if (-not $GamePath) {
	Say "Didn't find it. Pick your Mario Golf: Toadstool Tour (USA) file (.iso or .ciso)."
	$GamePath = Pick-File 'Pick YOUR copy of Mario Golf: Toadstool Tour (USA)' 'GameCube games (*.iso;*.gcm;*.ciso)|*.iso;*.gcm;*.ciso|All files|*.*'
	if (-not $GamePath) { exit 1 }
	if (-not (Test-CleanGame $GamePath)) {
		Say "That isn't Mario Golf: Toadstool Tour USA (GFTE01). .rvz/.gcz files: in Dolphin, right-click the game > Convert File > ISO." Red
		exit 1
	}
}
$config['game'] = $GamePath
$out = Join-Path (Split-Path $GamePath) $OutName
Save-Config
Say "Your game: $GamePath"

# 4. Build the modded game if it's missing or out of date.
if ($latest) {
	$current = (Test-Path $out) -and $config['installed_sha1'] -eq $latest.result_sha1
	if (-not $current) {
		Say "Installing mod v$($latest.version)..." Cyan
		$patchFile = Join-Path $dataDir ("patch-v{0}.json" -f $latest.version)
		Get-RepoFile $latest.patch $patchFile
		if ([TTMod]::Sha256File($patchFile) -ne $latest.patch_sha256) { throw 'Patch download was corrupted; try again.' }
		$patch = Get-Content -Raw $patchFile | ConvertFrom-Json
		$data = $null
		if ($patch.data) {
			Say '  downloading the course data...'
			$dataFile = Join-Path $dataDir (Split-Path -Leaf $patch.data.path)
			Get-RepoFile $patch.data.path $dataFile
			$data = Get-PatchData $patch $dataFile
		}
		$src = [TTMod]::Open($GamePath)
		try {
			$disc = [TTMod]::ReadDisc($src)
			Say '  checking your game files...'
			$bad = Compare-CleanManifest $src $disc $patch
			if ($bad.Count) { throw "Your copy doesn't match the clean USA game ($($bad.Count) files differ, e.g. $($bad[0]))." }
			$changed = Get-PatchChanges $src $disc $patch $data
			Say '  building the modded game (about 1.4 GB)...'
			try { [TTMod]::Build($src, $disc, $changed, $out) }
			catch [System.IO.IOException] { throw "Couldn't write the modded game ($($_.Exception.InnerException.Message)). If Dolphin is running, close it and run Play again." }
		}
		finally { $src.Dispose() }
		Say '  verifying...'
		if ([TTMod]::Sha1File($out) -ne $patch.result_sha1) {
			Remove-Item $out -Force
			throw 'The built game came out different from the official build.'
		}
		$config['installed_version'] = $latest.version
		$config['installed_sha1'] = $latest.result_sha1
		Save-Config
		Say "Mod v$($latest.version) ready: $out" Green
	}
	else { Say "Mod v$($latest.version) is up to date." Green }
}
elseif (-not (Test-Path $out)) { throw "Can't download the mod right now and it isn't installed yet. Check your internet and try again." }

# 5. HD UI textures (from their author's original link) and Dolphin settings for the mod.
if ($latest -and $latest.textures) {
	$texDir = Join-Path $DolphinUserDir 'Load\Textures\GFT'
	$marker = Join-Path $texDir '.toadstool-mod-textures'
	if (-not (Test-Path $marker) -or (Get-Content $marker) -ne $latest.textures.sha256) {
		try {
			Say 'Downloading HD UI textures (by NickPancakes, 3 MB)...'
			$zip = Join-Path $dataDir 'hd-textures.zip'
			[TTMod]::MegaDownload($latest.textures.mega, $zip)
			if ([TTMod]::Sha256File($zip) -ne $latest.textures.sha256) { throw 'unexpected file' }
			$unz = Join-Path $dataDir 'hd-textures'
			Remove-Item -Recurse -Force $unz -ErrorAction SilentlyContinue
			Expand-Archive -Path $zip -DestinationPath $unz
			New-Item -ItemType Directory -Force $texDir | Out-Null
			Copy-Item (Join-Path $unz 'textures\GFT\*') $texDir -Recurse -Force
			Set-Content -Path $marker -Value $latest.textures.sha256
			Say 'HD textures installed.' Green
		}
		catch { Say "Couldn't install the HD textures ($($_.Exception.Message)). The game works fine without them." Yellow }
	}
}
$ini = Join-Path $DolphinUserDir 'GameSettings\GFTEMD.ini'
if (-not (Test-Path $ini)) {
	New-Item -ItemType Directory -Force (Split-Path $ini) | Out-Null
	@'
# Toadstool Tour Mod: HD UI textures on, cached in RAM. Widescreen and unlocks are built into the game.
[Video_Settings]
HiresTextures = True
CacheHiresTextures = True

[Video_Enhancements]
# 4 = 16x anisotropic filtering
MaxAnisotropy = 4
'@ | Set-Content -Path $ini -Encoding ASCII
}
# Force 16:9: Dolphin's automatic aspect detection sometimes flips to 4:3 and squeezes the picture.
Set-IniValues $ini 'Video_Settings' ([ordered]@{ 'AspectRatio' = '1' })
# Start the mod fullscreen, covering the whole screen and taskbar (borderless, so Alt+Tab and overlays
# behave); Alt+Enter or both sticks clicked in switch to a window and back (Install-ModHotkeys). Other games
# keep their own setting.
Set-IniValues $ini 'Display' ([ordered]@{ 'Fullscreen' = 'True' })
Set-IniValues $ini 'Video_Settings' ([ordered]@{ 'BorderlessFullscreen' = 'True' })
# The HD textures are part of the mod, so keep them on even if this file predates them or was edited.
Set-IniValues $ini 'Video_Settings' ([ordered]@{ 'HiresTextures' = 'True'; 'CacheHiresTextures' = 'True' })
# Sharp by default. Dolphin's own default is native 640x528, which looks blurry on a modern screen, so when
# neither this game's settings nor the player's global graphics settings pick a resolution above native,
# scale to the screen (Auto). A resolution the player chose stays theirs.
$globalRes = (Read-IniSection (Join-Path $DolphinUserDir 'Config\GFX.ini') 'Settings')['InternalResolution']
if (-not (Read-IniSection $ini 'Video_Settings').Contains('InternalResolution') -and (-not $globalRes -or $globalRes -eq '1')) {
	Set-IniValues $ini 'Video_Settings' ([ordered]@{ 'InternalResolution' = '0' })
}

# Mod controller layout (every controller, see Install-ModControllerProfile), rebuilt when the layout changes or
# Port 1 changes (a keyboard there keeps its keys).
$device = (Read-IniSection (Join-Path $DolphinUserDir 'Config\GCPadNew.ini') 'GCPad1')['Device']
$profilePath = Join-Path $DolphinUserDir "Config\Profiles\GCPad\$ModProfileName.ini"
$layoutCurrent = $config['layout_version'] -eq $ModLayoutVersion -and $config['layout_device'] -eq $device -and
	(Test-Path $profilePath) -and (Read-IniSection $ini 'Controls')['PadProfile1'] -eq $ModProfileName
if (-not $layoutCurrent) {
	Say (Install-ModControllerProfile $DolphinUserDir $ini)
	$config['layout_version'] = $ModLayoutVersion
	$config['layout_device'] = $device
	Save-Config
}
# Fullscreen toggle and Esc (Install-ModHotkeys), set again when they change or you switch controllers.
if ($config['hotkeys_version'] -ne $ModHotkeysVersion -or $config['hotkeys_device'] -ne $device) {
	Say (Install-ModHotkeys $DolphinUserDir $device)
	$config['hotkeys_version'] = $ModHotkeysVersion
	$config['hotkeys_device'] = $device
	Save-Config
}

# 6. Start the game.
$dolphin = $config['dolphin_exe']
if (-not $dolphin -or -not (Test-Path $dolphin)) { $dolphin = Find-DolphinExe $(if ($latest) { $latest.dolphin }) }
if (-not $dolphin) {
	Say 'Where is Dolphin? Pick Dolphin.exe, in the folder you installed or unzipped Dolphin to.'
	$dolphin = Pick-File 'Find Dolphin.exe' 'Dolphin.exe|Dolphin.exe'
}
if ($dolphin) {
	$config['dolphin_exe'] = $dolphin
	Save-Config
	$have = Get-DolphinVersion $dolphin
	if ($latest -and $latest.dolphin -and $have -and $have -ne $latest.dolphin) {
		Say "Heads up: online play with the group needs Dolphin $($latest.dolphin); you have $have." Yellow
	}
}
$title = if ($config['installed_version']) { "Mario Golf: Toadstool Tour (Mod v$($config['installed_version']))" } else { 'Mario Golf: Toadstool Tour (Mod)' }
if ($NoLaunch) { Say "Done. Start Dolphin whenever you like; the game is listed as ""$title""." Green; exit 0 }
$launch = @('-e', "`"$out`"")
if ($PSBoundParameters.ContainsKey('DolphinUserDir')) { $launch = @('-u', "`"$DolphinUserDir`"") + $launch }
if ($dolphin) { Start-Process -FilePath $dolphin -ArgumentList $launch }
else { Say "Open Dolphin and start ""$title"" (file: $out)." }
