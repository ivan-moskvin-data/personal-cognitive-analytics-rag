"""Дашборды аналитики и телеметрии PCAR."""
import pandas as pd
import plotly.express as px
import sqlite3
import nicegui.ui as ui
from pathlib import Path
from typing import Optional
from .state import HISTORY_DIR
from memory.srs_db import SRSDatabase

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
            
            # Метрики тренировок
            db = SRSDatabase()
            stats = db.get_stats()
            
            with ui.row().classes('w-full gap-3'):
                # Виджет 1: Объем базы
                with ui.column().classes('flex-1 bg-[#1e1f20] rounded-2xl p-4 border border-white/5 items-center justify-center'):
                    ui.icon('inventory_2', size='24px').classes('text-blue-400 mb-1')
                    ui.label(str(stats["total"])).classes('text-2xl font-bold text-white')
                    ui.label('Всего фактов').classes('text-[11px] text-gray-500 uppercase tracking-wider')

                # Виджет 2: Долгосрочная память
                with ui.column().classes('flex-1 bg-[#1e1f20] rounded-2xl p-4 border border-white/5 items-center justify-center'):
                    ui.icon('emoji_events', size='24px').classes('text-yellow-400 mb-1')
                    ui.label(str(stats["long_term"])).classes('text-2xl font-bold text-white')
                    ui.label('В долгосрочной').classes('text-[11px] text-gray-500 uppercase tracking-wider')

                # Виджет 3: Качество обучения (Avg Ease Factor)
                with ui.column().classes('flex-1 bg-[#1e1f20] rounded-2xl p-4 border border-white/5 items-center justify-center'):
                    ui.icon('psychology', size='24px').classes('text-green-400 mb-1')
                    ui.label(str(stats["avg_ease"])).classes('text-2xl font-bold text-white')
                    ui.label('Средняя легкость').classes('text-[11px] text-gray-500 uppercase tracking-wider')
            
            ui.separator().classes('border-slate-800 my-2')
            
            # Learning Metrics (Retention Rate, Lapses и Active Days)
            db = SRSDatabase(Path("data/memory/srs_cards.sqlite"))
            metrics = db.get_learning_metrics()
            
            with ui.row().classes('w-full gap-4 mb-6'):
                # Карточка 1: Усвоение (Retention Rate)
                retention = metrics["retention_rate"]
                retention_color = "text-green-500" if retention >= 80 else "text-red-500"
                with ui.card().classes('flex-1 bg-slate-800 border-slate-700 rounded-xl p-6 shadow-lg'):
                    ui.label("Усвоение (Retention)").classes('text-sm text-gray-400')
                    ui.label(f"{retention}%").classes(f'text-2xl font-bold {retention_color} mt-1')
                
                # Карточка 2: Проблемные карточки (Lapses)
                lapsed = metrics["lapsed_cards"]
                lapsed_color = "text-red-500" if lapsed > 5 else "text-green-500"
                lapsed_icon = "warning" if lapsed > 5 else "check_circle"
                with ui.card().classes('flex-1 bg-slate-800 border-slate-700 rounded-xl p-6 shadow-lg'):
                    ui.label("Проблемные карточки").classes('text-sm text-gray-400')
                    with ui.row().classes('items-center gap-2 mt-1'):
                        ui.icon(lapsed_icon, size='24px').classes(f'{lapsed_color}')
                        ui.label(str(lapsed)).classes(f'text-2xl font-bold {lapsed_color}')
                
                # Карточка 3: Частота сессий Active Recall (за 7 дней)
                active_days = metrics.get("active_days", 0)
                if active_days >= 3:
                    active_color = "text-green-400"
                    has_streak = True
                elif active_days > 0:
                    active_color = "text-yellow-400"
                    has_streak = False
                else:
                    active_color = "text-red-400"
                    has_streak = False
                
                with ui.card().classes('flex-1 bg-slate-800 border-slate-700 rounded-xl p-6 shadow-lg'):
                    ui.label("Тренировки (за 7 дней)").classes('text-sm text-gray-400')
                    with ui.row().classes('items-center gap-2 mt-1'):
                        ui.label(f"{active_days} дн.").classes(f'text-2xl font-bold {active_color}')
                        if has_streak:
                            ui.icon('local_fire_department', color='orange', size='sm')
                    ui.label("Цель: 3-5").classes('text-xs text-gray-400')
            
            ui.separator().classes('border-slate-800 my-2')
            
            # Charts
            with ui.row().classes('w-full gap-4'):
                with ui.card().classes('flex-1 bg-slate-800/80 rounded-xl p-6 shadow-lg border border-slate-700/50'):
                    ui.label('Популярные Интенты').classes('text-lg font-semibold text-gray-200 mb-4')
                    
                    df['clean_intent'] = df['intent'].apply(lambda x: x[:30] + '...' if len(str(x)) > 30 else x)
                    
                    fig_intent = px.pie(df, names='clean_intent', hole=0.4, color_discrete_sequence=px.colors.sequential.RdBu)
                    fig_intent.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='white'))
                    ui.plotly(fig_intent).classes('w-full')
                
                # График 2: Задержка по интентам (Скорость LLM)
                with ui.card().classes('flex-1 bg-slate-800/80 rounded-xl p-6 shadow-lg border border-slate-700/50'):
                    ui.label('Время ответа (по типам задач)').classes('text-lg font-semibold text-gray-200 mb-4')
                    
                    # Берем статистику ТОЛЬКО по реальным запросам к нейросети (без кэша)
                    df_llm = df[df['cache_hit'] == 0].copy()
                    
                    if not df_llm.empty:
                        # Рисуем ящики с усами для каждого интента
                        fig_lat = px.box(df_llm, x='intent', y='latency_ms', color='intent', points="all", 
                                         labels={'latency_ms': 'Задержка (мс)', 'intent': 'Тип запроса'},
                                         color_discrete_sequence=px.colors.qualitative.Pastel)
                        
                        fig_lat.update_layout(
                            paper_bgcolor='rgba(0,0,0,0)', 
                            plot_bgcolor='rgba(0,0,0,0)', 
                            font=dict(color='white'),
                            showlegend=False,
                            xaxis={'categoryorder':'total descending'}
                        )
                        ui.plotly(fig_lat).classes('w-full')
                    else:
                        ui.label('Пока нет данных от нейросети').classes('text-gray-400 text-center mt-10 w-full')
        
        except Exception as e:
            with ui.card().classes('bg-slate-800/50 border border-red-600/30 p-6 rounded-xl'):
                ui.label(f'Ошибка загрузки телеметрии: {e}').classes('text-red-500 text-lg')

def load_data() -> Optional[pd.DataFrame]:
    """Ленивая загрузка и кэширование исторических логов из Parquet."""
    import os
    # Используем parent.parent.parent для достижения корня проекта
    base_dir = Path(__file__).resolve().parent.parent.parent
    file_path = base_dir / "data" / "processed" / "cleaned_logs.parquet"
    
    # Логирование в файл для отладки
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "analytics_debug.log"
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[DEBUG] load_data: cwd = {os.getcwd()}\n")
        f.write(f"[DEBUG] load_data: base_dir = {base_dir}\n")
        f.write(f"[DEBUG] load_data: file_path = {file_path}\n")
        f.write(f"[DEBUG] load_data: file_path.resolve() = {file_path.resolve()}\n")
        f.write(f"[DEBUG] load_data: exists = {file_path.exists()}\n")
        if file_path.exists():
            f.write(f"[DEBUG] load_data: file_size = {file_path.stat().st_size} bytes\n")
            processed_dir = file_path.parent
            f.write(f"[DEBUG] load_data: files in {processed_dir} = {list(processed_dir.glob('*'))}\n")
            try:
                df = pd.read_parquet(file_path)
                f.write(f"[DEBUG] load_data: df.shape = {df.shape}\n")
                return df if not df.empty else None
            except Exception as e:
                f.write(f"[DEBUG] load_data: read_parquet error = {e}\n")
                return None
        f.write(f"[DEBUG] load_data: file not found\n")
    return None
