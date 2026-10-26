# Sample the shooter's state and the camera every ~20 ms for a few seconds; print a line whenever they move.
param([double]$Seconds = 6)
. "$PSScriptRoot\gcmem.ps1"
$dpid = (Get-TestPid)
[GCMem]::Open($dpid, 'GFTEMD') | Out-Null
$end = (Get-Date).AddSeconds($Seconds)
$last = ''
$t0 = Get-Date
while ((Get-Date) -lt $end) {
	$cur = [GCMem]::U8(0x804E68FB) -band 3
	$pl = 0x804ECE70 + $cur * 0x5204
	$st = [GCMem]::U32($pl + 0x24)
	$setup = [GCMem]::U32($pl + 0x5168)
	$view = [GCMem]::U32($setup + 0x1C4)
	$cam = [GCMem]::U32(0x802D7E64)
	$ball = [GCMem]::U32($pl + 0x1C)
	$e = '{0,8:N1}{1,8:N1}{2,8:N1}' -f [GCMem]::F32($cam), [GCMem]::F32($cam + 4), [GCMem]::F32($cam + 8)
	$l = '{0,8:N1}{1,8:N1}{2,8:N1}' -f [GCMem]::F32($cam + 12), [GCMem]::F32($cam + 16), [GCMem]::F32($cam + 20)
	$b = '{0,8:N1}{1,8:N1}{2,8:N1}' -f [GCMem]::F32($ball + 0x9C), [GCMem]::F32($ball + 0xA0), [GCMem]::F32($ball + 0xA4)
	$line = "state $st view $view | eye $e | look $l | ball $b"
	if ($line -ne $last) { '{0,6:N0}ms {1}' -f ((Get-Date) - $t0).TotalMilliseconds, $line; $last = $line }
	Start-Sleep -Milliseconds 20
}
