import sys
import pandas as pd
import streamlit as st
import plotly.express as px
import sqlite3
from pathlib import Path
from typing import Optional, Dict, List, Any
import json
from hitl.auto_sync import AutoSync
import uuid

HISTORY_DIR = Path(__file__).resolve().parent.parent / "data" / "history"
METADATA_FILE = HISTORY_DIR / "metadata.json"

# Убедимся, что директория для истории существует
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

# --- НАСТРОЙКА СТРАНИЦЫ ---
st.set_page_config(page_title="PCAR | Цифровой Мозг", page_icon="🧠", layout="wide")

# Подключение локального модуля (допустимый хак для Streamlit)
sys.path.append(str(Path(__file__).resolve().parent))
from orchestrator import PCARBrain

def save_metadata() -> None:
    """Сохраняет метаданные чатов в JSON файл."""
    metadata = {
        "chats_meta": st.session_state.get("chats_meta", {}),
        "pinned_chat_ids": st.session_state.get("pinned_chat_ids", []),
        "folders": st.session_state.get("folders", {})
    }
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

def load_metadata() -> Dict[str, Any]:
    """Загружает метаданные чатов из JSON файла."""
    if METADATA_FILE.exists():
        try:
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    "chats_meta": data.get("chats_meta", {}),
                    "pinned_chat_ids": data.get("pinned_chat_ids", []),
                    "folders": data.get("folders", {})
                }
        except:
            pass
    return {"chats_meta": {}, "pinned_chat_ids": [], "folders": {}}

def save_chat_to_disk(chat_id: Optional[str] = None) -> None:
    """Сохраняет текущую сессию чата в файл."""
    if chat_id is None:
        chat_id = st.session_state.get("current_chat_id")
    if chat_id:
        chat_file = HISTORY_DIR / f"{chat_id}.json"
        with open(chat_file, "w", encoding="utf-8") as f:
            json.dump(st.session_state.messages, f, ensure_ascii=False, indent=2)

def load_chat_from_disk(chat_id: str) -> List[Dict[str, str]]:
    """Загружает историю чата из файла."""
    chat_file = HISTORY_DIR / f"{chat_id}.json"
    if chat_file.exists():
        try:
            with open(chat_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return []

@st.cache_data
def load_data() -> Optional[pd.DataFrame]:
    """Ленивая загрузка и кэширование исторических логов из Parquet."""
    file_path = Path(__file__).resolve().parent.parent / "data" / "processed" / "cleaned_logs.parquet"
    if file_path.exists():
        df = pd.read_parquet(file_path)
        # Защита от создания пустого дашборда
        return df if not df.empty else None
    return None


def init_session() -> None:
    if "bot" not in st.session_state:
        with st.spinner("🧠 Подключение к нейросети..."):
            st.session_state.bot = PCARBrain()
    
    # Загружаем метаданные чатов
    metadata = load_metadata()
    st.session_state.chats_meta = metadata["chats_meta"]
    st.session_state.pinned_chat_ids = metadata["pinned_chat_ids"]
    st.session_state.folders = metadata["folders"]
    
    # Инициализация current_chat_id
    if "current_chat_id" not in st.session_state:
        if st.session_state.chats_meta:
            # Берем последний созданный чат (последний в словаре)
            last_chat_id = list(st.session_state.chats_meta.keys())[-1]
            st.session_state.current_chat_id = last_chat_id
        else:
            # Создаем новый чат, если нет существующих
            st.session_state.current_chat_id = str(uuid.uuid4())
            st.session_state.chats_meta[st.session_state.current_chat_id] = {"title": "Новый чат", "folderId": None}
            save_metadata()
    
    # Загружаем сообщения для текущего чата
    if "messages" not in st.session_state:
        saved_messages = load_chat_from_disk(st.session_state.current_chat_id)
        if saved_messages:
            st.session_state.messages = saved_messages
        else:
            st.session_state.messages = [
                {"role": "assistant", "content": "Привет! Я твой цифровой мозг. Все наши разговоры теперь сохраняются, даже если ты обновишь страницу!"}
            ]


def render_chat() -> None:
    """Изолированная логика отрисовки RAG-чата."""
    st.title("🧠 PCAR: Интеллектуальный поиск")
    
    # Отрисовка истории
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    # Обработка нового ввода
    if prompt := st.chat_input("Напиши свой запрос здесь (например: Расскажи про стек ASSE)..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        save_chat_to_disk(st.session_state.current_chat_id)
        with st.chat_message("user"):
            st.markdown(prompt)
            
        with st.chat_message("assistant"):
            with st.spinner("Анализирую знания..."):
                bot = st.session_state.bot
                bot.process_query(query=prompt)
                
                # Извлечение результатов
                answer = bot.last_answer
                intent = getattr(bot, 'current_intent', 'unknown').upper()
                is_cache = getattr(bot, 'is_cache_hit', False)
                
                # Форматирование и вывод
                badge = "⚡ Из локального кэша" if is_cache else "🔍 Сгенерировано нейросетью"
                full_response = f"{answer}\n\n---\n*Интент: `{intent}` | {badge}*"
                
                st.markdown(full_response)
                
        st.session_state.messages.append({"role": "assistant", "content": full_response})
        save_chat_to_disk(st.session_state.current_chat_id)

def render_inbox():
    st.title("📥 Входящие знания")
    st.caption("Факты, выделенные из общения. Нажми «Принять», чтобы сохранить их навсегда.")

    inbox_path = Path(__file__).resolve().parent.parent / "data" / "inbox"
    patches = list(inbox_path.glob("*.md"))

    if not patches:
        st.success("Все знания усвоены!")
        return

    for patch_file in patches:
        with st.expander(f"📄 Предложение: {patch_file.name}", expanded=True):
            content = patch_file.read_text(encoding="utf-8")
            st.code(content, language="markdown")
            
            c1, c2 = st.columns(2)
            if c1.button("✅ Принять", key=f"ok_{patch_file.name}"):
                # Ставим пометку одобрения и запускаем синхронизацию
                patch_file.write_text(f"[x]\n{content}", encoding="utf-8")
                AutoSync().run()
                st.rerun()
                
            if c2.button("🗑️ Удалить", key=f"del_{patch_file.name}"):
                patch_file.unlink()
                st.rerun()

def render_dashboard() -> None:
    """Изолированная логика аналитического дашборда (EDA)."""
    st.title("📊 Аналитика чат-логов")
    st.caption("Визуализация исторических данных из `cleaned_logs.parquet`")
    
    df = load_data()
    if df is None:
        st.warning("⚠️ Файл `cleaned_logs.parquet` не найден или не содержит данных.")
        return
        
    # Предварительная проверка наличия колонок для избежания спама if-блоками
    has_role = 'role' in df.columns
    has_time = 'timestamp' in df.columns

    # Отсекаем пустые даты для корректной математики
    valid_times = df['timestamp'].dropna() if has_time else pd.Series(dtype='datetime64[ns]')

    c1, c2, c3 = st.columns(3)
    c1.metric("Всего сообщений", f"{len(df):,}".replace(",", " "))
    
    if has_role:
        c2.metric("Активных ролей", df['role'].nunique())
    if not valid_times.empty:
        c3.metric("Первое сообщение", valid_times.min().strftime('%d.%m.%Y'))
        
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Распределение по ролям")
        if has_role:
            # Оптимизированный агрегат для Plotly
            role_counts = df['role'].value_counts().reset_index(name='count')
            fig_pie = px.pie(role_counts, names='role', values='count', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig_pie, use_container_width=True)
            
    with col2:
        st.subheader("⏰ Пики активности (по часам)")
        if not valid_times.empty:
            hour_counts = valid_times.dt.hour.value_counts().rename_axis('hour').reset_index(name='count')
            fig_hour = px.bar(hour_counts, x='hour', y='count', labels={'hour': 'Час', 'count': 'Кол-во'}, color_discrete_sequence=['#AB63FA'])
            st.plotly_chart(fig_hour, use_container_width=True)
            
    st.subheader("📈 Динамика во времени")
    if not valid_times.empty:
        # Использование dt.date вместо dt.floor('D')
        daily_counts = valid_times.dt.date.value_counts().sort_index().rename_axis('date').reset_index(name='count')
        fig_line = px.line(daily_counts, x='date', y='count', labels={'date': 'Дата', 'count': 'Сообщения'})
        st.plotly_chart(fig_line, use_container_width=True)

def render_telemetry():
    """Отрисовка дашборда производительности RAG на основе telemetry.db"""
    st.title("📈 Мониторинг здоровья PCAR")
    st.caption("Анализ производительности: Оркестратор, Роутер, Кэш и LLM")
    
    # Путь к базе телеметрии
    db_path = Path(__file__).resolve().parent.parent / "data" / "vector_db" / "telemetry.db"
    
    if not db_path.exists():
        st.info("ℹ️ База телеметрии пока не создана. Задай пару вопросов боту в чате!")
        return

    try:
        with sqlite3.connect(db_path) as conn:
            df = pd.read_sql("SELECT * FROM telemetry", conn)
        
        if df.empty:
            st.warning("База пуста. Нужно больше данных для анализа.")
            return

        # KPI блоки
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        total_req = len(df)
        cache_hits = df['cache_hit'].sum()
        hit_rate = (cache_hits / total_req) * 100
        avg_latency = df['latency_ms'].mean() / 1000

        c1, c2, c3 = st.columns(3)
        c1.metric("Всего запросов", total_req)
        c2.metric("Hit Rate (Кэш)", f"{hit_rate:.1f}%")
        c3.metric("Средняя задержка", f"{avg_latency:.2f} сек")

        st.markdown("---")

        # Графики
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Популярные Интенты")
            fig_intent = px.pie(df, names='intent', hole=0.4, color_discrete_sequence=px.colors.sequential.RdBu)
            st.plotly_chart(fig_intent, use_container_width=True)
            
        with col2:
            st.subheader("Скорость: Кэш vs LLM")
            fig_lat = px.box(df, x='cache_hit', y='latency_ms', 
                             points="all", labels={'cache_hit': 'Из кэша (1=Да)', 'latency_ms': 'мс'})
            st.plotly_chart(fig_lat, use_container_width=True)

    except Exception as e:
        st.error(f"Ошибка загрузки телеметрии: {e}")

def render_sidebar() -> None:
    """
    Отрисовывает боковое меню (сайдбар) с историей чатов.
    Использует предварительно сгруппированные словари для O(1) доступа к данным.
    """
    # Edge Case: Защита от падения, если состояние еще не инициализировано
    _init_sidebar_state()

    with st.sidebar:
        # Кнопка создания нового чата
        if st.button("➕ Новый чат", use_container_width=True):
            _create_new_chat()
            
        st.markdown("---")
        
        # Рендер закрепленных чатов
        st.write("📌 **Закрепленные**")
        pinned_ids: List[str] = st.session_state.pinned_chat_ids
        
        if not pinned_ids:
            st.caption("Нет закрепленных чатов")
        else:
            for chat_id in pinned_ids:
                # O(1) получение метаданных по ключу
                chat_data = st.session_state.chats_meta.get(chat_id, {})
                title = chat_data.get("title", "Без названия")
                is_current = chat_id == st.session_state.get("current_chat_id")
                emoji = "🔹" if is_current else "💬"
                
                if st.button(f"{emoji} {title}", key=f"pin_{chat_id}", use_container_width=True):
                    _switch_chat(chat_id)

        # Рендер всех чатов (в обратном порядке)
        st.write("💬 **Чаты**")
        # Получаем все chat_id, исключая закрепленные, и сортируем в обратном порядке
        all_chat_ids = list(st.session_state.chats_meta.keys())
        for chat_id in reversed(all_chat_ids):
            if chat_id in pinned_ids:
                continue  # Пропускаем закрепленные чаты
            chat_data = st.session_state.chats_meta.get(chat_id, {})
            title = chat_data.get("title", "Без названия")
            is_current = chat_id == st.session_state.get("current_chat_id")
            emoji = "🔹" if is_current else "💬"
            
            if st.button(f"{emoji} {title}", key=f"chat_{chat_id}", use_container_width=True):
                _switch_chat(chat_id)

        # Рендер папок
        st.write("📁 **Папки**")
        folders: Dict[str, List[str]] = st.session_state.folders
        
        if not folders:
            st.caption("Нет созданных папок")
        else:
            for folder_name, chat_ids in folders.items():
                with st.expander(f"📁 {folder_name}"):
                    for chat_id in chat_ids:
                        # O(1) получение метаданных по ключу
                        chat_data = st.session_state.chats_meta.get(chat_id, {})
                        title = chat_data.get("title", "Без названия")
                        is_current = chat_id == st.session_state.get("current_chat_id")
                        emoji = "🔹" if is_current else "💬"
                        
                        if st.button(f"{emoji} {title}", key=f"fld_{folder_name}_{chat_id}", use_container_width=True):
                            _switch_chat(chat_id)


def _init_sidebar_state() -> None:
    """Инициализирует структуры данных для сайдбара, если их нет."""
    if "chats_meta" not in st.session_state:
        # Главное хранилище O(1). Формат: {chat_id: {"title": "...", "isPinned": True, ...}}
        st.session_state.chats_meta = {} 
    if "pinned_chat_ids" not in st.session_state:
        # Индекс закрепленных чатов
        st.session_state.pinned_chat_ids = []
    if "folders" not in st.session_state:
        # Индекс папок O(1). Формат: {folder_id/name: [chat_id_1, chat_id_2]}
        st.session_state.folders = {}


def _create_new_chat() -> None:
    """Создает новый чат и переключается на него."""
    chat_id = str(uuid.uuid4())
    st.session_state.current_chat_id = chat_id
    st.session_state.messages = [
        {"role": "assistant", "content": "Привет! Я твой цифровой мозг. Все наши разговоры теперь сохраняются, даже если ты обновишь страницу!"}
    ]
    # Добавляем чат в метаданные
    st.session_state.chats_meta[chat_id] = {"title": "Новый чат", "folderId": None}
    save_metadata()
    save_chat_to_disk(chat_id)
    st.rerun()


def _switch_chat(chat_id: str) -> None:
    """Переключает контекст на выбранный чат."""
    if st.session_state.get("current_chat_id") != chat_id:
        st.session_state.current_chat_id = chat_id
        # Удаляем старые сообщения и загружаем новые
        if "messages" in st.session_state:
            del st.session_state.messages
        # Загружаем сообщения для нового чата
        st.session_state.messages = load_chat_from_disk(chat_id)
        st.rerun()

# ==========================================
# ТОЧКА ВХОДА СИСТЕМЫ
# ==========================================
init_session()

with st.sidebar:
    st.title("⚙️ Управление PCAR")
    app_mode = st.radio("Режим:", ["💬 Чат", "📊 Логи", "📈 Телеметрия", "📥 Входящие"])
    
    st.markdown("---")
    
    render_sidebar()

    st.markdown("---")
    if st.button("🧹 Очистить историю чата"):
        st.session_state.messages = [st.session_state.messages[0]]
        st.rerun()


# В конце файла:
if app_mode == "💬 Чат":
    render_chat()
elif app_mode == "📊 Логи":
    render_dashboard()
elif app_mode == "📈 Телеметрия":
    render_telemetry()
elif app_mode == "📥 Входящие":
    render_inbox()