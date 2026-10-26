# For each caller: pin it, grab a crop (fractions of the screen), unpin. Tiles the crops into one labeled sheet.
param([string[]]$Sites, [int]$Anchor = 1, [double[]]$Crop = @(0, 0, 0.5, 0.35), [string]$Sheet = "$PSScriptRoot\hudcrop.png")
. "$PSScriptRoot\gcmem.ps1"
Add-Type -AssemblyName System.Drawing, System.Windows.Forms
$dpid = (Get-TestPid)
[GCMem]::Open($dpid, 'GFTEMD') | Out-Null
$entries = @{}
for ($e = 0x80021C60; [GCMem]::U32($e) -ne 0; $e += 12) { $entries['{0:X8}' -f ([GCMem]::U32($e) - 4)] = $e }
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$cx = [int]($Crop[0] * $screen.Width); $cy = [int]($Crop[1] * $screen.Height)
$cw = [int](($Crop[2] - $Crop[0]) * $screen.Width); $ch = [int](($Crop[3] - $Crop[1]) * $screen.Height)
$tw = 480; $th = [int]($tw * $ch / $cw)
$labels = @('base') + $Sites
$sheetBmp = New-Object System.Drawing.Bitmap ($tw * 2), ($th * [math]::Ceiling($labels.Count / 2))
$sg = [System.Drawing.Graphics]::FromImage($sheetBmp)
$font = New-Object System.Drawing.Font 'Arial', 11
$i = 0
foreach ($s in $labels) {
	$e = if ($s -ne 'base') { $entries[$s.ToUpper()] } else { $null }
	if ($e) { $old = [GCMem]::U32($e + 4); [GCMem]::W32($e + 4, [uint32]$Anchor) | Out-Null; Start-Sleep -Milliseconds 150 }
	$bmp = New-Object System.Drawing.Bitmap $cw, $ch
	$g = [System.Drawing.Graphics]::FromImage($bmp)
	$g.CopyFromScreen($screen.X + $cx, $screen.Y + $cy, 0, 0, (New-Object System.Drawing.Size $cw, $ch))
	if ($e) { [GCMem]::W32($e + 4, $old) | Out-Null }
	$x = ($i % 2) * $tw; $y = [math]::Floor($i / 2) * $th
	$sg.DrawImage($bmp, $x, $y, $tw, $th)
	$sg.FillRectangle([System.Drawing.Brushes]::Black, $x, $y, 90, 18)
	$sg.DrawString($s, $font, [System.Drawing.Brushes]::Yellow, $x + 2, $y + 1)
	$g.Dispose(); $bmp.Dispose(); $i++
}
$sheetBmp.Save($Sheet, [System.Drawing.Imaging.ImageFormat]::Png)
"sheet: $Sheet"

