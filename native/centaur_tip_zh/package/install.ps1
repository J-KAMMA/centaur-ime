# Centaur IME Chinese を入れる（試用版）。管理者の PowerShell で、このフォルダから実行する:
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
# 入れる場所: C:\Program Files\CentaurIME\Chinese（DLL、Rime、辞書）、%LOCALAPPDATA%\CentaurIME\chinese\rime（利用者の設定と学習）
# 入れた後、「設定 → 時刻と言語 → 言語と地域」で中国語（簡体字、中国）を足し、その「キーボードの追加」で
# 「Centaur IME Chinese」を選ぶ（入れただけでは今の入力方式は変わらない）。
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$dest = Join-Path $env:ProgramFiles 'CentaurIME\Chinese'
New-Item -ItemType Directory -Force (Join-Path $dest 'x64'), (Join-Path $dest 'x86') | Out-Null
Copy-Item (Join-Path $here 'x64\centaur_tip_zh.dll') (Join-Path $dest 'centaur_tip_zh64.dll') -Force
Copy-Item (Join-Path $here 'x86\centaur_tip_zh.dll') (Join-Path $dest 'centaur_tip_zh32.dll') -Force
Copy-Item (Join-Path $here 'x64\rime.dll') (Join-Path $dest 'x64\rime.dll') -Force
Copy-Item (Join-Path $here 'x86\rime.dll') (Join-Path $dest 'x86\rime.dll') -Force
Copy-Item (Join-Path $here 'data') $dest -Recurse -Force
& "$env:windir\System32\regsvr32.exe" /s (Join-Path $dest 'centaur_tip_zh64.dll')
if ($LASTEXITCODE -ne 0) { throw '64 ビットの登録に失敗' }
& "$env:windir\SysWOW64\regsvr32.exe" /s (Join-Path $dest 'centaur_tip_zh32.dll')
if ($LASTEXITCODE -ne 0) { throw '32 ビットの登録に失敗' }
Write-Output '入れました。設定で中国語の「キーボードの追加」から「Centaur IME Chinese」を選んでください。'
