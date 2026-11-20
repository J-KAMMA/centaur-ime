# Centaur IME Korean を入れる（試用版）。管理者の PowerShell で、このフォルダから実行する:
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
# 入れる場所: C:\Program Files\CentaurIME\Korean（DLL）、%LOCALAPPDATA%\CentaurIME\korean（表）
# 入れた後、「設定 → 時刻と言語 → 言語と地域」で韓国語を足し、その「キーボードの追加」で
# 「Centaur IME Korean」を選ぶ（入れただけでは今の入力方式は変わらない）。
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$dest = Join-Path $env:ProgramFiles 'CentaurIME\Korean'
$data = Join-Path $env:LOCALAPPDATA 'CentaurIME\korean'
New-Item -ItemType Directory -Force $dest | Out-Null
New-Item -ItemType Directory -Force $data | Out-Null
Copy-Item (Join-Path $here 'x64\centaur_tip_ko.dll') (Join-Path $dest 'centaur_tip_ko64.dll') -Force
Copy-Item (Join-Path $here 'x86\centaur_tip_ko.dll') (Join-Path $dest 'centaur_tip_ko32.dll') -Force
Copy-Item (Join-Path $here 'ko-detect.tsv') (Join-Path $data 'ko-detect.tsv') -Force
# ブランド名の正式な書き方（無くても動く）
if (Test-Path (Join-Path $here 'casing.tsv')) { Copy-Item (Join-Path $here 'casing.tsv') (Join-Path $data 'casing.tsv') -Force }
& "$env:windir\System32\regsvr32.exe" /s (Join-Path $dest 'centaur_tip_ko64.dll')
if ($LASTEXITCODE -ne 0) { throw '64 ビットの登録に失敗' }
& "$env:windir\SysWOW64\regsvr32.exe" /s (Join-Path $dest 'centaur_tip_ko32.dll')
if ($LASTEXITCODE -ne 0) { throw '32 ビットの登録に失敗' }
Write-Output '入れました。設定で韓国語の「キーボードの追加」から「Centaur IME Korean」を選んでください。'
