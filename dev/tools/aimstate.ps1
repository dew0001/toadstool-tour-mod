. "$PSScriptRoot\gcmem.ps1"
$dpid = (Get-TestPid)
[GCMem]::Open($dpid, 'GFTEMD') | Out-Null
function Hx($a) { '{0:X8}' -f [GCMem]::U32($a) }
function F($a) { '{0:N3}' -f [GCMem]::F32($a) }
"hook 0x80424AF8: $(Hx 0x80424AF8)  stub 0x8003EB80: $(Hx 0x8003EB80)  movie 0x8000E120: $(Hx 0x8000E120)"
$cur = [GCMem]::U8(0x804E68FB)
$pl = 0x804ECE70 + ($cur -band 3) * 0x5204
$setup = [GCMem]::U32($pl + 0x5168)
"cur $cur  state $([GCMem]::U32($pl + 0x24))  setup $(Hx ($pl + 0x5168))"
"club $([GCMem]::U32($setup + 0x1D4))  view $([GCMem]::U32($setup + 0x1C4))  zoom $(F ($setup + 0x12C))  +128 $(F ($setup + 0x128))  +16c $(F ($setup + 0x16C))"
"target $(F ($setup + 0x1EC)) $(F ($setup + 0x1F0)) $(F ($setup + 0x1F4))   aim ball $(F 0x80502734) $(F 0x80502738) $(F 0x8050273C)"
$ball = [GCMem]::U32($pl + 0x1C)
"ball rec pos $(F ($ball + 0x9C)) $(F ($ball + 0xA0)) $(F ($ball + 0xA4))"
$cam = [GCMem]::U32(0x802D7E64)
"camera $('{0:X8}' -f $cam): eye $(F $cam) $(F ($cam + 4)) $(F ($cam + 8))  look $(F ($cam + 12)) $(F ($cam + 16)) $(F ($cam + 20))"

