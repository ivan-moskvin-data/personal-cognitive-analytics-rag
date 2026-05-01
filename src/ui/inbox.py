"""Входящие патчи для PCAR."""
import re
import asyncio
import nicegui.ui as ui
from pathlib import Path
from typing import Optional
from .state import app_state

INBOX_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "inbox"

def render_inbox() -> None:
    """Отрисовывает интерфейс входящих патчей."""
    with ui.column().classes('gap-6 w-full max-w-5xl mx-auto'):
        # Header
        with ui.row().classes('w-full items-center justify-between'):
            ui.label('📥 Входящие знания').classes('text-3xl font-bold text-white')
            ui.label('Факты, выделенные из общения. Нажми «Принять», чтобы сохранить их навсегда.').classes('text-gray-400')
        
        patches = list(INBOX_PATH.glob("*.md"))
        
        if not patches:
            with ui.card().classes('bg-gradient-to-br from-green-900/20 to-emerald-900/20 border border-green-600/30 p-8 rounded-xl'):
                with ui.row().classes('items-center gap-3'):
                    ui.icon('check_circle', size='48px').classes('text-green-500')
                    ui.label('Все знания усвоены!').classes('text-green-500 text-2xl font-semibold')
            return
        
        for patch_file in patches:
            render_patch_expansion(patch_file)

def render_patch_expansion(patch_file: Path) -> None:
    """Отрисовывает раскрывающийся блок для одного патча."""
    content = patch_file.read_text(encoding="utf-8")
    # Парсим файл
    file_match = re.search(r"FILE:\s*(.+)", content)
    patch_match = re.search(r"<<<<<<<\s*SEARCH\s*(.*?)\s*=======\s*(.*?)\s*>>>>>>>\s*REPLACE", content, re.DOTALL)
    
    with ui.card().classes('w-full bg-slate-800/80 rounded-xl shadow-lg border border-slate-700/50 hover:border-slate-600 transition-all'):
        with ui.expansion(f"📄 {patch_file.name}", icon="folder").classes('w-full'):
            with ui.column().classes('gap-4 p-6'):
                if file_match and patch_match:
                    filename = file_match.group(1).strip()
                    search_text = patch_match.group(1).strip()
                    replace_text = patch_match.group(2).strip()
                    
                    ui.label(f'Целевой файл: {filename}').classes('text-sm font-mono text-indigo-400 bg-indigo-900/20 px-3 py-2 rounded-lg')
                    
                    if not search_text:
                        with ui.card().classes('bg-green-900/20 border border-green-600/30 p-4 rounded-lg'):
                            ui.label('➕ Добавление новых данных:').classes('text-green-500 font-semibold mb-2')
                            ui.markdown(replace_text).classes('text-sm text-gray-300')
                    else:
                        with ui.column().classes('gap-3'):
                            ui.label('📝 Изменение существующих данных:').classes('text-yellow-500 font-semibold')
                            
                            with ui.card().classes('bg-slate-900/80 border border-slate-700 p-4 rounded-lg'):
                                ui.label('Было:').classes('text-sm text-gray-400 mb-2')
                                ui.code(search_text, language='markdown').classes('bg-transparent text-xs text-red-400')
                            
                            with ui.card().classes('bg-slate-900/80 border border-slate-700 p-4 rounded-lg'):
                                ui.label('Станет:').classes('text-sm text-gray-400 mb-2')
                                ui.markdown(replace_text).classes('text-sm text-green-400')
                else:
                    ui.code(content, language='markdown').classes('bg-slate-900 rounded-lg p-4 text-xs')
                
                # Кнопки действий
                with ui.row().classes('gap-3 mt-4'):
                    ui.button(
                        '✅ Принять',
                        on_click=lambda pf=patch_file: handle_accept_patch(pf)
                    ).classes('bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-500 hover:to-emerald-500 text-white rounded-lg px-6 py-2.5 shadow-lg transition-all font-medium')
                    
                    ui.button(
                        '🗑️ Удалить',
                        on_click=lambda pf=patch_file: handle_delete_patch(pf)
                    ).classes('bg-gradient-to-r from-red-600 to-rose-600 hover:from-red-500 hover:to-rose-500 text-white rounded-lg px-6 py-2.5 shadow-lg transition-all font-medium')

async def handle_accept_patch(patch_file: Path) -> None:
    """Обрабатывает принятие патча."""
    app_state.apply_patch(patch_file)
    ui.notify("Патч успешно применен", type="positive", color='green')
    await asyncio.sleep(0.5)
    ui.refresh()

async def handle_delete_patch(patch_file: Path) -> None:
    """Обрабатывает удаление патча."""
    app_state.delete_patch(patch_file)
    ui.notify("Патч удален", type="warning", color='yellow')
    await asyncio.sleep(0.5)
    ui.refresh()