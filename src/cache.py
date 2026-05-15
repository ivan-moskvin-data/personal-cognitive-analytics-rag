import sqlite3
import logging
from typing import Optional

class SemanticCache:  # Оставляем старое название, чтобы не сломать orchestrator.py
    def __init__(self, db_path: str = "data/vector_db/telemetry.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Создает таблицу для точного кэша, если ее нет."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS exact_cache (
                    query TEXT PRIMARY KEY,
                    response TEXT
                )
            """)

    def check_cache(self, query: str) -> Optional[str]:
        """Ищет 100% точное совпадение текста запроса."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Ищем точное совпадение строки
                cursor.execute("SELECT response FROM exact_cache WHERE query = ?", (query,))
                result = cursor.fetchone()
                
                if result:
                    logging.info("⚡ Точное совпадение в кэше!")
                    return result[0]
            return None
        except Exception as e:
            logging.error(f"Ошибка чтения кэша: {e}")
            return None

    def add_to_cache(self, query: str, response: str, cache_hit: bool = False):
        """Сохраняет текст запроса и ответ."""
        if cache_hit:
            return  # Не сохраняем, если ответ уже взят из кэша
            
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO exact_cache (query, response) 
                    VALUES (?, ?)
                """, (query, response))
        except Exception as e:
            logging.error(f"Ошибка записи в кэш: {e}")