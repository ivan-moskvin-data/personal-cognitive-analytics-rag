"""Навигация и сайдбар интерфейса PCAR (Grid System)."""
import nicegui.ui as ui
from .state import app_state

current_mode = {"view": "chat"}

def render_layout() -> None:
    """Отрисовывает основной макет интерфейса."""
    # Главный контейнер на весь экран. Запрещаем скролл.
    with ui.row().classes('w-full h-screen bg-[#0e0e10] p-0 m-0 no-wrap items-stretch overflow-hidden'):
        
        # САЙДБАР
        with ui.column().classes('w-[280px] h-full bg-[#171719] p-4 gap-0 shrink-0 border-r border-white/5 no-wrap'):
            render_sidebar()
        
        # КОНТЕНТ (занимает все свободное место, overflow-hidden чтобы не плодить скроллы)
        with ui.column().classes('flex-1 h-full p-0 m-0 relative overflow-hidden'):
            render_content_area()

@ui.refreshable
def render_content_area() -> None:
    """Отрисовывает контентную область."""
    # Внутренний контейнер контента
    with ui.element('div').classes('w-full h-full flex flex-col overflow-hidden'):
        if current_mode["view"] == "chat":
            from .chat import render_chat
            render_chat()
        else:
            # Для остальных вкладок оставляем скролл внутри области контента
            with ui.element('div').classes('w-full h-full overflow-y-auto p-8 custom-scrollbar'):
                if current_mode["view"] == "logs":
                    from .analytics import render_dashboard
                    render_dashboard()
                elif current_mode["view"] == "telemetry":
                    from .analytics import render_telemetry
                    render_telemetry()
                elif current_mode["view"] == "inbox":
                    from .inbox import render_inbox
                    render_inbox()

@ui.refreshable
def render_sidebar() -> None:
    """Отрисовывает боковое меню."""
    # Логотип
    with ui.row().classes('w-full items-center gap-3 mb-8 px-2 mt-2 no-wrap'):
        ui.icon('menu', size='24px').classes('text-gray-400 cursor-pointer hover:text-white transition-colors shrink-0')
        ui.label('PCAR').classes('text-xl font-medium text-gray-200 truncate')

    def on_new_chat(e=None):
        app_state.create_new_chat()
        current_mode["view"] = "chat"
        render_sidebar.refresh()
        render_content_area.refresh()

    def set_mode(m):
        current_mode["view"] = m
        render_sidebar.refresh()
        render_content_area.refresh()

    # КНОПКА "НОВЫЙ ЧАТ"
    with ui.row().classes('w-full py-3 mb-8 bg-[#202123] hover:bg-[#2b2c2f] text-gray-300 rounded-full cursor-pointer flex items-center justify-center transition-all no-wrap group') \
                 .on('click', on_new_chat):
        ui.icon('add', size='18px').classes('shrink-0')
        ui.label('Новый чат').classes('text-sm font-medium ml-2')

    # ВКЛАДКИ (ИСПОЛЬЗУЕМ GRID ДЛЯ ИДЕАЛЬНОГО ВЫРАВНИВАНИЯ)
    with ui.column().classes('w-full gap-1 mb-8 no-wrap'):
        nav_items = [
            ('chat', 'Чат', 'chat_bubble_outline'),
            ('inbox', 'Входящие', 'inventory_2'),
            ('logs', 'Логи', 'analytics'),
            ('telemetry', 'Телеметрия', 'insights'),
        ]
        for mode, label, item_icon in nav_items:
            is_active = current_mode["view"] == mode
             
            def make_click_handler(m):
                """Функция-фабрика для создания обработчика клика с замыканием m."""
                def handler():
                    set_mode(m)
                return handler
             
            with ui.row().classes(f'w-full h-11 px-4 rounded-full cursor-pointer transition-colors '
                                  f'{"bg-[#282a2c] text-white" if is_active else "bg-transparent text-gray-400 hover:bg-[#202123] hover:text-gray-200"}') \
                                  .style('display: grid; grid-template-columns: 32px minmax(0, 1fr); align-items: center;') \
                                  .on('click', make_click_handler(mode)):
                ui.icon(item_icon, size='20px').classes('justify-self-center')
                ui.label(label).classes('text-[14px] font-medium truncate')

    # СПИСОК ЧАТОВ
    ui.label('ПОСЛЕДНИЕ').classes('text-[11px] text-gray-500 font-bold ml-4 mb-2 tracking-widest')
    
    with ui.element('div').classes('flex-1 w-full overflow-y-auto custom-scrollbar pr-2'):
        with ui.column().classes('w-full gap-1 no-wrap'):
            # Сортировка чатов: pinned first, затем по timestamp последнего сообщения
            sorted_chat_ids = app_state.get_sorted_chats()
            for chat_id in sorted_chat_ids:
                chat_data = app_state.chats_meta.get(chat_id, {})
                title = chat_data.get("title", "Без названия")
                is_current = (chat_id == app_state.current_chat_id) and (current_mode["view"] == "chat")
                is_pinned = chat_id in app_state.pinned_chat_ids

                def switch_chat(cid=chat_id):
                    app_state.switch_chat(cid)
                    current_mode["view"] = "chat"
                    render_sidebar.refresh()
                    render_content_area.refresh()

                # Сетка для чата: 28px (иконка), 1fr (текст), 32px (кнопка меню)
                with ui.row().classes(f'w-full h-10 items-center pl-4 pr-1 rounded-full cursor-pointer transition-colors no-wrap group '
                                      f'{"bg-[#282a2c] text-white" if is_current else "bg-transparent text-gray-400 hover:bg-[#202123] hover:text-gray-200"}') \
                                      .style('display: grid; grid-template-columns: 28px 1fr 32px; align-items: center;') \
                                      .on('click', lambda cid=chat_id: switch_chat(cid)):
                    
                    ui.icon('push_pin' if is_pinned else 'chat_bubble_outline', size='16px').classes('justify-self-start')
                    ui.label(title).classes('text-[14px] truncate font-normal')
                    
                    # Кнопка меню с блокировкой клика родителя
                    with ui.button(icon='more_vert').props('flat round dense size=sm') \
                            .classes('opacity-0 group-hover:opacity-100 transition-opacity text-gray-400 hover:text-white') \
                            .on('click.stop', lambda: None):
                        
                        with ui.menu().classes('bg-[#1e1f20] border border-white/10 text-gray-200 shadow-xl'):
                            ui.menu_item('Закрепить' if not is_pinned else 'Открепить', 
                                         on_click=lambda cid=chat_id: handle_pin(cid)).classes('hover:bg-[#2b2c2f]')
                            ui.menu_item('Переименовать', 
                                         on_click=lambda cid=chat_id: handle_rename(cid)).classes('hover:bg-[#2b2c2f]')
                            ui.separator().classes('bg-white/5')
                            ui.menu_item('Удалить', 
                                         on_click=lambda cid=chat_id: handle_delete(cid)).classes('text-red-400 hover:bg-[#2b2c2f]')

async def handle_pin(chat_id: str):
    app_state.toggle_pin(chat_id)
    render_sidebar.refresh()

async def handle_rename(chat_id: str):
    with ui.dialog() as dialog, ui.card().classes('bg-[#1e1f20] p-6 border border-white/10 shadow-2xl'):
        ui.label('Переименовать чат').classes('text-lg font-medium text-white mb-4')
        new_name = ui.input(value=app_state.chats_meta[chat_id].get('title', '')).classes('w-full mb-6').props('dark rounded outlined')
        with ui.row().classes('w-full justify-end gap-2'):
            ui.button('Отмена', on_click=dialog.close).props('flat text-color=gray')
            def save():
                app_state.update_chat_title(chat_id, new_name.value)
                render_sidebar.refresh()
                dialog.close()
            ui.button('Сохранить', on_click=save).props('unelevated color=indigo')
    dialog.open()

async def handle_delete(chat_id: str):
    if hasattr(app_state, 'delete_chat'):
        app_state.delete_chat(chat_id)
        render_sidebar.refresh()
        from .layout import render_content_area
        render_content_area.refresh()
    else:
        ui.notify('Метод удаления не реализован в state.py', type='warning')
