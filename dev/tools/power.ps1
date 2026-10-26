# Print the shooter's power step, the quarter-step state (cave 5) and the landing target.
. "$PSScriptRoot\gcmem.ps1"
$dpid = (Get-TestPid)
[GCMem]::Open($dpid, 'GFTEMD') | Out-Null
$cur = [GCMem]::U8(0x804E68FB) -band 3
$pl = 0x804ECE70 + $cur * 0x5204
$s = [GCMem]::U32($pl + 0x5168)
'state {0} club {1} step {2} max {3} meter target {4} | fine player {5:X8} club {6} step {7} quarter {8} | aim {9:N1} {10:N1} {11:N1} ball {12:N1} {13:N1} {14:N1}' -f `
	[GCMem]::U32($pl + 0x24), [GCMem]::U32($s + 0x1D4), [GCMem]::U32($s + 0x1D0), [GCMem]::U32($s + 0x250), [GCMem]::U32(0x80523CBC),
	[GCMem]::U32(0x800411B8), [GCMem]::U32(0x800411BC), [GCMem]::U32(0x800411C0), [GCMem]::U32(0x800411C4),
	[GCMem]::F32($s + 0x1EC), [GCMem]::F32($s + 0x1F0), [GCMem]::F32($s + 0x1F4),
	[GCMem]::F32(0x80502734), [GCMem]::F32(0x80502738), [GCMem]::F32(0x8050273C)
$dx = [GCMem]::F32($s + 0x1EC) - [GCMem]::F32(0x80502734); $dz = [GCMem]::F32($s + 0x1F4) - [GCMem]::F32(0x8050273C)
'aim distance {0:N2} ft = {1:N2} yd' -f [math]::Sqrt($dx * $dx + $dz * $dz), ([math]::Sqrt($dx * $dx + $dz * $dz) / 3)
