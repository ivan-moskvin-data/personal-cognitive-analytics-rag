"""Окно диалога чата PCAR (Pure Grid)."""
import asyncio
import nicegui.ui as ui
from .state import app_state

input_field = None
loading_container = None

def render_chat() -> None:
    """Отрисовывает интерфейс чата."""
    global input_field, loading_container

    # Контейнер чата занимает ВСЕ место. overflow-hidden критичен.
    with ui.element('div').classes('w-full h-full flex flex-col bg-[#0e0e10] p-0 m-0 overflow-hidden relative'):
        
        # 1. ОБЛАСТЬ СКРОЛЛА (занимает flex-1)
        with ui.element('div').classes('flex-1 w-full overflow-y-auto custom-scrollbar') as scroll_area:
            with ui.element('div').classes('w-full max-w-3xl mx-auto flex flex-col gap-8 p-4 pt-12 pb-12'):
                
                # Приветствие по центру если пусто
                if not app_state.messages or len(app_state.messages) <= 0:
                    with ui.column().classes('items-center w-full mt-32'):
                        ui.label('Здравствуй!').classes('text-4xl font-medium text-gray-200 mb-2')
                        ui.label('Чем я могу помочь?').classes('text-xl font-medium text-gray-500')
                
                render_messages()
                loading_container = ui.element('div').classes('w-full flex flex-col gap-4')
                
        # 2. ПАНЕЛЬ ВВОДА (shrink-0 заставляет её стоять на месте)
        with ui.element('div').classes('w-full shrink-0 p-4 pb-8 bg-[#0e0e10] z-20'):
            with ui.row().classes('w-full max-w-3xl mx-auto flex items-center bg-[#1e1f20] rounded-[28px] px-6 py-1 shadow-2xl border border-white/5 no-wrap'):
                
                ui.icon('add_circle_outline', size='24px').classes('text-gray-400 cursor-pointer hover:text-white transition-colors shrink-0 mr-2')

                input_field = ui.textarea(placeholder='Введите запрос...') \
                    .props('borderless dark dense autofocus autogrow') \
                    .classes('flex-1 text-lg text-gray-200 py-2 custom-textarea') \
                    .style('max-height: 200px; overflow-y: auto;') \
                    .on('keydown.enter.prevent', send_message)
                
                ui.icon('mic_none', size='24px').classes('text-gray-400 cursor-pointer hover:text-white transition-colors shrink-0 mx-2')
                
                # Кнопка отправки
                with ui.element('button').classes(
                    'w-10 h-10 rounded-full flex items-center justify-center text-gray-400 hover:text-white hover:bg-white/10 transition-all border-none outline-none cursor-pointer shrink-0 ml-1 bg-transparent'
                ).on('click', send_message):
                    ui.icon('send', size='20px')


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

        with ui.element('div').classes(f'w-full flex gap-5 no-wrap {"justify-end" if is_user else "justify-start"}'):
            if not is_user:
                with ui.element('div').classes('mt-1 shrink-0'):
                    ui.icon('auto_awesome', size='24px').classes('text-indigo-400')
            
            msg_box_classes = 'max-w-[85%] px-0 py-0 '
            if is_user:
                msg_box_classes = 'max-w-[85%] px-5 py-3 rounded-[24px] bg-[#2b2c2f] text-gray-200'
            
            with ui.element('div').classes(msg_box_classes):
                ui.markdown(base_response).classes('text-[16px] leading-relaxed break-words text-gray-200')
                if metadata and not is_user:
                    ui.label(metadata.replace('*', '')).classes('text-[11px] text-gray-500 mt-3 uppercase tracking-widest font-semibold')


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
    # Скроллим только область скролла
    await ui.run_javascript('const scroller = document.querySelector(".flex-1.overflow-y-auto"); if(scroller) scroller.scrollTo(0, scroller.scrollHeight);')
    
    loading_container.clear()
    with loading_container:
        with ui.element('div').classes('w-full flex gap-5 justify-start items-center no-wrap'):
            ui.icon('auto_awesome', size='24px').classes('text-indigo-400 shrink-0')
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

    except Exception as ex:
        app_state.messages.append({"role": "assistant", "content": f"Ошибка: {str(ex)}"})
        
    finally:
        loading_container.clear()
        render_messages.refresh()
        await ui.run_javascript('const scroller = document.querySelector(".flex-1.overflow-y-auto"); if(scroller) scroller.scrollTo(0, scroller.scrollHeight);')
        
        from .layout import render_sidebar
        render_sidebar.refresh()
