param([switch]$SkipInstaller)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$Python = Join-Path (Get-Location) '.venv\Scripts\python.exe'
if (!(Test-Path $Python)) { throw 'Run setup-windows.bat first.' }
& $Python -m pip install 'pyinstaller>=6.11,<7'
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller installation failed.' }
& $Python -m PyInstaller --noconfirm --clean packaging/VocalStudio.spec
if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }
$App = Join-Path (Get-Location) 'dist\VocalStudio\VocalStudio.exe'
$Report = Join-Path (Get-Location) 'dist\smoke-test.json'
$Smoke = Start-Process -FilePath $App -ArgumentList @('--self-test', "`"$Report`"") -PassThru
if (!$Smoke.WaitForExit(120000)) { $Smoke.Kill(); throw 'Packaged smoke test timed out.' }
if ($Smoke.ExitCode -ne 0 -or !(Test-Path $Report)) { throw 'Packaged application did not pass smoke test.' }
$Result = Get-Content $Report -Raw | ConvertFrom-Json
if (!$Result.ok) { throw $Result.error }
Compress-Archive -Path dist\VocalStudio -DestinationPath dist\VocalStudio-0.3.0-windows-x64.zip -Force
if (!$SkipInstaller) {
    $Compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($Compiler) { $Iscc = $Compiler.Source }
    else { $Iscc = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe' }
    if (!(Test-Path $Iscc)) { throw 'Install Inno Setup 6, or run with -SkipInstaller to build only the portable app.' }
    & $Iscc packaging\installer.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
}
Write-Host 'Build and packaged-app check passed. Files are in dist/.'
