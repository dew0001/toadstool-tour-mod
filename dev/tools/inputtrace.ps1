# Sample the shooter's shot-setup input fields every ~30 ms; print a line whenever they change.
param([double]$Seconds = 8)
. "$PSScriptRoot\gcmem.ps1"
$dpid = (Get-TestPid)
[GCMem]::Open($dpid, 'GFTEMD') | Out-Null
$end = (Get-Date).AddSeconds($Seconds)
$t0 = Get-Date
$last = ''
while ((Get-Date) -lt $end) {
	$cur = [GCMem]::U8(0x804E68FB) -band 3
	$pl = 0x804ECE70 + $cur * 0x5204
	$s = [GCMem]::U32($pl + 0x5168)
	$line = 'state {0} view {1} held {2:X4} pressed {3:X4} +120 {4:N2} +124 {5:N2} +128 {6:N2} +12C {7:N2} +144 {8:N2} +14C {9:N2}' -f `
		[GCMem]::U32($pl + 0x24), [GCMem]::U32($s + 0x1C4), ([GCMem]::U32($s + 0x100) -shr 16), ([GCMem]::U32($s + 0x104) -shr 16),
		[GCMem]::F32($s + 0x120), [GCMem]::F32($s + 0x124), [GCMem]::F32($s + 0x128), [GCMem]::F32($s + 0x12C), [GCMem]::F32($s + 0x144), [GCMem]::F32($s + 0x14C)
	if ($line -ne $last) { '{0,6:N0}ms {1}' -f ((Get-Date) - $t0).TotalMilliseconds, $line; $last = $line }
	Start-Sleep -Milliseconds 30
}
