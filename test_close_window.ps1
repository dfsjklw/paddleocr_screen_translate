Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class WinAPI {
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll", CharSet=CharSet.Auto)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
}
"@

$targetPid = 3092
$mainHwnd = [IntPtr]::Zero

$enumCb = [WinAPI+EnumWindowsProc]{
    param($hWnd, $lParam)
    $procId = 0
    [WinAPI]::GetWindowThreadProcessId($hWnd, [ref]$procId)
    if ($procId -eq $targetPid) {
        $sb = New-Object System.Text.StringBuilder 256
        [WinAPI]::GetWindowText($hWnd, $sb, 256)
        $text = $sb.ToString()
        if ($text -ne "") {
            Write-Output "Found window: hWnd=$hWnd title='$text'"
            Set-Variable -Name "hwnd" -Value $hWnd -Scope 2
        }
    }
    return $true
}

[void][WinAPI]::EnumWindows($enumCb, [IntPtr]::Zero)

if ($hwnd -ne $null -and $hwnd -ne [IntPtr]::Zero) {
    Write-Output "Sending WM_CLOSE to window..."
    $WM_CLOSE = 0x0010
    [WinAPI]::PostMessage($hwnd, $WM_CLOSE, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
    Write-Output "WM_CLOSE sent. Waiting 5s..."
    Start-Sleep -Seconds 5
    Write-Output "Done waiting."
} else {
    Write-Output "No visible window found for PID $targetPid"
}
