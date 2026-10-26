# Read the file log of a debug_patch.py "files" build: every file ID opened, in order, with its disc path.
param([switch]$Reset)
. "$PSScriptRoot\gcmem.ps1"
[GCMem]::Open((Get-TestPid), 'GFTEMD') | Out-Null
$log = 0x80057A14
if ($Reset) { [GCMem]::W32($log, 0) | Out-Null; 'log cleared'; return }
$n = [GCMem]::U32($log)
"count $n"
for ($i = 0; $i -lt $n; $i++) {
	$id = [GCMem]::U32($log + 4 + 4 * $i)
	$k = [int]($id -shr 1)
	$path = '{0}/{1}/{2}' -f [char][int](65 + [math]::Floor($k / 676)), [char][int](65 + [math]::Floor(($k % 676) / 26)), [char][int](65 + $k % 26)
	'{0,3} 0x{1:X4} {2}' -f $i, $id, $path
}
