# Find an ASCII string in MEM1 of the test Dolphin; print address and surrounding text.
param([Parameter(Mandatory)] [string] $Text, [int] $Context = 24)
. "$PSScriptRoot\gcmem.ps1"
[GCMem]::Open((Get-TestPid), 'GFTEMD') | Out-Null
$b = [GCMem]::ReadGC(0x80000000, 0x1800000)
$s = [System.Text.Encoding]::GetEncoding(28591).GetString($b)
$i = 0
while (($i = $s.IndexOf($Text, $i)) -ge 0) {
	$from = [math]::Max(0, $i - $Context)
	$snip = ($s.Substring($from, [math]::Min($s.Length - $from, $Text.Length + 2 * $Context)) -replace '[^\x20-\x7E]', '.')
	'{0:X8}: {1}' -f (0x80000000 + $i), $snip
	$i += $Text.Length
}
