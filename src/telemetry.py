import sqlite3
import time
import logging
import atexit
from functools import wraps
from pathlib import Path
from typing import Any, Callable, List, Tuple

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

class TelemetryCollector:
    """
    Сборщик телеметрии с буферизацией в памяти (Write-Behind Cache).
    Минимизирует блокировки основного потока приложения при записи метрик.
    """
    
    def __init__(self, batch_size: int = 10) -> None:
        # Умный абсолютный путь
        base_dir = Path(__file__).resolve().parent.parent
        self.db_path = base_dir / "data" / "vector_db" / "telemetry.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.batch_size: int = batch_size
        self._buffer: List[Tuple[str, int, str, int, str]] = []

        self._init_db()
        atexit.register(self.flush)

    def _init_db(self) -> None:
        """Инициализирует БД и включает высокопроизводительные режимы SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            # WAL (Write-Ahead Logging) снимает локи на чтение/запись
            conn.execute("PRAGMA journal_mode=WAL;")
            # Снижаем уровень синхронизации для огромного буста скорости I/O
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    event_type TEXT NOT NULL,
                    latency_ms INTEGER NOT NULL,
                    intent TEXT,
                    cache_hit INTEGER DEFAULT 0,
                    status TEXT
                )
            """)

    def log_event(self, event_type: str, latency: float, intent: str, cache_hit: bool, status: str = "success") -> None:
        """Добавляет событие в In-Memory буфер (O(1)). Сбрасывает на диск только при заполнении."""
        self._buffer.append((
            event_type, 
            int(latency * 1000), 
            intent, 
            1 if cache_hit else 0, 
            status
        ))

        if len(self._buffer) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        """Батчевая запись накопленных событий в SQLite."""
        if not self._buffer:
            return

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.executemany(
                    "INSERT INTO telemetry (event_type, latency_ms, intent, cache_hit, status) VALUES (?, ?, ?, ?, ?)",
                    self._buffer
                )
            # Закомментируй лог ниже в проде, чтобы не засорять вывод
            logging.debug(f"[TELEMETRY] Успешно сброшено {len(self._buffer)} метрик на диск.")
            self._buffer.clear()
        except sqlite3.Error as e:
            logging.error(f"[TELEMETRY] Ошибка батчевой записи: {e}")


# Глобальный объект для использования в декораторах
collector = TelemetryCollector()


def track_usage(event_name: str) -> Callable:
    """Универсальный декоратор для профилирования и сбора телеметрии."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()
            status = "success"
            
            # Универсальное извлечение контекста: защита от использования декоратора НЕ в классах
            # Если первый аргумент (args[0]) это экземпляр класса (self), пытаемся достать атрибуты
            instance = args[0] if args and hasattr(args[0], '__dict__') else None
            intent = getattr(instance, 'current_query', 'unknown') if instance else 'unknown'
            cache_hit = getattr(instance, 'is_cache_hit', False) if instance else False

            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Ограничиваем длину статуса, чтобы огромные трейсбеки не ломали БД
                status = f"error: {type(e).__name__}"
                raise e
            finally:
                # Блок finally выполняется ВСЕГДА (успех или ошибка), избавляя нас от дублирования кода
                latency = time.perf_counter() - start_time
                collector.log_event(event_name, latency, intent, cache_hit, status=status)
                
        return wrapper
    return decorator