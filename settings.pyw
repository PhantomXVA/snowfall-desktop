"""Окно настроек снега (Qt6 / PySide6).

Открывается из трея снега («Настройки…» или двойной клик по снежинке).
Каждое изменение сразу пишется в settings.json — снег подхватывает его за долю секунды.
Закрыли окно — снег продолжает жить в трее.
"""
import ctypes
import ctypes.wintypes as wt
import math
import os
import sys
import winreg

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QListWidget, QMenu, QPushButton, QSlider, QVBoxLayout, QWidget)

import config

HERE = os.path.dirname(os.path.abspath(__file__))
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
RUN_NAME = 'DesktopSnow'


# ---------------------------------------------------------------- автозапуск
def pythonw():
    w = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    return w if os.path.exists(w) else sys.executable


def autostart_cmd():
    return f'"{pythonw()}" "{os.path.join(HERE, "snow.pyw")}" --autostart'


def autostart_get():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return bool(winreg.QueryValueEx(k, RUN_NAME)[0])
    except OSError:
        return False


def autostart_set(on):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, autostart_cmd())
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except OSError:
                pass


# ---------------------------------------------------------------- запущенные программы
user32 = ctypes.WinDLL('user32')
kernel32 = ctypes.WinDLL('kernel32')
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
kernel32.CloseHandle.argtypes = [wt.HANDLE]
ENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def running_apps():
    """{exe: заголовок окна} для видимых окон с заголовком."""
    out = {}
    me = os.getpid()

    def cb(h, _):
        if not user32.IsWindowVisible(h) or user32.GetWindow(h, 4):  # GW_OWNER — пропускаем диалоги
            return True
        n = user32.GetWindowTextLengthW(h)
        if not n:
            return True
        title = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(h, title, n + 1)
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value == me:
            return True
        ph = kernel32.OpenProcess(0x1000, False, pid.value)
        if ph:
            buf = ctypes.create_unicode_buffer(520)
            ln = wt.DWORD(520)
            if kernel32.QueryFullProcessImageNameW(ph, 0, buf, ctypes.byref(ln)):
                exe = os.path.basename(buf.value).lower()
                if exe not in ('explorer.exe', 'textinputhost.exe', 'applicationframehost.exe'):
                    out.setdefault(exe, title.value)
            kernel32.CloseHandle(ph)
        return True

    user32.EnumWindows(ENUMPROC(cb), 0)
    return dict(sorted(out.items()))


# ---------------------------------------------------------------- вид
def snowflake_icon(size=64, color='#5aafff'):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(color), size / 14, Qt.SolidLine, Qt.RoundCap))
    c = size / 2
    r = size * 0.44
    for k in range(6):
        a = math.pi / 2 + k * math.pi / 3
        dx, dy = math.cos(a), -math.sin(a)
        p.drawLine(QPointF(c, c), QPointF(c + dx * r, c + dy * r))
        for t, ln in ((0.55, 0.32), (0.8, 0.2)):
            bx, by = c + dx * r * t, c + dy * r * t
            for s in (-1, 1):
                b = a + s * math.pi / 3
                p.drawLine(QPointF(bx, by), QPointF(bx + math.cos(b) * r * ln, by - math.sin(b) * r * ln))
    p.end()
    return QIcon(pm)


class Slider(QWidget):
    """Ползунок с подписью значения. Хранит float: value = raw / scale."""

    def __init__(self, lo, hi, scale=1, fmt='{:g}', on_change=None):
        super().__init__()
        self.scale, self.fmt, self.on_change = scale, fmt, on_change
        self.s = QSlider(Qt.Horizontal)
        self.s.setRange(int(lo * scale), int(hi * scale))
        self.lbl = QLabel()
        self.lbl.setMinimumWidth(78)
        self.lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.s, 1)
        lay.addWidget(self.lbl)
        self.s.valueChanged.connect(self._changed)

    def value(self):
        return self.s.value() / self.scale

    def _text(self):
        v = self.value()
        return self.fmt(v) if callable(self.fmt) else self.fmt.format(v)

    def set_value(self, v):
        self.s.blockSignals(True)
        self.s.setValue(round(v * self.scale))
        self.s.blockSignals(False)
        self.lbl.setText(self._text())

    def _changed(self):
        self.lbl.setText(self._text())
        if self.on_change:
            self.on_change()


FPS_LOAD = ((10, 5), (15, 7), (30, 15), (60, 24), (120, 33))  # замер: FPS -> % одного ядра (снег + DWM)


def fps_load(fps):
    pts = FPS_LOAD
    for (f0, l0), (f1, l1) in zip(pts, pts[1:]):
        if fps <= f1:
            return l0 + (l1 - l0) * (max(fps, f0) - f0) / (f1 - f0)
    return pts[-1][1]


def fmt_time(sec):
    sec = int(sec)
    return f'{sec} с' if sec < 90 else f'{sec / 60:.1f} мин'.replace('.0 ', ' ')


# ---------------------------------------------------------------- окно
class SettingsWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(config.SETTINGS_TITLE)
        self.setWindowIcon(snowflake_icon())
        self.setMinimumWidth(480)
        self.cfg = config.load()
        self.save_timer = QTimer(self, singleShot=True, interval=250, timeout=self.save)

        ch = self.schedule_save
        self.fps = Slider(10, 120, 1, '{:g} FPS', self._fps_changed)
        self.fps.s.setSingleStep(5)
        self.fps.s.setPageStep(15)
        self.fps_warn = QLabel()
        self.fps_warn.setWordWrap(True)
        self.density = Slider(5, 250, 1, '{:g} шт/Мп', ch)
        self.speed = Slider(0.3, 3, 10, '×{:.1f}', ch)
        self.wind = Slider(0, 3, 10, '×{:.1f}', ch)
        self.size = Slider(0.5, 2.5, 10, '×{:.1f}', ch)
        self.on_icons = QCheckBox('На иконках рабочего стола')
        self.on_taskbar = QCheckBox('На панели задач')
        self.icon_cap = Slider(2, 24, 1, '{:g} px', ch)
        self.taskbar_cap = Slider(2, 30, 1, '{:g} px', ch)
        self.fill_time = Slider(20, 900, 1, fmt_time, ch)
        self.hide_fullscreen = QCheckBox('В играх и полноэкранных программах (видео, F11)')
        self.excluded = QListWidget()
        self.excluded.setMaximumHeight(110)
        self.autostart = QCheckBox('Запускать вместе с Windows (сразу в трей)')
        self.show_on_start = QCheckBox('Показывать это окно при ручном запуске')
        for cb in (self.on_icons, self.on_taskbar, self.hide_fullscreen, self.show_on_start):
            cb.toggled.connect(ch)
        self.autostart.toggled.connect(self._autostart_toggled)

        # --- раскладка
        g1 = QGroupBox('Снегопад')
        f1 = QFormLayout(g1)
        f1.addRow('Плавность', self.fps)
        f1.addRow(self.fps_warn)
        f1.addRow('Количество', self.density)
        f1.addRow('Скорость', self.speed)
        f1.addRow('Ветер', self.wind)
        f1.addRow('Размер', self.size)

        g2 = QGroupBox('Сугробы')
        f2 = QFormLayout(g2)
        f2.addRow(self.on_icons)
        f2.addRow(self.on_taskbar)
        f2.addRow('Высота на иконках', self.icon_cap)
        f2.addRow('Высота на панели', self.taskbar_cap)
        f2.addRow('Полный сугроб за', self.fill_time)

        g3 = QGroupBox('Прятать снег')
        v3 = QVBoxLayout(g3)
        v3.addWidget(self.hide_fullscreen)
        v3.addWidget(QLabel('…и когда активна одна из этих программ:'))
        v3.addWidget(self.excluded)
        row = QHBoxLayout()
        b_run = QPushButton('Из запущенных…')
        b_file = QPushButton('Выбрать .exe…')
        b_del = QPushButton('Убрать')
        b_run.clicked.connect(self._add_running)
        b_file.clicked.connect(self._add_file)
        b_del.clicked.connect(self._remove)
        for b in (b_run, b_file, b_del):
            row.addWidget(b)
        v3.addLayout(row)

        g4 = QGroupBox('Программа')
        v4 = QVBoxLayout(g4)
        v4.addWidget(self.autostart)
        v4.addWidget(self.show_on_start)
        tip = QLabel('Закрытое окно сворачивается в трей: снег продолжает идти. '
                     'Снежинка в трее: двойной клик — это окно, правый клик — пауза и выход.')
        tip.setWordWrap(True)
        tip.setStyleSheet('color: palette(placeholder-text);')
        v4.addWidget(tip)

        bottom = QHBoxLayout()
        reset = QPushButton('Сбросить по умолчанию')
        reset.clicked.connect(self._reset)
        close = QPushButton('Свернуть в трей')
        close.setDefault(True)
        close.clicked.connect(self.close)
        bottom.addWidget(reset)
        bottom.addStretch(1)
        bottom.addWidget(close)

        lay = QVBoxLayout(self)
        for g in (g1, g2, g3, g4):
            lay.addWidget(g)
        lay.addLayout(bottom)

        self._fill()

    # --- данные <-> виджеты
    def _fill(self):
        c = self.cfg
        for name in ('fps', 'density', 'speed', 'wind', 'size', 'icon_cap', 'taskbar_cap'):
            getattr(self, name).set_value(c[name])
        self._update_fps_warn()
        self.fill_time.set_value(c['fill_time'])
        for name in ('on_icons', 'on_taskbar', 'hide_fullscreen', 'show_on_start'):
            cb = getattr(self, name)
            cb.blockSignals(True)
            cb.setChecked(c[name])
            cb.blockSignals(False)
        self.excluded.clear()
        self.excluded.addItems(c['excluded'])
        self.autostart.blockSignals(True)
        self.autostart.setChecked(autostart_get())
        self.autostart.blockSignals(False)

    def _collect(self):
        c = self.cfg
        c['fps'] = int(self.fps.value())
        c['density'] = int(self.density.value())
        c['speed'] = self.speed.value()
        c['wind'] = self.wind.value()
        c['size'] = self.size.value()
        c['icon_cap'] = int(self.icon_cap.value())
        c['taskbar_cap'] = int(self.taskbar_cap.value())
        c['fill_time'] = int(self.fill_time.value())
        for name in ('on_icons', 'on_taskbar', 'hide_fullscreen', 'show_on_start'):
            c[name] = getattr(self, name).isChecked()
        c['excluded'] = [self.excluded.item(i).text() for i in range(self.excluded.count())]

    def schedule_save(self):
        self.save_timer.start()

    def _fps_changed(self):
        self._update_fps_warn()
        self.schedule_save()

    def _update_fps_warn(self):
        fps = self.fps.value()
        core = fps_load(fps)
        if fps <= 30:
            color, level = '#5fb86b', 'Нагрузка низкая.'
        elif fps <= 60:
            color, level = '#e0a63a', 'Нагрузка средняя.'
        else:
            color, level = '#e05a4a', 'Нагрузка высокая — на слабом ПК или ноутбуке от батареи лучше не надо.'
        self.fps_warn.setText(
            f'<span style="color:{color}">⚠ Чем выше FPS, тем плавнее снег, но тем больше нагрузка на процессор. '
            f'{level}</span><br><span style="color:#8a8f98">'
            f'Примерно {core:.0f}% одного ядра процессора (вместе с отрисовкой Windows). '
            f'30 FPS — золотая середина.</span>')

    def save(self):
        self._collect()
        config.save(self.cfg)

    # --- действия
    def _autostart_toggled(self, on):
        try:
            autostart_set(on)
        except OSError:
            self.autostart.blockSignals(True)
            self.autostart.setChecked(not on)
            self.autostart.blockSignals(False)

    def _add_exe(self, exe):
        exe = exe.lower()
        if exe and not self.excluded.findItems(exe, Qt.MatchExactly):
            self.excluded.addItem(exe)
            self.schedule_save()

    def _add_running(self):
        m = QMenu(self)
        apps = running_apps()
        if not apps:
            m.addAction('Нет открытых окон').setEnabled(False)
        for exe, title in apps.items():
            t = title if len(title) < 50 else title[:47] + '…'
            m.addAction(f'{exe}  —  {t}', lambda e=exe: self._add_exe(e))
        m.exec(QCursor.pos())

    def _add_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Программа, при которой прятать снег', 'C:\\',
                                              'Программы (*.exe)')
        if path:
            self._add_exe(os.path.basename(path))

    def _remove(self):
        for it in self.excluded.selectedItems():
            self.excluded.takeItem(self.excluded.row(it))
        self.schedule_save()

    def _reset(self):
        self.cfg = dict(config.DEFAULTS)
        self.cfg['excluded'] = []
        self._fill()
        self.save()

    def closeEvent(self, e):
        if self.save_timer.isActive():
            self.save_timer.stop()
            self.save()
        super().closeEvent(e)


def main():
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    mutex = k32.CreateMutexW(None, False, 'Local\\DesktopSnowSettings')
    if ctypes.get_last_error() == 183:  # окно уже открыто
        return
    app = QApplication(sys.argv)
    app.setApplicationName('Снег')
    w = SettingsWindow()
    w.show()
    w.raise_()
    w.activateWindow()
    app.exec()
    del mutex


if __name__ == '__main__':
    main()
