"""Дашборды аналитики и телеметрии PCAR."""
import pandas as pd
import plotly.express as px
import sqlite3
import nicegui.ui as ui
from pathlib import Path
from typing import Optional
from .state import HISTORY_DIR

def render_dashboard() -> None:
    """Отрисовывает аналитический дашборд (EDA)."""
    with ui.column().classes('gap-6 w-full max-w-7xl mx-auto'):
        # Header
        with ui.row().classes('w-full items-center justify-between'):
            ui.label('📊 Аналитика чат-логов').classes('text-3xl font-bold text-white')
            ui.label('Визуализация исторических данных из cleaned_logs.parquet').classes('text-gray-400')
        
        df = load_data()
        if df is None:
            with ui.card().classes('bg-slate-800/50 border border-yellow-600/30 p-6 rounded-xl'):
                ui.label('⚠️ Файл cleaned_logs.parquet не найден или не содержит данных.').classes('text-yellow-500 text-lg')
            return
        
        # Предварительная проверка наличия колонок
        has_role = 'role' in df.columns
        has_time = 'timestamp' in df.columns
        valid_times = df['timestamp'].dropna() if has_time else pd.Series(dtype='datetime64[ns]')
        
        # KPI Cards
        with ui.row().classes('w-full gap-4'):
            kpi_data = [
                ('Всего сообщений', f"{len(df):,}".replace(",", " "), 'chat', 'indigo'),
                ('Активных ролей', str(df['role'].nunique() if has_role else 0), 'people', 'purple'),
                ('Первое сообщение', valid_times.min().strftime('%d.%m.%Y') if not valid_times.empty else 'N/A', 'schedule', 'green'),
            ]
            
            for title, value, icon, color in kpi_data:
                with ui.card().classes('flex-1 bg-slate-800/80 rounded-xl p-6 shadow-lg border border-slate-700/50 hover:border-slate-600 transition-all'):
                    ui.icon(icon, size='32px').classes(f'text-{color}-500 mb-3')
                    ui.label(title).classes('text-sm text-gray-400')
                    ui.label(value).classes('text-3xl font-bold text-white mt-1')
        
        ui.separator().classes('border-slate-800 my-2')
        
        # Charts Row 1
        with ui.row().classes('w-full gap-4'):
            with ui.card().classes('flex-1 bg-slate-800/80 rounded-xl p-6 shadow-lg border border-slate-700/50'):
                ui.label('Распределение по ролям').classes('text-lg font-semibold text-gray-200 mb-4')
                if has_role:
                    role_counts = df['role'].value_counts().reset_index(name='count')
                    fig_pie = px.pie(role_counts, names='role', values='count', hole=0.4,
                                    color_discrete_sequence=px.colors.qualitative.Pastel)
                    fig_pie.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='white'))
                    ui.plotly(fig_pie).classes('w-full')
        
        with ui.card().classes('flex-1 bg-slate-800/80 rounded-xl p-6 shadow-lg border border-slate-700/50'):
            ui.label('⏰ Пики активности (по часам)').classes('text-lg font-semibold text-gray-200 mb-4')
            if not valid_times.empty:
                hour_counts = valid_times.dt.hour.value_counts().rename_axis('hour').reset_index(name='count')
                fig_hour = px.bar(hour_counts, x='hour', y='count', labels={'hour': 'Час', 'count': 'Кол-во'},
                                 color_discrete_sequence=['#818cf8'])
                fig_hour.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='white'))
                ui.plotly(fig_hour).classes('w-full')
        
        # Chart Row 2
        ui.label('📈 Динамика во времени').classes('text-lg font-semibold text-gray-200 mt-4')
        if not valid_times.empty:
            with ui.card().classes('w-full bg-slate-800/80 rounded-xl p-6 shadow-lg border border-slate-700/50'):
                daily_counts = valid_times.dt.date.value_counts().sort_index().rename_axis('date').reset_index(name='count')
                fig_line = px.line(daily_counts, x='date', y='count', labels={'date': 'Дата', 'count': 'Сообщения'})
                fig_line.update_traces(line=dict(color='#818cf8', width=3))
                fig_line.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='white'))
                ui.plotly(fig_line).classes('w-full')

def render_telemetry() -> None:
    """Отрисовывает дашборд производительности RAG."""
    with ui.column().classes('gap-6 w-full max-w-7xl mx-auto'):
        # Header
        with ui.row().classes('w-full items-center justify-between'):
            ui.label('📈 Мониторинг здоровья PCAR').classes('text-3xl font-bold text-white')
            ui.label('Анализ производительности: Оркестратор, Роутер, Кэш и LLM').classes('text-gray-400')
        
        db_path = Path(__file__).resolve().parent.parent.parent / "data" / "vector_db" / "telemetry.db"
        
        if not db_path.exists():
            with ui.card().classes('bg-slate-800/50 border border-blue-600/30 p-6 rounded-xl'):
                ui.label('ℹ️ База телеметрии пока не создана. Задай пару вопросов боту в чате!').classes('text-blue-400 text-lg')
            return
        
        try:
            with sqlite3.connect(db_path) as conn:
                df = pd.read_sql("SELECT * FROM telemetry", conn)
            
            if df.empty:
                with ui.card().classes('bg-slate-800/50 border border-yellow-600/30 p-6 rounded-xl'):
                    ui.label('База пуста. Нужно больше данных для анализа.').classes('text-yellow-500 text-lg')
                return
            
            # KPI блоки
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            total_req = len(df)
            cache_hits = df['cache_hit'].sum()
            hit_rate = (cache_hits / total_req) * 100 if total_req > 0 else 0
            avg_latency = df['latency_ms'].mean() / 1000 if total_req > 0 else 0
            
            with ui.row().classes('w-full gap-4'):
                kpi_data = [
                    ('Всего запросов', str(total_req), 'api', 'indigo'),
                    ('Hit Rate (Кэш)', f"{hit_rate:.1f}%", 'cached', 'green'),
                    ('Средняя задержка', f"{avg_latency:.2f} сек", 'speed', 'purple'),
                ]
                
                for title, value, icon, color in kpi_data:
                    with ui.card().classes('flex-1 bg-slate-800/80 rounded-xl p-6 shadow-lg border border-slate-700/50'):
                        ui.icon(icon, size='32px').classes(f'text-{color}-500 mb-3')
                        ui.label(title).classes('text-sm text-gray-400')
                        ui.label(value).classes('text-3xl font-bold text-white mt-1')
            
            ui.separator().classes('border-slate-800 my-2')
            
            # Charts
            with ui.row().classes('w-full gap-4'):
                with ui.card().classes('flex-1 bg-slate-800/80 rounded-xl p-6 shadow-lg border border-slate-700/50'):
                    ui.label('Популярные Интенты').classes('text-lg font-semibold text-gray-200 mb-4')
                    fig_intent = px.pie(df, names='intent', hole=0.4, color_discrete_sequence=px.colors.sequential.RdBu)
                    fig_intent.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='white'))
                    ui.plotly(fig_intent).classes('w-full')
                
                with ui.card().classes('flex-1 bg-slate-800/80 rounded-xl p-6 shadow-lg border border-slate-700/50'):
                    ui.label('Скорость: Кэш vs LLM').classes('text-lg font-semibold text-gray-200 mb-4')
                    fig_lat = px.box(df, x='cache_hit', y='latency_ms',
                                    points="all", labels={'cache_hit': 'Из кэша (1=Да)', 'latency_ms': 'мс'})
                    fig_lat.update_traces(marker=dict(color=['#ef4444', '#22c55e']))
                    fig_lat.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='white'))
                    ui.plotly(fig_lat).classes('w-full')
        
        except Exception as e:
            with ui.card().classes('bg-slate-800/50 border border-red-600/30 p-6 rounded-xl'):
                ui.label(f'Ошибка загрузки телеметрии: {e}').classes('text-red-500 text-lg')

def load_data() -> Optional[pd.DataFrame]:
    """Ленивая загрузка и кэширование исторических логов из Parquet."""
    file_path = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "cleaned_logs.parquet"
    if file_path.exists():
        try:
            df = pd.read_parquet(file_path)
            return df if not df.empty else None
        except Exception:
            pass
    return None