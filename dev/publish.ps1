# Toadstool Tour Mod - publish a new version (maintainer only).
# Builds the mod, writes mod/patches/vN.json, does a reference build with the SAME C# code friends run
# (clean-game hash list + SHA-1 of the finished disc), and updates mod/latest.json. Commit and push after.
#
# Usage (Windows PowerShell 5.1, from the repo root):
#   powershell -ExecutionPolicy Bypass -File dev\publish.ps1 -Version 2 -CleanGame <clean .ciso/.iso>
#     -CleanDisc <extracted clean disc dir> -BuildDir <scratch dir> [-ReferenceIso <path>] [-SkipBuild]
#     [-ShyGuy <folder with Shy Guy.obj and heyho_body_alb.png; default: assets\shy-guy next to the repo>]
#     [-ShyGuyVoice <zip of his WAV clips; default: assets\shy-guy\mario-power-tennis-shy-guy-voice.zip>]
#     [-ShyGuyMpt <Mario Power Tennis disc for his model; default: gamecube_games\Mario Power Tennis (USA) (Rev 1).ciso
#      two folders above the repo; '' builds him from the OBJ in -ShyGuy instead>]
#     [-Course8 <the 8th course's folder from dev\course\holegen.py; default: mod\course8 next to the repo; '' for none>]
#     [-Course9 <the 9th course's folder (TTMOD_COURSE=pasadena); default: mod\course9 next to the repo; '' for none>]
#     [-Course10 / -Course11 <Battleground's / Timber Creek's folders (TTMOD_COURSE=battleground / timbercreek);
#      defaults: mod\course10, mod\course11 next to the repo; '' for none>]
#     [-Tony <folder with Tony the Tiger's source\untitled.glb; default: assets\tony-the-tiger next to the repo; '' for none>]
param(
	[Parameter(Mandatory)] [int] $Version,
	[Parameter(Mandatory)] [string] $CleanGame,
	[Parameter(Mandatory)] [string] $CleanDisc,
	[Parameter(Mandatory)] [string] $BuildDir,
	[string] $ReferenceIso,
	[string] $DolphinExe,
	[switch] $SkipBuild,
	[string] $ShyGuy = (Join-Path $PSScriptRoot '..\..\assets\shy-guy'),
	[string] $ShyGuyVoice = (Join-Path $PSScriptRoot '..\..\assets\shy-guy\mario-power-tennis-shy-guy-voice.zip'),
	[string] $ShyGuyMpt = (Join-Path $PSScriptRoot '..\..\..\gamecube_games\Mario Power Tennis (USA) (Rev 1).ciso'),
	[string] $Course8 = (Join-Path $PSScriptRoot '..\..\mod\course8'),
	[string] $Course9 = (Join-Path $PSScriptRoot '..\..\mod\course9'),
	[string] $Course10 = (Join-Path $PSScriptRoot '..\..\mod\course10'),
	[string] $Course11 = (Join-Path $PSScriptRoot '..\..\mod\course11'),
	[string] $Tony = (Join-Path $PSScriptRoot '..\..\assets\tony-the-tiger')
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
	$mpt = @()
	if ($ShyGuyMpt) {
		if (-not (Test-Path $ShyGuyMpt)) { throw "No Mario Power Tennis disc at $ShyGuyMpt (pass -ShyGuyMpt '' for the OBJ)" }
		$mpt = @('--shyguy-mpt', (Resolve-Path $ShyGuyMpt).Path)
	}
	elseif (-not (Test-Path (Join-Path $ShyGuy 'Shy Guy.obj'))) { throw "Shy Guy's model isn't in $ShyGuy" }
	if (-not (Test-Path $ShyGuyVoice)) { throw "Shy Guy's voice clips aren't at $ShyGuyVoice" }
	$course = @()
	if ($Course8) {
		if (-not (Test-Path (Join-Path $Course8 'course.json'))) { throw "No 8th course at $Course8 (run dev\course\holegen.py, or pass -Course8 '')" }
		$course = @('--course8', (Resolve-Path $Course8).Path)
		if ($Course9) {
			if (-not (Test-Path (Join-Path $Course9 'course.json'))) { throw "No 9th course at $Course9 (run dev\course\holegen.py with TTMOD_COURSE=pasadena, or pass -Course9 '')" }
			$course += @('--course9', (Resolve-Path $Course9).Path)
			foreach ($c in @(@('--course10', $Course10), @('--course11', $Course11))) {
				if (-not $c[1]) { break }
				if (-not (Test-Path (Join-Path $c[1] 'course.json'))) { throw "No course at $($c[1]) (run dev\course\holegen.py, or pass '')" }
				$course += @($c[0], (Resolve-Path $c[1]).Path)
			}
		}
	}
	$tonyArgs = @()
	if ($Tony) {
		if (-not (Test-Path (Join-Path $Tony 'source\untitled.glb'))) { throw "Tony's model isn't in $Tony (pass -Tony '' for none)" }
		$tonyArgs = @('--tony', (Resolve-Path $Tony).Path)
	}
	python -I (Join-Path $PSScriptRoot 'build_mod.py') $CleanDisc $BuildDir --version $Version --shyguy (Resolve-Path $ShyGuy).Path `
		--shyguy-voice (Resolve-Path $ShyGuyVoice).Path @mpt @course @tonyArgs
	if ($LASTEXITCODE) { throw 'build_mod.py failed' }
	python -I (Join-Path $PSScriptRoot 'make_patch.py') $CleanDisc $BuildDir $patchPath $Version @course
	if ($LASTEXITCODE) { throw 'make_patch.py failed' }
}

$patch = Get-Content -Raw $patchPath | ConvertFrom-Json
$data = $null
if ($patch.data) { $data = Get-PatchData $patch (Get-PatchDataPaths $patch $repo) }
$src = [TTMod]::Open($CleanGame)
try {
	if ([TTMod]::GameId($src) -ne 'GFTE01-rev0') { throw "$CleanGame is not a clean GFTE01 rev 0 disc" }
	$disc = [TTMod]::ReadDisc($src)
	Write-Host 'Hashing the clean game...'
	$man = [TTMod]::Manifest($src, $disc)
	$changed = Get-PatchChanges $src $disc $patch $data
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
if ($patch.data) { $full['data'] = @($patch.data) }   # the courses' own bytes: v22 mod/data/<course>-<hash>.gz
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
