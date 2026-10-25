param([string]$OutPath, [int]$X = 0, [int]$Y = 0, [int]$W = 700, [int]$H = 500)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$crop = New-Object System.Drawing.Bitmap $W, $H
$g2 = [System.Drawing.Graphics]::FromImage($crop)
$g2.DrawImage($bmp, (New-Object System.Drawing.Rectangle 0,0,$W,$H), (New-Object System.Drawing.Rectangle $X,$Y,$W,$H), [System.Drawing.GraphicsUnit]::Pixel)
$crop.Save($OutPath, [System.Drawing.Imaging.ImageFormat]::Png)
$g2.Dispose(); $crop.Dispose(); $g.Dispose(); $bmp.Dispose()
Write-Output "captured $OutPath"
