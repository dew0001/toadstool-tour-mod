# Read the sound effect log of a debug_patch.py "sfx" build (every sfx ID started, in order) or, with -Pairs, of a
# "voices" build (every sfx ID and voice group asked of voiceFXcall), with the group each ID belongs to.
param([switch]$Reset, [switch]$Pairs, [uint32]$At = 2147867388)   # 0x8005DAFC   # -At 0x80057A14 for a "plays" build
. "$PSScriptRoot\gcmem.ps1"
[GCMem]::Open((Get-TestPid), 'GFTEMD') | Out-Null
$log = $At
if ($Reset) { [GCMem]::W32($log, 0) | Out-Null; 'log cleared'; return }
# MusyX groups (main.dol 0x80137308: name, first file, sfx count, first sfx, group), read live
$groups = @()
for ($g = 0; $g -lt 37; $g++) {
	$e = 0x80137308 + 0x14 * $g
	$p = [GCMem]::U32($e); $name = ''
	for ($k = 0; $k -lt 16; $k++) { $c = [GCMem]::U8($p + $k); if ($c -eq 0) { break }; $name += [char]$c }
	$groups += [pscustomobject]@{ Name = $name; First = [GCMem]::U32($e + 12); Count = [GCMem]::U32($e + 8) }
}
$n = [GCMem]::U32($log)
"count $n"
for ($i = 0; $i -lt $n; $i++) {
	if ($Pairs) {
		$id = [GCMem]::U32($log + 4 + 8 * $i); $asked = [GCMem]::U32($log + 8 + 8 * $i)
		$g = $groups | Where-Object { $id -ge $_.First -and $id -lt $_.First + $_.Count } | Select-Object -First 1
		'{0,3} 0x{1:X3} asked of {2} {3}' -f $i, $id, $(if ($asked -lt 37) { "$asked ($($groups[$asked].Name))" } else { $asked }), $(if ($g) { "= $($g.Name) +$($id - $g.First)" } else { '' })
		continue
	}
	$id = [GCMem]::U32($log + 4 + 4 * $i)
	$g = $groups | Where-Object { $id -ge $_.First -and $id -lt $_.First + $_.Count } | Select-Object -First 1
	'{0,3} 0x{1:X3} {2}' -f $i, $id, $(if ($g) { "$($g.Name) +$($id - $g.First)" } else { '' })
}
