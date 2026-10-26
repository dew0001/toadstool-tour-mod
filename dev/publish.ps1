# Toadstool Tour Mod - publish a new version (maintainer only).
# Builds the mod, writes mod/patches/vN.json, does a reference build with the SAME C# code friends run
# (clean-game hash list + SHA-1 of the finished disc), and updates mod/latest.json. Commit and push after.
#
# Usage (Windows PowerShell 5.1, from the repo root):
#   powershell -ExecutionPolicy Bypass -File dev\publish.ps1 -Version 2 -CleanGame <clean .ciso/.iso>
#     -CleanDisc <extracted clean disc dir> -BuildDir <scratch dir> [-ReferenceIso <path>] [-SkipBuild]
#     [-ShyGuy <folder with Shy Guy.obj and heyho_body_alb.png; default: assets\shy-guy next to the repo>]
param(
	[Parameter(Mandatory)] [int] $Version,
	[Parameter(Mandatory)] [string] $CleanGame,
	[Parameter(Mandatory)] [string] $CleanDisc,
	[Parameter(Mandatory)] [string] $BuildDir,
	[string] $ReferenceIso,
	[string] $DolphinExe,
	[switch] $SkipBuild,
	[string] $ShyGuy = (Join-Path $PSScriptRoot '..\..\assets\shy-guy')
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
. (Join-Path $repo 'app\common.ps1')
Import-TTMod

$patchRel = "mod/patches/v$Version.json"
$patchPath = Join-Path $repo $patchRel
if (-not $SkipBuild) {
	robocopy $CleanDisc $BuildDir /MIR /NFL /NDL /NJH /NJS /NP /R:1 /W:1 | Out-Null
	if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" }
	if (-not (Test-Path (Join-Path $ShyGuy 'Shy Guy.obj'))) { throw "Shy Guy's model isn't in $ShyGuy" }
	python -I (Join-Path $PSScriptRoot 'build_mod.py') $CleanDisc $BuildDir --version $Version --shyguy (Resolve-Path $ShyGuy).Path
	if ($LASTEXITCODE) { throw 'build_mod.py failed' }
	python -I (Join-Path $PSScriptRoot 'make_patch.py') $CleanDisc $BuildDir $patchPath $Version
	if ($LASTEXITCODE) { throw 'make_patch.py failed' }
}

$patch = Get-Content -Raw $patchPath | ConvertFrom-Json
$src = [TTMod]::Open($CleanGame)
try {
	if ([TTMod]::GameId($src) -ne 'GFTE01-rev0') { throw "$CleanGame is not a clean GFTE01 rev 0 disc" }
	$disc = [TTMod]::ReadDisc($src)
	Write-Host 'Hashing the clean game...'
	$man = [TTMod]::Manifest($src, $disc)
	$changed = Get-PatchChanges $src $disc $patch
	if (-not $ReferenceIso) { $ReferenceIso = Join-Path $env:TEMP "ttmod-reference-v$Version.iso" }
	Write-Host "Reference build -> $ReferenceIso"
	[TTMod]::Build($src, $disc, $changed, $ReferenceIso)
}
finally { $src.Dispose() }
$resultSha1 = [TTMod]::Sha1File($ReferenceIso)

$manifest = [ordered]@{}
foreach ($k in ($man.Keys | Sort-Object)) { $manifest[$k] = $man[$k] }
$full = [ordered]@{
	format = 2; name = $patch.name; version = $Version; game_id = $patch.game_id; new_game_id = $patch.new_game_id
	files = $patch.files; clean_manifest = $manifest; result_sha1 = $resultSha1
}
[IO.File]::WriteAllText($patchPath, ($full | ConvertTo-Json -Depth 10), (New-Object Text.UTF8Encoding $false))

$appFiles = [ordered]@{}
foreach ($rel in 'app/play.ps1', 'app/common.ps1', 'app/TTMod.cs', 'app/version.txt') {
	$appFiles[$rel] = [TTMod]::Sha256File((Join-Path $repo $rel))
}
if (-not $DolphinExe) {
	$running = Get-Process Dolphin -ErrorAction SilentlyContinue | Select-Object -First 1
	if ($running) { $DolphinExe = $running.Path }
}
$dolphinVersion = Get-DolphinVersion $DolphinExe
if (-not $dolphinVersion) { Write-Warning 'Could not read the Dolphin version; latest.json will not pin one.' }
$latest = [ordered]@{
	name = 'Toadstool Tour Mod'
	version = $Version
	patch = $patchRel
	patch_sha256 = [TTMod]::Sha256File($patchPath)
	result_sha1 = $resultSha1
	app_version = [int](Get-Content (Join-Path $repo 'app/version.txt'))
	app_files = $appFiles
	dolphin = $dolphinVersion
	textures = [ordered]@{
		mega = 'https://mega.nz/file/uph2xbRY#VoZqBPjbGxnetCxzsGogiV_gA8AIb9GuRKXSUkQaLOw'
		sha256 = 'b23b08689819b5ebc4ad4b86ac49f120902cce628a99e1f7de1a1c2c589d8e0c'
		credit = 'Toadstool Tour 4x UI texture pack by NickPancakes - https://forums.dolphin-emu.org/Thread-mario-golf-toadstool-tour-gcn-4x-ui-texture-pack'
	}
}
[IO.File]::WriteAllText((Join-Path $repo 'mod/latest.json'), ($latest | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding $false))
Write-Host ''
Write-Host "Published v$Version locally: result SHA-1 $resultSha1" -ForegroundColor Green
Write-Host 'Next: git add -A; git commit; git push'
