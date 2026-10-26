# Sample the aim view, zoom amount (+0x16C), C-stick Y (+0x12C) and the camera every ~30 ms; print changes.
param([double]$Seconds = 8, [string]$Out = '')
. "$PSScriptRoot\gcmem.ps1"
$dpid = (Get-TestPid)
[GCMem]::Open($dpid, 'GFTEMD') | Out-Null
$end = (Get-Date).AddSeconds($Seconds)
$t0 = Get-Date
$last = ''
$lines = @()
while ((Get-Date) -lt $end) {
	$cur = [GCMem]::U8(0x804E68FB) -band 3
	$pl = 0x804ECE70 + $cur * 0x5204
	$s = [GCMem]::U32($pl + 0x5168)
	$c = [GCMem]::U32(0x802D7E64)
	$line = 'st {0} view {1} z {2,6:N3} cy {3,5:N2} r {4} eye {5,7:N1} {6,6:N1} {7,7:N1} look {8,7:N1} {9,6:N1} {10,7:N1}' -f `
		[GCMem]::U32($pl + 0x24), [GCMem]::U32($s + 0x1C4), [GCMem]::F32($s + 0x16C), [GCMem]::F32($s + 0x12C), [GCMem]::U32($s + 0x1D0),
		[GCMem]::F32($c), [GCMem]::F32($c + 4), [GCMem]::F32($c + 8), [GCMem]::F32($c + 12), [GCMem]::F32($c + 16), [GCMem]::F32($c + 20)
	if ($line -ne $last) { $lines += ('{0,6:N0}ms {1}' -f ((Get-Date) - $t0).TotalMilliseconds, $line); $last = $line }
	Start-Sleep -Milliseconds 30
}
if ($Out) { $lines | Set-Content $Out } else { $lines }
