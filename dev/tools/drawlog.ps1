# Read the debug draw log (debug_patch.py "draws" build) or set its skip switches.
param([string]$SkipModel = '', [string]$SkipCaller = '')
. "$PSScriptRoot\gcmem.ps1"
[GCMem]::Open((Get-TestPid), 'GFTEMD') | Out-Null
$log = 0x80057A14
$skip = $log + 4 + 63 * 8
if ($SkipModel -ne '') { [GCMem]::W32($skip, [Convert]::ToUInt32($SkipModel, 16)) }
if ($SkipCaller -ne '') { [GCMem]::W32($skip + 4, [Convert]::ToUInt32($SkipCaller, 16)) }
if ($SkipModel -eq '' -and $SkipCaller -eq '') {
	$n = [GCMem]::U32($log)
	"count $n"
	for ($i = 0; $i -lt $n; $i++) { '{0:X8} model {1:X8}' -f [GCMem]::U32($log + 4 + 8 * $i), [GCMem]::U32($log + 8 + 8 * $i) }
}
'skip model {0:X8} caller {1:X8}' -f [GCMem]::U32($skip), [GCMem]::U32($skip + 4)
