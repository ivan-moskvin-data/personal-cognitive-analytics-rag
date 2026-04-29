"""Точка входа в приложение PCAR на базе NiceGUI."""
import sys
from pathlib import Path

# Добавляем путь к модулям
sys.path.append(str(Path(__file__).resolve().parent))

import nicegui.ui as ui
from nicegui import app as nicegui_app
from ui import AppState, render_layout, render_chat, render_inbox, render_dashboard, render_telemetry

# Инициализация состояния
app_state = AppState()

# Глобальные стили
ui.add_head_html('''
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');
    
    :root {
        --bg-deep: #0e0e10;        /* Почти черный как в Gemini */
        --bg-sidebar: #171719; 
        --accent: #4e46e5;
    }

    body {
        background-color: var(--bg-deep);
        font-family: 'Inter', sans-serif;
        color: #e3e3e3;
    }

    .q-page { padding: 0 !important; min-height: 100vh !important; }
    .q-layout-padding { padding: 0 !important; }

    /* Убираем все стандартные тени и границы */
    .q-btn, .q-card {
        box-shadow: none !important;
        border: none !important;
    }

    /* Стилизация скроллбара */
    ::-webkit-scrollbar { width: 5px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #333; border-radius: 10px; }
</style>
''', shared=True)

@ui.page('/')
def main_page() -> None:
    """Главная страница приложения."""
    render_layout()

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="PCAR | Цифровой Мозг",
        dark=True,
        port=8080,
        language="ru",
        storage_secret='pCar-secure-key-2024',
        reconnect_timeout=10
    )