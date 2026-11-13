"""Настройки снега: один JSON-файл, общий для снега и окна настроек."""
import json
import os

DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'DesktopSnow')
PATH = os.path.join(DIR, 'settings.json')
SETTINGS_TITLE = 'Снег — настройки'   # по заголовку снег находит уже открытое окно

DEFAULTS = {
    'fps': 30,               # кадров в секунду: выше — плавнее, но больше нагрузка на процессор
    'density': 70,           # снежинок на мегапиксель экрана
    'speed': 1.0,            # множитель скорости падения
    'wind': 1.0,             # множитель ветра
    'size': 1.0,             # множитель размера снежинок
    'on_icons': True,        # копить на иконках
    'on_taskbar': True,      # копить на панели задач
    'icon_cap': 9,           # макс. высота сугроба на иконке, px
    'taskbar_cap': 10,       # макс. высота сугроба на панели задач, px
    'fill_time': 150,        # за сколько секунд сугроб дорастает
    'hide_fullscreen': True, # прятать снег, когда активна полноэкранная программа (игры, видео)
    'excluded': [],          # имена .exe, при которых снег прячется
    'show_on_start': True,   # открывать окно настроек при ручном запуске (автозапуск — сразу в трей)
}


def load():
    data = dict(DEFAULTS)
    try:
        with open(PATH, encoding='utf-8') as f:
            raw = json.load(f)
        for k, v in raw.items():
            if k in DEFAULTS and type(v) is type(DEFAULTS[k]) or (
                    k in DEFAULTS and isinstance(DEFAULTS[k], float) and isinstance(v, int)):
                data[k] = v
    except (OSError, ValueError):
        pass
    data['excluded'] = [str(x).lower() for x in data['excluded']]
    return data


def save(data):
    os.makedirs(DIR, exist_ok=True)
    tmp = PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PATH)  # атомарно: снег никогда не прочитает половину файла


def mtime():
    try:
        return os.path.getmtime(PATH)
    except OSError:
        return 0.0
