# Swing the test game's current shot on the meter's own target: start, set power when the meter counter reaches
# the target step, hit when it comes back round to the impact mark (not for putts). Reads the meter from RAM and presses A on the
# virtual pad (dsu_pad.py's command port), so shots land where the game aims them (putts included).
#
#   swing.ps1 [-Lead <frames to press early, for the pad's latency>] [-Power <step instead of the target>]
param([int] $Lead = 2, [int] $Power = -1)
. "$PSScriptRoot\gcmem.ps1"
[GCMem]::Open((Get-TestPid), 'GFTEMD') | Out-Null
$counter = 0x80523CB8      # meter counter: 0..2 * max - 1, one step a frame
$targetAt = 0x80523CBC     # the meter's target step (where the aim puts the ball)
$cur = [GCMem]::U8(0x804E68FB) -band 3
$setup = [GCMem]::U32(0x804ECE70 + $cur * 0x5204 + 0x5168)
$max = [GCMem]::U32($setup + 0x250)
$target = if ($Power -ge 0) { $Power } else { [GCMem]::U32($targetAt) }

function Press {
	$c = [Net.Sockets.TcpClient]::new('127.0.0.1', 26761)
	$s = $c.GetStream()
	$b = [Text.Encoding]::ASCII.GetBytes("press Cross 60`n")
	$s.Write($b, 0, $b.Length)
	$c.Close()
}
function WaitFor([int] $step) {
	$sw = [Diagnostics.Stopwatch]::StartNew()
	while ([GCMem]::U32($counter) -lt $step) {
		if ($sw.ElapsedMilliseconds -gt 8000) { throw "meter never reached $step (at $([GCMem]::U32($counter)))" }
	}
}
Press
Start-Sleep -Milliseconds 100
WaitFor ([math]::Max(0, $target - $Lead))
Press
$power = [GCMem]::U32($counter)
if ([GCMem]::U32($setup + 0x1D4) -ne 13) {   # putts have no impact press
	WaitFor (2 * $max - 1 - $Lead)
	Press
}
"max $max target $target, set power at $power"
