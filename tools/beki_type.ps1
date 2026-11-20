# 一般的な IME との比べ: 入っている IME（BekiIME）に、本物のキーを送って文を打ち込み、確定した文を読む（測るだけ）。
#   pwsh tools/beki_type.ps1 -In in.txt -Out raw.tsv [-KeyMs 15] [-SettleMs 400]
# 入力は 1 行 1 文のローマ字（小文字、数字、. , ! ? -）。窓の上の 1 行の入力欄に、1 文ずつ
#   変換キー（IME 入）→ ローマ字のキー → 空白（変換）→ Enter（確定）
# と送り、入力欄の文字を読んで「ローマ字<TAB>確定した文」を書く。次の文の前に入力欄を空にする。
# キーは SendInput の仮想キー（文字そのものではなく、IME がローマ字として受け取る形）で送る。
param(
  [Parameter(Mandatory)] [string]$In,
  [Parameter(Mandatory)] [string]$Out,
  [int]$KeyMs = 15,
  [int]$SettleMs = 400,
  [int]$Limit = 0
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

public static class KeySender {
  [StructLayout(LayoutKind.Sequential)] struct KEYBDINPUT { public ushort wVk; public ushort wScan; public uint dwFlags; public uint time; public IntPtr dwExtraInfo; }
  [StructLayout(LayoutKind.Sequential)] struct MOUSEINPUT { public int dx; public int dy; public uint mouseData; public uint dwFlags; public uint time; public IntPtr dwExtraInfo; }
  [StructLayout(LayoutKind.Explicit)] struct UNION { [FieldOffset(0)] public MOUSEINPUT mi; [FieldOffset(0)] public KEYBDINPUT ki; }
  [StructLayout(LayoutKind.Sequential)] struct INPUT { public uint type; public UNION u; }
  [DllImport("user32.dll", SetLastError = true)] static extern uint SendInput(uint n, INPUT[] inputs, int size);
  [DllImport("user32.dll")] static extern uint MapVirtualKey(uint code, uint mapType);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);

  static void One(ushort vk, bool up) {
    var i = new INPUT[1];
    i[0].type = 1;
    i[0].u.ki.wVk = vk;
    i[0].u.ki.wScan = (ushort)MapVirtualKey(vk, 0);
    i[0].u.ki.dwFlags = up ? 2u : 0u;
    if (SendInput(1, i, Marshal.SizeOf(typeof(INPUT))) != 1) throw new Exception("SendInput " + Marshal.GetLastWin32Error());
  }
  public static void Tap(ushort vk, bool shift, int ms) {
    if (shift) One(0x10, false);
    One(vk, false); One(vk, true);
    if (shift) One(0x10, true);
    Thread.Sleep(ms);
  }
  // ローマ字の 1 文字を仮想キーに（US・JIS どちらの配列でも同じ所だけ使う）
  public static bool Vk(char c, out ushort vk, out bool shift) {
    shift = false; vk = 0;
    if (c >= 'a' && c <= 'z') { vk = (ushort)(c - 'a' + 0x41); return true; }
    if (c >= '0' && c <= '9') { vk = (ushort)(c - '0' + 0x30); return true; }
    switch (c) {
      case '.': vk = 0xBE; return true;
      case ',': vk = 0xBC; return true;
      case '-': vk = 0xBD; return true;
      case '!': vk = 0x31; shift = true; return true;
      case '?': vk = 0xBF; shift = true; return true;
    }
    return false;
  }
}

public class TypingForm : Form {
  public TextBox Box = new TextBox();
  public TypingForm() {
    Text = "beki-measure"; Width = 900; Height = 120; TopMost = true;
    Box.Dock = DockStyle.Fill; Box.Font = new System.Drawing.Font("Yu Gothic UI", 14);
    Controls.Add(Box);
  }

  // 窓は別の糸（STA）で動かし、PowerShell の糸からは下の関数で触る（PowerShell の台本は別の糸で動かせない）
  static TypingForm form;
  public static void Start() {
    var ready = new ManualResetEvent(false);
    var t = new Thread(() => { form = new TypingForm(); form.Shown += (s, e) => ready.Set(); Application.Run(form); });
    t.SetApartmentState(ApartmentState.STA);
    t.IsBackground = true;
    t.Start();
    if (!ready.WaitOne(30000)) throw new Exception("window did not show");
  }
  public static void ClearAndFocus() {
    form.Invoke((MethodInvoker)(() => { form.Activate(); form.Box.Clear(); form.Box.Focus(); }));
    KeySender.SetForegroundWindow(form.Handle);
  }
  public static string Read() { return (string)form.Invoke((Func<string>)(() => form.Box.Text)); }
  public static void Stop() { form.Invoke((MethodInvoker)(() => form.Close())); }
}
'@ -ReferencedAssemblies System.Windows.Forms, System.Drawing

[TypingForm]::Start()

$lines = Get-Content -LiteralPath $In -Encoding utf8 | Where-Object { $_ -ne '' }
if ($Limit -gt 0) { $lines = $lines | Select-Object -First $Limit }
$writer = [IO.StreamWriter]::new($Out, $false, [Text.UTF8Encoding]::new($false))
$n = 0
foreach ($r in $lines) {
  [TypingForm]::ClearAndFocus()
  Start-Sleep -Milliseconds 50
  [KeySender]::Tap(0x1C, $false, 80)   # VK_CONVERT（変換キー）: BekiIME では IME 入（「あ」）
  foreach ($c in $r.ToCharArray()) {
    $vk = [uint16]0; $shift = $false
    if ([KeySender]::Vk($c, [ref]$vk, [ref]$shift)) { [KeySender]::Tap($vk, $shift, $KeyMs) }
  }
  Start-Sleep -Milliseconds $SettleMs
  [KeySender]::Tap(0x20, $false, $SettleMs)   # 空白: 変換
  [KeySender]::Tap(0x0D, $false, 150)         # Enter: 確定
  $text = ([TypingForm]::Read()) -replace "[`r`n]", ''
  $writer.WriteLine("$r`t$text")
  $writer.Flush()
  $n++
  if ($n -le 3 -or $n % 100 -eq 0) { Write-Host "$n`t$r`t$text" }
}
$writer.Close()
[TypingForm]::Stop()
