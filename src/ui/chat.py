"""Окно диалога чата PCAR."""
import asyncio
import nicegui.ui as ui
from .state import app_state

input_field = None
loading_container = None

def render_chat() -> None:
    """Отрисовывает интерфейс чата."""
    global input_field, loading_container

    with ui.column().classes('w-full h-full justify-between no-wrap gap-0 relative bg-[#0e0e10] p-0'):
        
        # Приветствие по центру
        if not app_state.messages or len(app_state.messages) <= 1:
            with ui.column().classes('absolute-center items-center w-full z-0'):
                ui.label('Здравствуй!').classes('text-4xl font-medium text-gray-200 mb-2')
                ui.label('Что нужно сделать?').classes('text-4xl font-medium text-gray-500 mb-8')

        # Область скролла
        with ui.scroll_area().classes('w-full flex-grow z-10 pb-32'):
            with ui.column().classes('w-full max-w-3xl mx-auto gap-6 p-4 pt-12'):
                render_messages()
                loading_container = ui.column().classes('w-full gap-4')

        # ПЛАВАЮЩИЙ ВВОД 
        with ui.page_sticky(position='bottom', x_offset=0, y_offset=24).classes('w-full flex justify-center z-20 pointer-events-none'):
            with ui.row().classes('w-full max-w-3xl items-center bg-[#1e1f20] rounded-[28px] px-6 py-2 shadow-2xl pointer-events-auto border border-white/5 mx-4'):
                
                ui.icon('add_circle_outline', size='24px').classes('text-gray-400 cursor-pointer hover:text-gray-200 transition-colors mr-2')

                # Исправлен Enter: используем keyup.enter.prevent
                input_field = ui.input(placeholder='Спросить PCAR...') \
                    .props('borderless dark dense autofocus') \
                    .classes('flex-grow text-lg text-gray-200 py-2') \
                    .on('keyup.enter.prevent', lambda e: send_message())
                
                with ui.row().classes('gap-3 items-center ml-2'):
                    ui.icon('mic_none', size='24px').classes('text-gray-400 cursor-pointer hover:text-gray-200 transition-colors')
                    ui.button(icon='send', on_click=lambda e: send_message()) \
                        .props('flat round dense color=white').classes('text-white bg-transparent')


@ui.refreshable
def render_messages():
    """Перерисовывает историю сообщений."""
    for msg in app_state.messages:
        if msg["content"].startswith("Привет! Я твой цифровой мозг"):
            continue

        is_user = msg["role"] == "user"
        content = msg["content"]
        
        base_response = content
        metadata = ""
        if "---" in content:
            parts = content.split("---", 1)
            base_response = parts[0].strip()
            metadata = parts[1].strip()

        with ui.row().classes(f'w-full gap-4 {"justify-end" if is_user else "justify-start"}'):
            if not is_user:
                ui.icon('auto_awesome', size='24px').classes('text-indigo-400 mt-2')
            
            with ui.column().classes(f'max-w-[85%] {"bg-[#2b2c2f] px-5 py-3 rounded-[24px]" if is_user else "py-2"}'):
                ui.markdown(base_response).classes('text-[16px] leading-relaxed text-gray-200')
                if metadata and not is_user:
                    ui.label(metadata.replace('*', '')).classes('text-[11px] text-gray-500 mt-2 uppercase tracking-widest font-medium')

async def send_message(e=None) -> None:
    """Обрабатывает отправку сообщения."""
    global input_field, loading_container
    if not input_field: return
        
    prompt = input_field.value.strip()
    if not prompt: return

    input_field.value = ''
    app_state.auto_rename_chat(prompt)
    app_state.messages.append({"role": "user", "content": prompt})
    app_state._save_chat_to_disk()
    
    render_messages.refresh()
    ui.run_javascript('window.scrollTo(0, document.body.scrollHeight)')
    
    loading_container.clear()
    with loading_container:
        with ui.row().classes('w-full gap-4 justify-start items-center'):
            ui.icon('auto_awesome', size='24px').classes('text-indigo-400')
            ui.spinner(size='sm', type='dots', color='indigo-400')

    try:
        await asyncio.to_thread(app_state.bot.process_query, query=prompt)
        
        answer = app_state.bot.last_answer
        intent = getattr(app_state.bot, 'current_intent', 'unknown').upper()
        is_cache = getattr(app_state.bot, 'is_cache_hit', False)
        
        badge = "⚡ КЭШ" if is_cache else "🔍 LLM"
        full_response = f"{answer}\n\n---\n{badge} | {intent}"

        app_state.messages.append({"role": "assistant", "content": full_response})
        app_state._save_chat_to_disk()

    except Exception as e:
        app_state.messages.append({"role": "assistant", "content": f"Ошибка: {str(e)}"})
        
    finally:
        loading_container.clear()
        render_messages.refresh()
        ui.run_javascript('window.scrollTo(0, document.body.scrollHeight)')
        
        from .layout import render_sidebar
        render_sidebar.refresh()