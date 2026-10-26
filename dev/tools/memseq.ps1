# Find a byte sequence (hex, e.g. "0000010D0000010E") in MEM1 of the test Dolphin.
param([Parameter(Mandatory)] [string] $Hex, [int] $Dump = 32)
. "$PSScriptRoot\gcmem.ps1"
[GCMem]::Open((Get-TestPid), 'GFTEMD') | Out-Null
$b = [GCMem]::ReadGC(0x80000000, 0x1800000)
$s = [System.Text.Encoding]::GetEncoding(28591).GetString($b)
$pat = -join ((0..($Hex.Length / 2 - 1)) | ForEach-Object { [char][Convert]::ToByte($Hex.Substring(2 * $_, 2), 16) })
$i = 0
while (($i = $s.IndexOf($pat, $i, [StringComparison]::Ordinal)) -ge 0) {
	$hexs = -join ($b[$i..($i + $Dump - 1)] | ForEach-Object { '{0:X2}' -f $_ })
	'{0:X8}: {1}' -f (0x80000000 + $i), $hexs
	$i += 1
}
