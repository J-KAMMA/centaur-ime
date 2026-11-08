# Centaur IME Chinese を外す。管理者の PowerShell で実行する:
#   powershell -ExecutionPolicy Bypass -File .\uninstall.ps1
# 利用者の設定と学習（%LOCALAPPDATA%\CentaurIME\chinese）は残す。要らなければ手で消す（ごみ箱へ）。
$ErrorActionPreference = 'Continue'
$dest = Join-Path $env:ProgramFiles 'CentaurIME\Chinese'
& "$env:windir\System32\regsvr32.exe" /s /u (Join-Path $dest 'centaur_tip_zh64.dll')
& "$env:windir\SysWOW64\regsvr32.exe" /s /u (Join-Path $dest 'centaur_tip_zh32.dll')
# 使っているアプリが DLL を開いたままのことがあるので、消せないときは次に起動したときに消す
foreach ($f in 'centaur_tip_zh64.dll', 'centaur_tip_zh32.dll', 'x64\rime.dll', 'x86\rime.dll') {
  $p = Join-Path $dest $f
  try { Remove-Item $p -Force -ErrorAction Stop } catch { Write-Output "使用中のため残しました: $p（再起動後に消せます）" }
}
Write-Output '外しました。'
