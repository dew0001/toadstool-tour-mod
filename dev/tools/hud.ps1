# HUD anchor table tool. -List: callers with call counts. -Reset: zero counts. -Set addr=anchor,...: change anchors live.
param([switch]$List, [switch]$Reset, [string[]]$Set, [long]$Table = 0x80021C60)
. "$PSScriptRoot\gcmem.ps1"
$dpid = (Get-TestPid)
[GCMem]::Open($dpid, 'GFTEMD') | Out-Null
$rows = @()
for ($e = $Table; ; $e += 12) {
	$ret = [GCMem]::U32($e)
	if ($ret -eq 0) { break }
	$rows += [pscustomobject]@{ Entry = $e; Site = '{0:X8}' -f ($ret - 4); Anchor = [GCMem]::U32($e + 4); Calls = [GCMem]::U32($e + 8) }
}
if ($Reset) { foreach ($r in $rows) { [GCMem]::W32($r.Entry + 8, 0) | Out-Null } }
foreach ($s in $Set) {
	$site, $anchor = $s -split '='
	$r = $rows | Where-Object { $_.Site -eq $site.ToUpper() }
	if (-not $r) { "no caller $site"; continue }
	[GCMem]::W32($r.Entry + 4, [uint32]$anchor) | Out-Null
	"set $site -> $anchor"
}
if ($List) { $rows | ForEach-Object { '{0}  anchor {1}  calls {2}' -f $_.Site, [GCMem]::U32($_.Entry + 4), [GCMem]::U32($_.Entry + 8) } }

