"""Навигация и сайдбар интерфейса PCAR."""
import nicegui.ui as ui
from typing import List
from .state import app_state

current_mode = {"view": "chat"}

def render_layout() -> None:
    """Отрисовывает основной макет интерфейса."""
    with ui.left_drawer().classes('bg-[#171719] border-none w-[280px] h-full shadow-none'):
        render_sidebar()
    
    with ui.column().classes('flex-1 h-screen bg-[#0e0e10] text-gray-100 overflow-hidden p-0 m-0'):
        render_content_area()

@ui.refreshable
def render_content_area() -> None:
    """Отрисовывает контентную область."""
    with ui.column().classes('w-full h-full p-0 m-0'):
        if current_mode["view"] == "chat":
            from .chat import render_chat
            render_chat()
        elif current_mode["view"] == "logs":
            with ui.column().classes('w-full max-w-7xl mx-auto p-8 overflow-y-auto h-full'):
                from .analytics import render_dashboard
                render_dashboard()
        elif current_mode["view"] == "telemetry":
            with ui.column().classes('w-full max-w-7xl mx-auto p-8 overflow-y-auto h-full'):
                from .analytics import render_telemetry
                render_telemetry()
        elif current_mode["view"] == "inbox":
            with ui.column().classes('w-full max-w-7xl mx-auto p-8 overflow-y-auto h-full'):
                from .inbox import render_inbox
                render_inbox()

@ui.refreshable
def render_sidebar() -> None:
    """Отрисовывает боковое меню (в стиле Gemini)."""
    with ui.column().classes('w-full h-full p-4 gap-0'):
        # Логотип
        with ui.row().classes('items-center gap-3 mb-8 px-2 mt-2'):
            ui.icon('menu', size='24px').classes('text-gray-400 cursor-pointer hover:text-white transition-colors')
            ui.label('PCAR').classes('text-xl font-medium text-gray-200')

        def on_new_chat(e):
            app_state.create_new_chat()
            current_mode["view"] = "chat"
            render_sidebar.refresh()
            render_content_area.refresh()

        def set_mode(m):
            current_mode["view"] = m
            render_sidebar.refresh()
            render_content_area.refresh()

        # КНОПКА "НОВЫЙ ЧАТ"
        with ui.row().classes('w-[90%] py-3 mb-8 bg-[#202123] hover:bg-[#2b2c2f] text-gray-300 rounded-full cursor-pointer items-center justify-center transition-all') \
                     .on('click', on_new_chat):
            ui.icon('add', size='18px')
            ui.label('Новый чат').classes('text-sm font-medium ml-2')

        # ВКЛАДКИ
        with ui.column().classes('w-full gap-1 mb-8'):
            nav_items = [
                ('chat', 'Чат', 'chat_bubble_outline'),
                ('inbox', 'Входящие', 'inventory_2'),
                ('logs', 'Логи', 'analytics'),
                ('telemetry', 'Телеметрия', 'monitoring'),
            ]
            for mode, label, item_icon in nav_items:
                is_active = current_mode["view"] == mode
                
                with ui.row().classes(f'w-full h-11 items-center px-4 rounded-full cursor-pointer transition-colors no-wrap '
                                      f'{"bg-[#282a2c] text-white" if is_active else "bg-transparent text-gray-400 hover:bg-[#202123] hover:text-gray-200"}') \
                                      .on('click', lambda m=mode: set_mode(m)):
                    # Вот тут исправлено: передаем item_icon
                    ui.icon(item_icon, size='20px').style('width: 28px; text-align: center;')
                    ui.label(label).classes('text-[14px] font-medium')

        # СПИСОК ЧАТОВ
        ui.label('ПОСЛЕДНИЕ').classes('text-[11px] text-gray-500 font-bold ml-4 mb-2 tracking-widest')
        
        with ui.scroll_area().classes('flex-1 w-full'):
            with ui.column().classes('w-full gap-1'):
                all_chat_ids = list(app_state.chats_meta.keys())
                for chat_id in reversed(all_chat_ids):
                    chat_data = app_state.chats_meta.get(chat_id, {})
                    title = chat_data.get("title", "Без названия")
                    is_current = (chat_id == app_state.current_chat_id) and (current_mode["view"] == "chat")

                    def switch_chat(cid=chat_id):
                        app_state.switch_chat(cid)
                        current_mode["view"] = "chat"
                        render_sidebar.refresh()
                        render_content_area.refresh()

                    with ui.row().classes(f'w-full h-10 items-center px-4 rounded-full cursor-pointer transition-colors no-wrap '
                                          f'{"bg-[#282a2c] text-white" if is_current else "bg-transparent text-gray-400 hover:bg-[#202123] hover:text-gray-200"}') \
                                          .on('click', lambda cid=chat_id: switch_chat(cid)):
                        ui.icon('chat_bubble_outline', size='16px').classes('min-w-[20px]')
                        ui.label(title).classes('text-[14px] truncate font-normal flex-1')