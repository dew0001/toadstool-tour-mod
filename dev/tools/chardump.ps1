# Dump the shooter's character object (player+0x4F18): words as hex and float.
param([int]$Bytes = 0x1E4, [long]$Addr = 0)
. "$PSScriptRoot\gcmem.ps1"
$dpid = (Get-TestPid)
[GCMem]::Open($dpid, 'GFTEMD') | Out-Null
if (-not $Addr) {
	$cur = [GCMem]::U8(0x804E68FB) -band 3
	$pl = 0x804ECE70 + $cur * 0x5204
	$Addr = [GCMem]::U32($pl + 0x4F18)
}
'object at {0:X8}' -f $Addr
for ($o = 0; $o -lt $Bytes; $o += 16) {
	$line = '{0:X3}:' -f $o
	for ($k = 0; $k -lt 16; $k += 4) {
		$w = [GCMem]::U32($Addr + $o + $k)
		$f = [GCMem]::F32($Addr + $o + $k)
		$fs = if ([math]::Abs($f) -gt 1e-4 -and [math]::Abs($f) -lt 1e6) { '{0,9:G5}' -f $f } else { '         ' }
		$line += ' {0:X8}{1}' -f $w, $fs
	}
	$line
}
