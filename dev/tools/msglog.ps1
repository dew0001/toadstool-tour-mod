# Read the message lookup log of a debug_patch.py "messages" build: (code that showed the text, message id).
. "$PSScriptRoot\gcmem.ps1"
[GCMem]::Open((Get-TestPid), 'GFTEMD') | Out-Null
$log = 0x8005DAFC
$n = [GCMem]::U32($log)
"count $n"
for ($i = 0; $i -lt $n; $i++) { '{0:X8} id 0x{1:X}' -f [GCMem]::U32($log + 4 + 8 * $i), [GCMem]::U32($log + 8 + 8 * $i) }
