$original_path = (Get-Location).Path
# Set the location to the directory where this script resides
Set-Location $PSScriptRoot

Write-Host "Starting sync for THz_system..." -ForegroundColor Cyan
git add . 2>$null
git commit -m "Auto sync $([datetime]::Now.ToString('yyyy-MM-dd HH:mm:ss'))" | Out-Null

Write-Host "Pulling latest updates from GitHub..." -ForegroundColor Yellow
git pull origin main --rebase

Write-Host "Pushing local version to GitHub..." -ForegroundColor Yellow
git push origin main

Set-Location $original_path
Write-Host "THz_system sync completed!" -ForegroundColor Green
