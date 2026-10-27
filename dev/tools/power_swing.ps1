# Swing the test game's shot (a power shot when the shot type is 0, setup +0x1CC; B cycles it) and catch its burst:
# start, set power when the meter counter reaches the target step, press impact when it comes round to the impact
# mark (the test profile's auto swing hits by itself), then as soon as the ball moves list the live effect particles
# by type and index parity and take screenshots (the pad's PS button).
#
#   power_swing.ps1 [-Power <step; 999 = the club's top>] [-Lead <frames early>] [-Shots N] [-Gap <ms>] [-Clean]
#
# -Clean holds the impact error (setup +0x1AC) at 0 until the ball moves, so a top-power shot gets the burst's
# strongest case (_DAT_8050f1ac = 2, see RE-NOTES Characters) every time. A test aid only.
param([int] $Power = -1, [int] $Lead = 2, [int] $Shots = 4, [int] $Gap = 110, [switch] $Clean)
. "$PSScriptRoot\gcmem.ps1"
[GCMem]::Open((Get-TestPid), 'GFTEMD') | Out-Null
$counter = 0x80523CB8       # meter counter: 0..2 * max - 1, one step a frame
$cur = [GCMem]::U8(0x804E68FB) -band 3
$pl = 0x804ECE70 + $cur * 0x5204
$setup = [GCMem]::U32($pl + 0x5168)
$max = [GCMem]::U32($setup + 0x250)
$target = if ($Power -ge 900) { $max + 1 } elseif ($Power -ge 0) { $Power } else { [GCMem]::U32(0x80523CBC) }

function Send([string] $line) {
	$c = [Net.Sockets.TcpClient]::new('127.0.0.1', 26761)
	$s = $c.GetStream()
	$b = [Text.Encoding]::ASCII.GetBytes("$line`n")
	$s.Write($b, 0, $b.Length)
	$c.Close()
}
$sw = [Diagnostics.Stopwatch]::StartNew()
function Note([string] $what) { '{0,5} ms  {1}' -f $sw.ElapsedMilliseconds, $what }
"max $max, target $target, shot type $([GCMem]::U32($setup + 0x1CC)), power shots left $([GCMem]::U8($pl + 0x5200))"
Send 'press Cross 60'
Start-Sleep -Milliseconds 100
while ([GCMem]::U32($counter) -lt [math]::Max(0, $target - $Lead)) { if ($sw.ElapsedMilliseconds -gt 8000) { throw 'meter never reached the target' } }
Send 'press Cross 60'
Note "power set at $([GCMem]::U32($counter))"
$pressed = $false; $t0 = $sw.ElapsedMilliseconds
while ($sw.ElapsedMilliseconds - $t0 -lt 6000) {
	$c = [GCMem]::U32($counter); $st = [GCMem]::U32($pl + 0x24)
	if ($st -eq 7) {
		Note 'ball moving'
		$raw = [GCMem]::ReadGC(0x8050F1B8, 0x400 * 0x3C); $h = @{}
		for ($i = 0; $i -lt 0x400; $i++) {
			$o = $i * 0x3C
			$t = [BitConverter]::ToInt32([byte[]]($raw[($o + 0x33)..($o + 0x30)]), 0)
			if ($t -eq -1) { continue }
			$k = 'type 0x{0:X} {1}' -f $t, $(if ($i % 2) { 'odd' } else { 'even' })
			$h[$k] = 1 + $(if ($h.ContainsKey($k)) { $h[$k] } else { 0 })
		}
		Note ('particles: ' + (($h.GetEnumerator() | Sort-Object Name | ForEach-Object { '{0} x{1}' -f $_.Name, $_.Value }) -join ', '))
		for ($i = 0; $i -lt $Shots; $i++) { Send 'press PS 40'; Start-Sleep -Milliseconds $Gap }
		break
	}
	if ($Clean) { [GCMem]::W32($setup + 0x1AC, 0) | Out-Null }
	if (-not $pressed -and $c -ge 2 * $max - 1 - $Lead) { Send 'press Cross 60'; Note 'impact pressed'; $pressed = $true }
}
Start-Sleep -Milliseconds 200
Note ('burst case (_DAT_8050f1ac) {0}, golfer code {1}' -f [GCMem]::U32(0x8050F1AC), [GCMem]::U32(0x8050F1B0))
