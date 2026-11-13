"""Новогодний снег поверх рабочего стола Windows.

Снегопад — три слоя заранее нарисованных снежинок в прозрачных окнах (UpdateLayeredWindow),
в каждом кадре окна только сдвигаются, поэтому процессор почти не нагружается.
Клики проходят насквозь. Сугробы копятся по реальному контуру иконок рабочего стола
и на панели задач. Управление — снежинка в трее (двойной клик — настройки,
правая кнопка — пауза / стряхнуть / выход). Сам снег использует только стандартную
библиотеку Python (tkinter + ctypes); окну настроек нужен PySide6.

Запуск с --autostart — сразу в трей, без окна настроек.
SNOW_DEBUG=1 — печатать реальный FPS в stderr.
"""
import ctypes
import ctypes.wintypes as wt
import math
import os
import random
import subprocess
import sys
import time
import tkinter as tk

import config

# ---------------------------------------------------------------- константы
# (то, что меняет пользователь, лежит в config.py / окне настроек)
COL = 3                      # ширина столбика сугроба, px
SCAN_EVERY = 1.0             # как часто перечитывать иконки/панель, с
HERE = os.path.dirname(os.path.abspath(__file__))
DEBUG = bool(os.environ.get('SNOW_DEBUG'))   # печатать реальный FPS в stderr

# ---------------------------------------------------------------- WinAPI
user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
shell32 = ctypes.WinDLL('shell32', use_last_error=True)
gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)
winmm = ctypes.WinDLL('winmm')

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


def sig(fn, args, res):
    fn.argtypes = args
    fn.restype = res


sig(user32.FindWindowW, [wt.LPCWSTR, wt.LPCWSTR], wt.HWND)
sig(user32.FindWindowExW, [wt.HWND, wt.HWND, wt.LPCWSTR, wt.LPCWSTR], wt.HWND)
sig(user32.SendMessageTimeoutW, [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM, wt.UINT, wt.UINT,
                                 ctypes.POINTER(ctypes.c_size_t)], LRESULT)
sig(user32.GetWindowThreadProcessId, [wt.HWND, ctypes.POINTER(wt.DWORD)], wt.DWORD)
sig(user32.MapWindowPoints, [wt.HWND, wt.HWND, ctypes.c_void_p, wt.UINT], ctypes.c_int)
sig(user32.GetWindowRect, [wt.HWND, ctypes.POINTER(wt.RECT)], wt.BOOL)
sig(user32.IsWindow, [wt.HWND], wt.BOOL)
sig(user32.IsWindowVisible, [wt.HWND], wt.BOOL)
sig(user32.WindowFromPoint, [wt.POINT], wt.HWND)
sig(user32.GetAncestor, [wt.HWND, wt.UINT], wt.HWND)
sig(user32.GetParent, [wt.HWND], wt.HWND)
sig(user32.GetWindowLongPtrW, [wt.HWND, ctypes.c_int], ctypes.c_ssize_t)
sig(user32.SetWindowLongPtrW, [wt.HWND, ctypes.c_int, ctypes.c_ssize_t], ctypes.c_ssize_t)
sig(user32.SetWindowPos, [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                          ctypes.c_int, wt.UINT], wt.BOOL)
sig(user32.DefWindowProcW, [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM], LRESULT)
sig(user32.CreateWindowExW, [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int,
                             ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU,
                             wt.HINSTANCE, wt.LPVOID], wt.HWND)
sig(user32.DestroyWindow, [wt.HWND], wt.BOOL)
sig(user32.CreatePopupMenu, [], wt.HMENU)
sig(user32.AppendMenuW, [wt.HMENU, wt.UINT, ctypes.c_size_t, wt.LPCWSTR], wt.BOOL)
sig(user32.TrackPopupMenu, [wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                            wt.HWND, wt.LPVOID], wt.BOOL)
sig(user32.DestroyMenu, [wt.HMENU], wt.BOOL)
sig(user32.SetForegroundWindow, [wt.HWND], wt.BOOL)
sig(user32.PostMessageW, [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM], wt.BOOL)
sig(user32.GetCursorPos, [ctypes.POINTER(wt.POINT)], wt.BOOL)
sig(user32.RegisterWindowMessageW, [wt.LPCWSTR], wt.UINT)
sig(user32.CreateIconIndirect, [ctypes.c_void_p], wt.HICON)
sig(user32.DestroyIcon, [wt.HICON], wt.BOOL)
sig(kernel32.OpenProcess, [wt.DWORD, wt.BOOL, wt.DWORD], wt.HANDLE)
sig(kernel32.VirtualAllocEx, [wt.HANDLE, wt.LPVOID, ctypes.c_size_t, wt.DWORD, wt.DWORD], wt.LPVOID)
sig(kernel32.VirtualFreeEx, [wt.HANDLE, wt.LPVOID, ctypes.c_size_t, wt.DWORD], wt.BOOL)
sig(kernel32.WriteProcessMemory, [wt.HANDLE, wt.LPVOID, wt.LPCVOID, ctypes.c_size_t, ctypes.c_void_p], wt.BOOL)
sig(kernel32.ReadProcessMemory, [wt.HANDLE, wt.LPCVOID, wt.LPVOID, ctypes.c_size_t, ctypes.c_void_p], wt.BOOL)
sig(kernel32.CloseHandle, [wt.HANDLE], wt.BOOL)
sig(kernel32.GetModuleHandleW, [wt.LPCWSTR], wt.HMODULE)
sig(kernel32.CreateMutexW, [wt.LPVOID, wt.BOOL, wt.LPCWSTR], wt.HANDLE)
sig(gdi32.CreateDIBSection, [wt.HDC, ctypes.c_void_p, wt.UINT, ctypes.POINTER(ctypes.c_void_p),
                             wt.HANDLE, wt.DWORD], wt.HBITMAP)
sig(gdi32.CreateBitmap, [ctypes.c_int, ctypes.c_int, wt.UINT, wt.UINT, wt.LPVOID], wt.HBITMAP)
sig(gdi32.DeleteObject, [wt.HGDIOBJ], wt.BOOL)


def dpi_aware():
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass


def send(hwnd, msg, wp, lp):
    res = ctypes.c_size_t(0)
    ok = user32.SendMessageTimeoutW(hwnd, msg, wp, lp, 0x0002, 200, ctypes.byref(res))  # ABORTIFHUNG
    return res.value if ok else 0


# ---------------------------------------------------------------- рабочий стол
def find_desktop_listview():
    defview = None
    progman = user32.FindWindowW('Progman', None)
    if progman:
        defview = user32.FindWindowExW(progman, None, 'SHELLDLL_DefView', None)
    if not defview:  # после смены обоев DefView бывает внутри одного из WorkerW
        w = None
        while True:
            w = user32.FindWindowExW(None, w, 'WorkerW', None)
            if not w:
                break
            defview = user32.FindWindowExW(w, None, 'SHELLDLL_DefView', None)
            if defview:
                break
    if not defview:
        return None
    return user32.FindWindowExW(defview, None, 'SysListView32', None)


class DesktopIcons:
    """Читает прямоугольники иконок из ListView проводника (чужой процесс)."""

    def __init__(self):
        self.lv = self.proc = self.mem = None
        self.root = None

    def close(self):
        if self.proc:
            if self.mem:
                kernel32.VirtualFreeEx(self.proc, self.mem, 0, 0x8000)
            kernel32.CloseHandle(self.proc)
        self.lv = self.proc = self.mem = None

    def _open(self):
        lv = find_desktop_listview()
        if not lv:
            return False
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(lv, ctypes.byref(pid))
        proc = kernel32.OpenProcess(0x0008 | 0x0010 | 0x0020, False, pid.value)
        if not proc:
            return False
        mem = kernel32.VirtualAllocEx(proc, None, 4096, 0x3000, 0x04)
        if not mem:
            kernel32.CloseHandle(proc)
            return False
        self.lv, self.proc, self.mem = lv, proc, mem
        self.root = user32.GetAncestor(lv, 2)  # GA_ROOT: Progman или WorkerW
        return True

    def rects(self):
        if not self.lv or not user32.IsWindow(self.lv):
            self.close()
            if not self._open():
                return []
        if not user32.IsWindowVisible(self.lv):
            return []
        n = min(send(self.lv, 0x1004, 0, 0), 400)  # LVM_GETITEMCOUNT
        out = []
        r = wt.RECT()
        pts = (wt.POINT * 2)()
        for i in range(n):
            r.left, r.top, r.right, r.bottom = 1, 0, 0, 0  # LVIR_ICON
            kernel32.WriteProcessMemory(self.proc, self.mem, ctypes.byref(r), 16, None)
            if not send(self.lv, 0x100E, i, self.mem):  # LVM_GETITEMRECT
                continue
            kernel32.ReadProcessMemory(self.proc, self.mem, ctypes.byref(r), 16, None)
            pts[0].x, pts[0].y, pts[1].x, pts[1].y = r.left, r.top, r.right, r.bottom
            user32.MapWindowPoints(self.lv, None, pts, 2)
            out.append((pts[0].x, pts[0].y, pts[1].x, pts[1].y))
        return out


    def texts(self, n):
        """Подписи иконок (LVM_GETITEMTEXTW) — чтобы узнать, чья это иконка."""
        if not self.proc:
            return []
        out = []
        it = LVITEMW()
        it.cchTextMax = 260
        it.pszText = self.mem + 1024
        buf = ctypes.create_unicode_buffer(260)
        for i in range(n):
            kernel32.WriteProcessMemory(self.proc, self.mem, ctypes.byref(it), ctypes.sizeof(it), None)
            ln = send(self.lv, 0x1073, i, self.mem)  # LVM_GETITEMTEXTW
            buf.value = ''
            if ln:
                kernel32.ReadProcessMemory(self.proc, self.mem + 1024, buf, min(ln + 1, 260) * 2, None)
            out.append(buf.value)
        return out


class LVITEMW(ctypes.Structure):
    _fields_ = [('mask', wt.UINT), ('iItem', ctypes.c_int), ('iSubItem', ctypes.c_int),
                ('state', wt.UINT), ('stateMask', wt.UINT), ('pszText', ctypes.c_void_p),
                ('cchTextMax', ctypes.c_int), ('iImage', ctypes.c_int), ('lParam', wt.LPARAM),
                ('iIndent', ctypes.c_int), ('iGroupId', ctypes.c_int), ('cColumns', wt.UINT),
                ('puColumns', ctypes.c_void_p), ('piColFmt', ctypes.c_void_p), ('iGroup', ctypes.c_int)]


# ---------------------------------------------------------------- силуэты иконок
class SHFILEINFOW(ctypes.Structure):
    _fields_ = [('hIcon', wt.HICON), ('iIcon', ctypes.c_int), ('dwAttributes', wt.DWORD),
                ('szDisplayName', wt.WCHAR * 260), ('szTypeName', wt.WCHAR * 80)]


sig(shell32.SHGetFileInfoW, [ctypes.c_void_p, wt.DWORD, ctypes.POINTER(SHFILEINFOW), wt.UINT, wt.UINT],
    ctypes.c_size_t)
sig(shell32.SHParseDisplayName, [wt.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), wt.ULONG,
                                 ctypes.c_void_p], ctypes.c_long)
sig(shell32.SHGetFolderPathW, [wt.HWND, ctypes.c_int, wt.HANDLE, wt.DWORD, wt.LPWSTR], ctypes.c_long)
sig(shell32.SHGetImageList, [ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)], ctypes.c_long)
sig(user32.GetIconInfo, [wt.HICON, ctypes.c_void_p], wt.BOOL)
sig(user32.GetDC, [wt.HWND], wt.HDC)
sig(user32.ReleaseDC, [wt.HWND, wt.HDC], ctypes.c_int)
sig(gdi32.GetDIBits, [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT],
    ctypes.c_int)
sig(ctypes.windll.ole32.CoTaskMemFree, [ctypes.c_void_p], None)

SHIL_EXTRALARGE = 2   # 48x48 — как «обычные» значки рабочего стола
SIL = 48
VIRTUAL_ITEMS = ('20D04FE0-3AEA-1069-A2D8-08002B30309D',  # Этот компьютер
                 '645FF040-5081-101B-9F08-00AA002F954E',  # Корзина
                 'F02C1A0D-BE21-4350-88B0-7367FC96EF3C',  # Сеть
                 '59031A47-3F72-44A7-89C5-5595FE6B30EE',  # Папка пользователя
                 '5399E694-6CE5-4D6C-8FCE-1D8870FDCBA0')  # Панель управления


class IconShapes:
    """Имя иконки -> верхний контур её картинки: список из SIL значений (строка или None)."""

    def __init__(self):
        self.cache = {}
        self.names = {}      # отображаемое имя -> индекс в системном списке значков
        self.names_at = 0
        self.iml = None
        ctypes.windll.ole32.CoInitialize(None)  # без COM ярлыки отдают значок «документ»
        # GUID хранится little-endian по первым трём полям
        g = bytes.fromhex('46EB5926582E40179FDFE8998DAA0950')
        iid = (ctypes.c_ubyte * 16).from_buffer_copy(g[3::-1] + g[5:3:-1] + g[7:5:-1] + g[8:])
        p = ctypes.c_void_p()
        if shell32.SHGetImageList(SHIL_EXTRALARGE, ctypes.byref(iid), ctypes.byref(p)) == 0:
            self.iml = p

    def _refresh_names(self):
        names = {}
        sfi = SHFILEINFOW()
        flags = 0x200 | 0x4000  # DISPLAYNAME | SYSICONINDEX
        import os
        for csidl in (0x10, 0x19):  # рабочий стол пользователя и общий
            buf = ctypes.create_unicode_buffer(260)
            if shell32.SHGetFolderPathW(None, csidl, None, 0, buf) != 0:
                continue
            try:
                entries = os.listdir(buf.value)
            except OSError:
                continue
            for e in entries:
                if e.lower() == 'desktop.ini':
                    continue
                full = os.path.join(buf.value, e)
                if shell32.SHGetFileInfoW(full, 0, ctypes.byref(sfi), ctypes.sizeof(sfi), flags):
                    names.setdefault(sfi.szDisplayName, sfi.iIcon)
        for clsid in VIRTUAL_ITEMS:
            pidl = ctypes.c_void_p()
            if shell32.SHParseDisplayName('::{%s}' % clsid, None, ctypes.byref(pidl), 0, None) == 0:
                if shell32.SHGetFileInfoW(pidl, 0, ctypes.byref(sfi), ctypes.sizeof(sfi), flags | 0x8):
                    names.setdefault(sfi.szDisplayName, sfi.iIcon)
                ctypes.windll.ole32.CoTaskMemFree(pidl)
        self.names = names

    def contour(self, name):
        if name in self.cache:
            return self.cache[name]
        if self.iml is None:
            return None
        if name not in self.names and time.time() - self.names_at > 3:
            self.names_at = time.time()
            self._refresh_names()
        idx = self.names.get(name)
        prof = self._contour_of(idx) if idx is not None else None
        if prof is not None:
            self.cache[name] = prof
        return prof

    def _contour_of(self, idx):
        # IImageList::GetIcon — 11-й метод в vtable
        vtbl = ctypes.cast(ctypes.cast(self.iml, ctypes.POINTER(ctypes.c_void_p))[0],
                           ctypes.POINTER(ctypes.c_void_p))
        get_icon = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_int, wt.UINT,
                                      ctypes.POINTER(wt.HICON))(vtbl[10])
        hicon = wt.HICON()
        if get_icon(self.iml, idx, 1, ctypes.byref(hicon)) != 0 or not hicon:
            return None
        ii = ICONINFO()
        user32.GetIconInfo(hicon, ctypes.byref(ii))
        bi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), SIL, -SIL, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = (ctypes.c_ubyte * (SIL * SIL * 4))()
        hdc = user32.GetDC(None)
        ok = ii.hbmColor and gdi32.GetDIBits(hdc, ii.hbmColor, 0, SIL, buf, ctypes.byref(bi), 0)
        user32.ReleaseDC(None, hdc)
        for b in (ii.hbmColor, ii.hbmMask):
            if b:
                gdi32.DeleteObject(b)
        user32.DestroyIcon(hicon)
        if not ok:
            return None
        has_alpha = any(buf[i] for i in range(3, len(buf), 4))
        prof = []
        for x in range(SIL):
            top = None
            for y in range(SIL):
                i = (y * SIL + x) * 4
                if (buf[i + 3] > 90) if has_alpha else (buf[i] | buf[i + 1] | buf[i + 2]):
                    top = y
                    break
            prof.append(top)
        return prof


def root_at(x, y):
    h = user32.WindowFromPoint(wt.POINT(int(x), int(y)))
    return user32.GetAncestor(h, 2) if h else None


def taskbars():
    """Прямоугольники видимых панелей задач (основная + на других мониторах)."""
    out = []
    h = user32.FindWindowW('Shell_TrayWnd', None)
    hs = [h] if h else []
    w = None
    while True:
        w = user32.FindWindowExW(None, w, 'Shell_SecondaryTrayWnd', None)
        if not w:
            break
        hs.append(w)
    r = wt.RECT()
    for h in hs:
        if user32.IsWindowVisible(h) and user32.GetWindowRect(h, ctypes.byref(r)):
            if r.right - r.left > r.bottom - r.top:  # горизонтальная
                out.append((h, r.left, r.top, r.right, r.bottom))
    return out


# ---------------------------------------------------------------- игры и исключения
class MONITORINFO(ctypes.Structure):
    _fields_ = [('cbSize', wt.DWORD), ('rcMonitor', wt.RECT), ('rcWork', wt.RECT), ('dwFlags', wt.DWORD)]


sig(user32.GetForegroundWindow, [], wt.HWND)
sig(user32.GetClassNameW, [wt.HWND, wt.LPWSTR, ctypes.c_int], ctypes.c_int)
sig(user32.MonitorFromWindow, [wt.HWND, wt.DWORD], wt.HMONITOR)
sig(user32.GetMonitorInfoW, [wt.HMONITOR, ctypes.POINTER(MONITORINFO)], wt.BOOL)
sig(user32.ShowWindow, [wt.HWND, ctypes.c_int], wt.BOOL)
sig(kernel32.QueryFullProcessImageNameW, [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)], wt.BOOL)
sig(shell32.SHQueryUserNotificationState, [ctypes.POINTER(ctypes.c_int)], ctypes.c_long)

SHELL_CLASSES = {'Progman', 'WorkerW', 'Shell_TrayWnd', 'Shell_SecondaryTrayWnd'}


def exe_of(hwnd):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
    if not h:
        return ''
    buf = ctypes.create_unicode_buffer(520)
    n = wt.DWORD(520)
    ok = kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n))
    kernel32.CloseHandle(h)
    return os.path.basename(buf.value).lower() if ok else ''


class Blocker:
    """Нужно ли сейчас прятать снег: полноэкранная игра/видео или программа из исключений."""

    def __init__(self):
        self.fg = None
        self.exe = ''

    def blocked(self, cfg):
        fg = user32.GetForegroundWindow()
        if not fg:
            return False
        if fg != self.fg:
            self.fg = fg
            self.exe = exe_of(fg)
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(fg, cls, 64)
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
            # рабочий стол, панель задач и само окно снега — это не «игра»
            self.shell = cls.value in SHELL_CLASSES or pid.value == os.getpid()
        if self.shell:
            return False
        if self.exe and self.exe in cfg['excluded']:
            return True
        if cfg['hide_fullscreen']:
            st = ctypes.c_int(0)
            # 3 = Direct3D-игра в эксклюзивном режиме, 4 = режим презентации
            # (2 «что-то на весь экран» не берём: срабатывает и от окна на другом мониторе)
            if shell32.SHQueryUserNotificationState(ctypes.byref(st)) == 0 and st.value in (3, 4):
                return True
            r = wt.RECT()
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if user32.GetWindowRect(fg, ctypes.byref(r)) and user32.GetMonitorInfoW(
                    user32.MonitorFromWindow(fg, 2), ctypes.byref(mi)):
                m = mi.rcMonitor
                if r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom:
                    return True  # окно без рамки на весь монитор (F11, игры в оконном режиме без рамки)
        return False


# ---------------------------------------------------------------- сугробы
class Pile:
    """Сугроб на поверхности: base[i] — экранная Y поверхности в столбике i, h[i] — высота снега.

    Рисует себя сам в маленькое прозрачное окно со сглаживанием (UpdateLayeredWindow).
    Перерисовываются только изменившиеся столбики (lo..hi)."""

    def __init__(self, x0, base, cap):
        self.x0 = x0
        self.base = base
        self.n = n = len(base)
        self.x1 = x0 + n * COL
        edge = max(2, min(n // 5, 12))
        caps = []
        # мягкие холмы: максимальная высота плавно гуляет вдоль сугроба (волны 40–170 px)
        waves = [(random.uniform(0, 6.3), 2 * math.pi / random.uniform(40, 170), random.uniform(0.5, 1))
                 for _ in range(3)]
        wsum = sum(a for _, _, a in waves)
        for i in range(n):
            sx = x0 + (i + 0.5) * COL
            hill = 0.72 + 0.28 * sum(a * math.sin(ph + k * sx) for ph, k, a in waves) / wsum
            # края скруглены: у краёв снега меньше, как шапка
            c = cap * hill * min(1.0, (min(i, n - 1 - i) + 0.6) / edge) ** 0.7
            # на крутых склонах снег не держится
            sl = max(abs(base[i] - base[max(0, i - 1)]), abs(base[min(n - 1, i + 1)] - base[i])) / COL
            caps.append(c * max(0.0, 1 - sl / 1.1))
        self.caps = caps
        self.h = [0.0] * n
        self.lo, self.hi = n, -1      # диапазон изменённых столбиков
        self.unsettled = 0
        self.visible = True
        self.acc = random.random()
        # окно сугроба: от вершины самого высокого возможного снега до поверхности
        self.wx = int(math.floor(x0)) - 1
        self.wy = int(math.floor(min(b - c for b, c in zip(base, caps)))) - 2
        self.ww = int(math.ceil(self.x1)) - self.wx + 2
        self.wh = int(math.ceil(max(base))) - self.wy + 1
        self.buf = bytearray(self.ww * self.wh * 4)
        self.hwnd = None
        self.shown = False

    def _mark(self, a, b):
        if a < self.lo:
            self.lo = a
        if b > self.hi:
            self.hi = b

    def deposit(self, i, amount):
        h, caps, n = self.h, self.caps, self.n
        for d, k in ((0, 1.0), (-1, 0.55), (1, 0.55), (-2, 0.2), (2, 0.2)):
            j = i + d
            if 0 <= j < n:
                h[j] = min(caps[j], h[j] + amount * k)
        self._mark(i - 2, i + 2)
        self.unsettled = 12

    def settle(self):
        # снег ссыпается с более высокого столбика на соседний, если перепад > 1.2 px
        h, caps, b = self.h, self.caps, self.base
        for i in range(self.n - 1):
            d = (b[i + 1] - h[i + 1]) - (b[i] - h[i])  # >0: i выше соседа
            # сыпется только туда, где есть место — иначе снег терялся бы у краёв
            m = 0
            if d > 1.2 and h[i] > 0:
                m = min(h[i], (d - 1.2) * 0.4, caps[i + 1] - h[i + 1])
            elif d < -1.2 and h[i + 1] > 0:
                m = -min(h[i + 1], (-d - 1.2) * 0.4, caps[i] - h[i])
            if m > 0.01 or m < -0.01:
                h[i] -= m
                h[i + 1] += m
                self._mark(i, i + 1)
        self.unsettled -= 1

    def grow(self, dt, fill_time):
        """Тихое накопление, будто снежинки ложатся всё время (полный сугроб ~fill_time с)."""
        self.acc += dt * sum(self.caps) / max(10, fill_time) / 1.5
        while self.acc >= 1:
            self.acc -= 1
            self.deposit(random.randrange(self.n), 0.6)

    # --- отрисовка
    def _edges(self, sx):
        """Верх снега и поверхность в экранной точке sx (линейно между центрами столбиков)."""
        b, h, n = self.base, self.h, self.n
        g = (sx - self.x0) / COL - 0.5
        if g < 0:  # от левого края (снега 0) к центру первого столбика
            f = (sx - self.x0) / (COL * 0.5)
            return b[0] - h[0] * f, b[0]
        if g >= n - 1:
            f = (self.x1 - sx) / (COL * 0.5)
            return b[-1] - h[-1] * min(1.0, f), b[-1]
        j = int(g)
        f = g - j
        top = (b[j] - h[j]) * (1 - f) + (b[j + 1] - h[j + 1]) * f
        return top, b[j] * (1 - f) + b[j + 1] * f

    def render(self):
        if self.hi < self.lo:
            return False
        lo, hi = max(0, self.lo - 1), min(self.n - 1, self.hi + 1)
        self.lo, self.hi = self.n, -1
        w, hgt, buf = self.ww, self.wh, self.buf
        px0 = max(0, int(self.x0 + lo * COL) - self.wx - 1)
        px1 = min(w, int(self.x0 + (hi + 1) * COL) - self.wx + 2)
        zero = bytes(4)
        for px in range(px0, px1):
            sx = self.wx + px + 0.5
            for y in range(hgt):  # очистить столбец
                i = (y * w + px) * 4
                buf[i:i + 4] = zero
            if sx <= self.x0 or sx >= self.x1:
                continue
            top, base = self._edges(sx)
            top -= self.wy
            base -= self.wy
            depth = max(1.0, base - top)
            for y in range(max(0, int(top)), min(hgt, int(math.ceil(base)))):
                cov = min(y + 1, base) - max(y, top)  # доля пикселя, покрытая снегом
                if cov <= 0:
                    continue
                a = min(1.0, cov) * 0.97
                d = min(1.0, (y + 0.5 - top) / depth)  # 0 — верх, 1 — у поверхности
                i = (y * w + px) * 4
                # верх белый, ниже чуть голубее — объём
                buf[i] = int(255 * a)                     # B
                buf[i + 1] = int((255 - 14 * d) * a)      # G
                buf[i + 2] = int((255 - 26 * d) * a)      # R
                buf[i + 3] = int(255 * a)
        return True

    def present(self, on_screen):
        """Отправить картинку в окно (создаёт окно при первом показе)."""
        if self.hwnd is None:
            self.hwnd = layer_window()
        push_bitmap(self.hwnd, bytes(self.buf), self.ww, self.wh, self.wx, self.wy)
        self.show(on_screen)

    def show(self, on):
        on = bool(on and self.visible)
        if self.hwnd and on != self.shown:
            self.shown = on
            user32.ShowWindow(self.hwnd, 8 if on else 0)  # SW_SHOWNA / SW_HIDE

    def destroy(self):
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None


# ---------------------------------------------------------------- трей
class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [('cbSize', wt.DWORD), ('hWnd', wt.HWND), ('uID', wt.UINT), ('uFlags', wt.UINT),
                ('uCallbackMessage', wt.UINT), ('hIcon', wt.HICON), ('szTip', wt.WCHAR * 128),
                ('dwState', wt.DWORD), ('dwStateMask', wt.DWORD), ('szInfo', wt.WCHAR * 256),
                ('uVersion', wt.UINT), ('szInfoTitle', wt.WCHAR * 64), ('dwInfoFlags', wt.DWORD),
                ('guidItem', ctypes.c_ubyte * 16), ('hBalloonIcon', wt.HICON)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [('style', wt.UINT), ('lpfnWndProc', WNDPROC), ('cbClsExtra', ctypes.c_int),
                ('cbWndExtra', ctypes.c_int), ('hInstance', wt.HINSTANCE), ('hIcon', wt.HICON),
                ('hCursor', wt.HANDLE), ('hbrBackground', wt.HBRUSH), ('lpszMenuName', wt.LPCWSTR),
                ('lpszClassName', wt.LPCWSTR)]


class ICONINFO(ctypes.Structure):
    _fields_ = [('fIcon', wt.BOOL), ('xHotspot', wt.DWORD), ('yHotspot', wt.DWORD),
                ('hbmMask', wt.HBITMAP), ('hbmColor', wt.HBITMAP)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize', wt.DWORD), ('biWidth', wt.LONG), ('biHeight', wt.LONG),
                ('biPlanes', wt.WORD), ('biBitCount', wt.WORD), ('biCompression', wt.DWORD),
                ('biSizeImage', wt.DWORD), ('biXPelsPerMeter', wt.LONG), ('biYPelsPerMeter', wt.LONG),
                ('biClrUsed', wt.DWORD), ('biClrImportant', wt.DWORD)]


def make_snowflake_icon(S=32):
    """Рисует голубую снежинку 32x32 с альфой и делает из неё HICON."""
    c = (S - 1) / 2
    segs = []
    for k in range(6):
        a = math.pi / 2 + k * math.pi / 3
        dx, dy = math.cos(a), -math.sin(a)
        ex, ey = c + dx * 14, c + dy * 14
        segs.append((c, c, ex, ey))
        for t, ln in ((0.55, 5), (0.8, 3.5)):
            bx, by = c + dx * 14 * t, c + dy * 14 * t
            for s in (-1, 1):
                b = a + s * math.pi / 3
                segs.append((bx, by, bx + math.cos(b) * ln, by - math.sin(b) * ln))

    def dist(px, py, x0, y0, x1, y1):
        vx, vy = x1 - x0, y1 - y0
        t = max(0.0, min(1.0, ((px - x0) * vx + (py - y0) * vy) / (vx * vx + vy * vy)))
        return math.hypot(px - x0 - t * vx, py - y0 - t * vy)

    buf = bytearray(S * S * 4)
    for y in range(S):
        for x in range(S):
            d = min(dist(x, y, *s) for s in segs)
            if d < 1.9:
                a = 255 if d < 1.2 else int(255 * (1.9 - d) / 0.7)
                # premultiplied BGRA, цвет (90, 175, 255)
                i = (y * S + x) * 4
                buf[i], buf[i + 1], buf[i + 2], buf[i + 3] = 255 * a // 255, 175 * a // 255, 90 * a // 255, a
    bi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), S, -S, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    color = gdi32.CreateDIBSection(None, ctypes.byref(bi), 0, ctypes.byref(bits), None, 0)
    ctypes.memmove(bits, bytes(buf), len(buf))
    mask = gdi32.CreateBitmap(S, S, 1, 1, None)
    ii = ICONINFO(True, 0, 0, mask, color)
    hicon = user32.CreateIconIndirect(ctypes.byref(ii))
    gdi32.DeleteObject(color)
    gdi32.DeleteObject(mask)
    return hicon


class Tray:
    WM_TRAY = 0x8000 + 1  # WM_APP + 1
    CMD_TOGGLE, CMD_CLEAR, CMD_EXIT, CMD_SETTINGS = 1, 2, 3, 4

    def __init__(self, on_cmd, is_running):
        self.on_cmd = on_cmd
        self.is_running = is_running
        self.hinst = kernel32.GetModuleHandleW(None)
        self.msg_created = user32.RegisterWindowMessageW('TaskbarCreated')
        self._proc = WNDPROC(self._wndproc)  # держим ссылку, иначе GC
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._proc
        wc.hInstance = self.hinst
        wc.lpszClassName = 'DesktopSnowTray'
        user32.RegisterClassW(ctypes.byref(wc))
        self.hwnd = user32.CreateWindowExW(0, 'DesktopSnowTray', 'Desktop Snow', 0,
                                           0, 0, 0, 0, None, None, self.hinst, None)
        self.hicon = make_snowflake_icon()
        self.nid = NOTIFYICONDATAW()
        self.nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        self.nid.hWnd = self.hwnd
        self.nid.uID = 1
        self.nid.uFlags = 0x1 | 0x2 | 0x4  # MESSAGE | ICON | TIP
        self.nid.uCallbackMessage = self.WM_TRAY
        self.nid.hIcon = self.hicon
        self.nid.szTip = 'Снег на рабочем столе'
        self.add()

    def add(self):
        shell32.Shell_NotifyIconW(0, ctypes.byref(self.nid))  # NIM_ADD

    def remove(self):
        shell32.Shell_NotifyIconW(2, ctypes.byref(self.nid))  # NIM_DELETE
        user32.DestroyIcon(self.hicon)
        user32.DestroyWindow(self.hwnd)

    def _menu(self):
        m = user32.CreatePopupMenu()
        running = self.is_running()
        user32.AppendMenuW(m, 0, self.CMD_SETTINGS, 'Настройки…')
        user32.AppendMenuW(m, 0x800, 0, None)  # MF_SEPARATOR
        user32.AppendMenuW(m, 0x8 if running else 0, self.CMD_TOGGLE, 'Снег идёт')  # MF_CHECKED
        user32.AppendMenuW(m, 0, self.CMD_CLEAR, 'Стряхнуть сугробы')
        user32.AppendMenuW(m, 0x800, 0, None)  # MF_SEPARATOR
        user32.AppendMenuW(m, 0, self.CMD_EXIT, 'Выход')
        pt = wt.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self.hwnd)
        cmd = user32.TrackPopupMenu(m, 0x100 | 0x2, pt.x, pt.y, 0, self.hwnd, None)  # RETURNCMD|RIGHTBUTTON
        user32.PostMessageW(self.hwnd, 0, 0, 0)
        user32.DestroyMenu(m)
        if cmd:
            self.on_cmd(cmd)

    def _wndproc(self, hwnd, msg, wp, lp):
        try:
            if msg == self.WM_TRAY:
                ev = lp & 0xFFFF
                if ev == 0x205:      # WM_RBUTTONUP
                    self._menu()
                elif ev == 0x203:    # WM_LBUTTONDBLCLK — открыть настройки
                    self.on_cmd(self.CMD_SETTINGS)
                return 0
            if msg == self.msg_created:  # проводник перезапустился
                self.add()
                return 0
        except Exception:
            pass
        return user32.DefWindowProcW(hwnd, msg, wp, lp)


# ---------------------------------------------------------------- слои снегопада
# Снежинки не рисуются каждый кадр. Каждый слой — бесшовная текстура TILE×TILE,
# заранее нарисованная в прозрачные окна (UpdateLayeredWindow). В кадре окна только
# сдвигаются — это делает DWM на видеокарте, процессор почти не тратится.
# Слой разбит на две половины по ширине: окно на весь экран Windows считает
# «полноэкранной программой» и глушит уведомления.
class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [('BlendOp', ctypes.c_ubyte), ('BlendFlags', ctypes.c_ubyte),
                ('SourceConstantAlpha', ctypes.c_ubyte), ('AlphaFormat', ctypes.c_ubyte)]


sig(user32.UpdateLayeredWindow, [wt.HWND, wt.HDC, ctypes.POINTER(wt.POINT), ctypes.POINTER(wt.SIZE), wt.HDC,
                                 ctypes.POINTER(wt.POINT), wt.DWORD, ctypes.POINTER(BLENDFUNCTION), wt.DWORD],
    wt.BOOL)
sig(user32.RegisterClassW, [ctypes.c_void_p], wt.ATOM)
sig(user32.BeginDeferWindowPos, [ctypes.c_int], wt.HANDLE)
sig(user32.DeferWindowPos, [wt.HANDLE, wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                            ctypes.c_int, wt.UINT], wt.HANDLE)
sig(user32.EndDeferWindowPos, [wt.HANDLE], wt.BOOL)
sig(gdi32.CreateCompatibleDC, [wt.HDC], wt.HDC)
sig(gdi32.SelectObject, [wt.HDC, wt.HGDIOBJ], wt.HGDIOBJ)
sig(gdi32.DeleteDC, [wt.HDC], wt.BOOL)

TILE = 512
#             радиус px, доля снежинок, непрозрачность, скорость px/с, качание px, частота
LAYERS = ((1.0, 0.45, 0.55, 26, 9, 0.45),     # дальний: мелкий, медленный, бледный
          (1.5, 0.35, 0.80, 44, 15, 0.65),    # средний
          (2.3, 0.20, 0.95, 68, 24, 0.85))    # ближний: крупный, быстрый
MOVE_FLAGS = 0x1 | 0x4 | 0x10 | 0x200 | 0x400  # NOSIZE|NOZORDER|NOACTIVATE|NOOWNERZORDER|NOSENDCHANGING
_layer_class = None


def layer_window():
    global _layer_class
    hinst = kernel32.GetModuleHandleW(None)
    if _layer_class is None:
        wc = WNDCLASSW()
        wc.lpfnWndProc = ctypes.cast(user32.DefWindowProcW, WNDPROC)  # без Python-обработчика
        wc.hInstance = hinst
        wc.lpszClassName = 'DesktopSnowLayer'
        user32.RegisterClassW(ctypes.byref(wc))
        _layer_class = wc  # держим ссылку
    # LAYERED | TRANSPARENT | TOOLWINDOW | NOACTIVATE | TOPMOST, стиль WS_POPUP
    return user32.CreateWindowExW(0x80000 | 0x20 | 0x80 | 0x08000000 | 0x8, 'DesktopSnowLayer', 'snow', 0x80000000,
                                  0, 0, 1, 1, None, None, hinst, None)


def render_tile(flakes):
    """Мягкие круглые снежинки в BGRA (premultiplied), бесшовно по краям тайла."""
    P = TILE
    buf = bytearray(P * P * 4)
    for fx, fy, r, op in flakes:
        R = r + 1.5
        for yy in range(int(fy - R), int(fy + R) + 1):
            dy = yy + 0.5 - fy
            row = (yy % P) * P
            for xx in range(int(fx - R), int(fx + R) + 1):
                d = math.hypot(xx + 0.5 - fx, dy)
                a = (r + 0.6 - d) / 1.2  # мягкий край ~1px
                if a <= 0:
                    continue
                a = min(1.0, a) * op
                i = (row + xx % P) * 4
                k = 1 - a
                buf[i] = int(255 * a + buf[i] * k)          # B
                buf[i + 1] = int(250 * a + buf[i + 1] * k)  # G
                buf[i + 2] = int(243 * a + buf[i + 2] * k)  # R — чуть голубоватый белый
                buf[i + 3] = int(255 * a + buf[i + 3] * k)
    return bytes(buf)


def compose(tile, w, h, ox):
    """Картинка w×h из повторений тайла, сдвинутого на ox по горизонтали."""
    P, rb = TILE, TILE * 4
    s = (ox % P) * 4
    reps = w // P + 2
    rows = []
    for ty in range(P):
        src = tile[ty * rb:(ty + 1) * rb]
        rows.append(((src[s:] + src[:s]) * reps)[:w * 4])
    return b''.join(rows[y % P] for y in range(h))


def push_bitmap(hwnd, pixels, w, h, x, y):
    bi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    hbm = gdi32.CreateDIBSection(None, ctypes.byref(bi), 0, ctypes.byref(bits), None, 0)
    if not hbm:
        return
    ctypes.memmove(bits, pixels, len(pixels))
    dc = gdi32.CreateCompatibleDC(None)
    old = gdi32.SelectObject(dc, hbm)
    blend = BLENDFUNCTION(0, 0, 255, 1)  # AC_SRC_OVER, альфа из картинки
    user32.UpdateLayeredWindow(hwnd, None, ctypes.byref(wt.POINT(x, y)), ctypes.byref(wt.SIZE(w, h)), dc,
                               ctypes.byref(wt.POINT(0, 0)), 0, ctypes.byref(blend), 2)  # ULW_ALPHA
    gdi32.SelectObject(dc, old)
    gdi32.DeleteDC(dc)
    gdi32.DeleteObject(hbm)  # DWM хранит свою копию — у нас память не держим


class Layer:
    def __init__(self, idx):
        self.r, self.share, self.op, self.v, self.amp, self.fr = LAYERS[idx]
        self.ph = random.uniform(0, 6.3)
        self.yoff = random.uniform(0, TILE)
        self.xoff = random.uniform(0, TILE)
        self.hw = [layer_window(), layer_window()]
        self.pos = [None, None]
        self.split = 0

    def build(self, vx, vy, vw, vh, density, size, sc):
        P = TILE
        n = round(density * self.share * P * P / 1e6)
        r = self.r * sc * size
        flakes = [(random.uniform(0, P), random.uniform(0, P), r * random.uniform(0.8, 1.2), self.op)
                  for _ in range(n)]
        tile = render_tile(flakes)
        self.split = half = vw // 2
        self.vx, self.vy = vx, vy
        widths = (half + P, vw - half + P)
        h = vh + P
        for k, hwnd in enumerate(self.hw):
            ox = 0 if k == 0 else half + P  # правая половина продолжает узор левой
            x, y = self._xy(k)
            push_bitmap(hwnd, compose(tile, widths[k], h, ox), widths[k], h, x, y)
            self.pos[k] = (x, y)

    def _xy(self, k):
        sx, sy = int(self.xoff) % TILE, int(self.yoff) % TILE
        x = self.vx - TILE + sx + (0 if k == 0 else self.split + TILE)
        return x, self.vy - TILE + sy

    def advance(self, dt, t, speed, wind, sc):
        self.yoff += self.v * speed * sc * dt
        self.xoff += wind * (0.4 + self.r / 2) * dt
        self.cur_sway = self.amp * sc * math.sin(t * self.fr + self.ph)

    def move(self):
        for k, hwnd in enumerate(self.hw):
            x, y = self._xy(k)
            x += int(self.cur_sway)
            if self.pos[k] != (x, y):
                self.pos[k] = (x, y)
                user32.SetWindowPos(hwnd, None, x, y, 0, 0, MOVE_FLAGS)

    def show(self, on):
        for hwnd in self.hw:
            user32.ShowWindow(hwnd, 8 if on else 0)  # SW_SHOWNA / SW_HIDE

    def topmost(self):
        for hwnd in self.hw:
            user32.SetWindowPos(hwnd, wt.HWND(-1), 0, 0, 0, 0, 0x2 | 0x1 | 0x10)

    def destroy(self):
        for hwnd in self.hw:
            user32.DestroyWindow(hwnd)


# ---------------------------------------------------------------- приложение
def pythonw():
    exe = sys.executable
    w = os.path.join(os.path.dirname(exe), 'pythonw.exe')
    return w if os.path.exists(w) else exe


class SnowApp:
    def __init__(self):
        self.vx, self.vy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
        self.vw, self.vh = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)

        # Tk нужен только как цикл событий и таймер: своих окон у него нет
        self.root = root = tk.Tk()
        root.withdraw()

        try:
            self.dpi_scale = user32.GetDpiForSystem() / 96
        except AttributeError:
            self.dpi_scale = 1
        self.cfg = config.load()
        self.cfg_mtime = config.mtime()
        self.icons = DesktopIcons()
        self.shapes = IconShapes()
        self.blocker = Blocker()
        self.piles = {}       # key -> Pile
        self.running = True   # включено пользователем
        self.shown = True     # сейчас видно (не прячемся от игры)
        self.cmds = []
        self.t = 0.0
        self.frame = 0
        self.last = time.perf_counter()
        self.last_scan = 0.0
        self.last_check = 0.0
        self.last_piles = 0.0
        self.next_frame = time.perf_counter()
        self.precise = False
        self.set_precise_timer(True)

        self.layers = [Layer(i) for i in range(len(LAYERS))]
        self.build_layers()
        for L in self.layers:
            L.show(True)
        self.raise_top()

        self.tray = Tray(self.cmds.append, lambda: self.running)
        root.after(10, self.tick)

    def build_layers(self):
        c = self.cfg
        for L in self.layers:
            L.build(self.vx, self.vy, self.vw, self.vh, c['density'], c['size'], self.dpi_scale)

    def raise_top(self):
        # HWND_TOPMOST, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE; снег поверх сугробов
        for p in self.piles.values():
            if p.hwnd:
                user32.SetWindowPos(p.hwnd, wt.HWND(-1), 0, 0, 0, 0, 0x2 | 0x1 | 0x10)
        for L in self.layers:
            L.topmost()

    # --- настройки «на лету»
    def reload_cfg(self):
        m = config.mtime()
        if m == self.cfg_mtime:
            return
        self.cfg_mtime = m
        old, self.cfg = self.cfg, config.load()
        new = self.cfg
        if new['density'] != old['density'] or new['size'] != old['size']:
            self.build_layers()
        if any(new[k] != old[k] for k in ('icon_cap', 'taskbar_cap', 'on_icons', 'on_taskbar')):
            self.clear_piles()

    def visible(self):
        return self.running and self.shown

    def set_precise_timer(self, on):
        """Таймер Windows по умолчанию шагает по ~15.6 мс, и 30 FPS превращаются в ~21.
        Точный (1 мс) включаем только пока снег виден."""
        if on != self.precise:
            self.precise = on
            (winmm.timeBeginPeriod if on else winmm.timeEndPeriod)(1)

    def apply_visibility(self):
        on = self.visible()
        self.set_precise_timer(on)
        self.next_frame = time.perf_counter()
        for L in self.layers:
            L.show(on)
        for p in self.piles.values():
            p.show(on)
        if on:
            self.last_scan = 0  # сразу перепроверить, какие сугробы видны

    # --- сцена: где лежит снег
    def scan(self):
        found = {}
        sc = self.dpi_scale
        cfg = self.cfg
        if cfg['on_icons']:
            self._scan_icons(found, cfg['icon_cap'] * sc)
        if cfg['on_taskbar']:
            for h, l, t, r, b in taskbars():
                if t >= self.vy + self.vh - 4:  # авто-скрытая
                    continue
                my = (t + b) // 2  # у самого края бывает рамка развёрнутого окна
                vis = any(root_at(x, my) == h for x in ((l + r) // 2, l + 40, r - 40))
                found[('tb', h, l, r, t)] = (l, [t] * int((r - l) / COL), cfg['taskbar_cap'] * sc, vis)

        for key in list(self.piles):
            if key not in found:
                self.piles.pop(key).destroy()
        on = self.visible()
        for key, (x0, base, cap, vis) in found.items():
            p = self.piles.get(key)
            if p is None:
                p = self.piles[key] = Pile(x0, base, cap)
            if vis != p.visible:
                p.visible = vis
                p.show(on)
            if vis:
                p.grow(SCAN_EVERY, cfg['fill_time'])
        self.raise_top()

    def _scan_icons(self, found, cap):
        sc = self.dpi_scale
        root = self.icons.root
        rects = self.icons.rects()
        names = self.icons.texts(len(rects))
        for i, (l, t, r, b) in enumerate(rects):
            w, h = r - l, b - t
            img = max(8, min(w, h) - int(4 * sc))       # сам значок внутри ячейки
            il, it = l + (w - img) / 2, t + (h - img) / 2
            name = names[i] if i < len(names) else ''
            prof = self.shapes.contour(name)
            if prof is None:  # форма неизвестна (например, миниатюра картинки) — плоский верх
                prof = [None] * 6 + [2] * (SIL - 12) + [None] * 6
            k = img / SIL
            base = []
            for c in range(int(img / COL)):
                a = int(c * COL / k)
                z = max(a + 1, int((c + 1) * COL / k))
                vals = [v for v in prof[a:z] if v is not None]
                base.append(it + min(vals) * k if vals else None)
            vis = all(root_at(il + img * f, it + img * 0.5) == root for f in (0.2, 0.5, 0.8))
            # непрерывные куски контура — отдельные сугробы
            start = None
            for c in range(len(base) + 1):
                if c < len(base) and base[c] is not None:
                    if start is None:
                        start = c
                elif start is not None:
                    if c - start >= 2:
                        found[('icon', i, name, il, it, start)] = (il + start * COL, base[start:c], cap, vis)
                    start = None

    def clear_piles(self):
        for p in self.piles.values():
            p.destroy()
        self.piles = {}
        self.last_scan = 0

    # --- трей
    def open_settings(self):
        h = user32.FindWindowW(None, config.SETTINGS_TITLE)
        if h:  # уже открыто — просто показать
            user32.ShowWindow(h, 9)  # SW_RESTORE
            user32.SetForegroundWindow(h)
            return
        try:
            subprocess.Popen([pythonw(), os.path.join(HERE, 'settings.pyw')], cwd=HERE)
        except OSError:
            pass

    def handle_cmds(self):
        while self.cmds:
            c = self.cmds.pop(0)
            if c == Tray.CMD_EXIT:
                self.quit()
                return False
            if c == Tray.CMD_SETTINGS:
                self.open_settings()
            elif c == Tray.CMD_CLEAR:
                self.clear_piles()
            elif c == Tray.CMD_TOGGLE:
                self.running = not self.running
                if not self.running:
                    self.clear_piles()
                self.apply_visibility()
        return True

    # --- главный цикл
    def tick(self):
        if not self.handle_cmds():
            return
        now = time.perf_counter()
        dt = min(0.1, now - self.last)
        self.last = now
        if now - self.last_check > 0.25:
            self.last_check = now
            self.reload_cfg()
            if self.running:
                shown = not self.blocker.blocked(self.cfg)
                if shown != self.shown:
                    self.shown = shown
                    self.apply_visibility()
        if not self.visible():
            self.root.after(250, self.tick)  # спим: почти ноль процессора
            return
        if now - self.last_scan > SCAN_EVERY:
            self.last_scan = now
            self.scan()
        self.step(dt)
        # расписание без накопления ошибки: следующий кадр — ровно через 1/fps от прошлого
        fps = min(144, max(10, self.cfg['fps']))
        self.next_frame += 1 / fps
        end = time.perf_counter()
        if self.next_frame < end - 0.1:  # сильно отстали (например, после сна) — не догоняем
            self.next_frame = end
        self.root.after(max(1, round((self.next_frame - end) * 1000)), self.tick)

    def step(self, dt):
        self.t += dt
        self.frame += 1
        if DEBUG:  # реальный FPS раз в 2 секунды
            now = time.perf_counter()
            if not hasattr(self, '_dbg'):
                self._dbg, self._dbg_n = now, self.frame
            elif now - self._dbg >= 2:
                print(f'fps {(self.frame - self._dbg_n) / (now - self._dbg):.1f}', file=sys.stderr, flush=True)
                self._dbg, self._dbg_n = now, self.frame
        t, c, sc = self.t, self.cfg, self.dpi_scale
        wind = (14 * math.sin(t * 0.11) + 7 * math.sin(t * 0.37 + 1)) * c['wind'] * sc
        for L in self.layers:
            L.advance(dt, t, c['speed'], wind, sc)
            L.move()

        # сугробы меняются медленно — перерисовываем их ~4 раза в секунду
        if self.t - self.last_piles < 0.25:
            return
        self.last_piles = self.t
        for p in self.piles.values():
            if p.unsettled > 0:
                p.settle()
            if p.visible and p.render():
                new = p.hwnd is None
                p.present(True)
                if new:  # новое окно сугроба — под снегопадом
                    self.raise_top()

    def quit(self):
        try:
            self.tray.remove()
        except Exception:
            pass
        for L in self.layers:
            L.destroy()
        for p in self.piles.values():
            p.destroy()
        self.set_precise_timer(False)
        self.icons.close()
        self.root.destroy()

    def run(self):
        try:
            self.root.mainloop()
        finally:
            try:
                self.tray.remove()
            except Exception:
                pass


def main():
    kernel32.CreateMutexW(None, False, 'Local\\DesktopSnow')
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS — уже запущено
        return
    dpi_aware()
    app = SnowApp()
    # ручной запуск — показываем окно настроек; автозапуск — тихо в трей
    if '--autostart' not in sys.argv and app.cfg['show_on_start']:
        app.root.after(500, app.open_settings)
    app.run()


if __name__ == '__main__':
    main()


