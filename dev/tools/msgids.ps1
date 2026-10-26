# Find message IDs (bank<<24 | index) whose string pointer equals given addresses, from live RAM.
param([string[]]$Targets)
. "$PSScriptRoot\gcmem.ps1"
$dpid = (Get-TestPid)
[GCMem]::Open($dpid, 'GFTEMD') | Out-Null
$want = @{}
foreach ($t in $Targets) { $v = [Convert]::ToUInt32($t, 16); foreach ($d in 0, 1, 2) { $want[[uint32]($v - $d)] = "$t-$d" } }
for ($bank = 0; $bank -lt 0x32; $bank++) {
	$count = [GCMem]::U32(0x802CBEC0 + 8 * $bank)
	$arr = [GCMem]::U32(0x802CBEC4 + 8 * $bank)
	if ($count -le 0 -or $count -gt 100000 -or $arr -lt 0x80000000) { continue }
	"bank {0}: {1} messages, pointers at {2:X8}" -f $bank, $count, $arr
	for ($i = 0; $i -lt $count; $i++) {
		$p = [GCMem]::U32($arr + 4 * $i)
		if ($want.ContainsKey($p)) { '  {0} -> id 0x{1:X8} (index 0x{2:X})' -f $want[$p], (($bank -shl 24) -bor $i), $i }
	}
}

