param([int]$TargetPid)
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinEnum {
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder text, int count);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    public struct RECT { public int Left, Top, Right, Bottom; }
    public static void List() {
        EnumWindows(delegate(IntPtr hWnd, IntPtr lParam) {
            uint pid; GetWindowThreadProcessId(hWnd, out pid);
            if (pid == $TargetPid) {
                var sb = new System.Text.StringBuilder(256);
                GetWindowText(hWnd, sb, 256);
                RECT r; GetWindowRect(hWnd, out r);
                Console.WriteLine((IsWindowVisible(hWnd) ? "VISIBLE" : "hidden ") + " | " + sb.ToString() + " | rect=(" + r.Left + "," + r.Top + ")-(" + r.Right + "," + r.Bottom + ")");
            }
            return true;
        }, IntPtr.Zero);
    }
}
"@
[WinEnum]::List()
