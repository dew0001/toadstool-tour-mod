# Find every aligned word equal to a value in MEM1 (24 MB) of the test Dolphin.
param([Parameter(Mandatory)] [string] $Value)
. "$PSScriptRoot\gcmem.ps1"
[GCMem]::Open((Get-TestPid), 'GFTEMD') | Out-Null
$v = [Convert]::ToUInt32($Value, 16)
$b = [GCMem]::ReadGC(0x80000000, 0x1800000)
$p0 = [byte]($v -shr 24); $p1 = [byte](($v -shr 16) -band 0xFF); $p2 = [byte](($v -shr 8) -band 0xFF); $p3 = [byte]($v -band 0xFF)
for ($i = 0; $i -lt $b.Length - 3; $i += 4) {
	if ($b[$i] -eq $p0 -and $b[$i + 1] -eq $p1 -and $b[$i + 2] -eq $p2 -and $b[$i + 3] -eq $p3) { '{0:X8}' -f (0x80000000 + $i) }
}
