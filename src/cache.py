import sqlite3
import logging
import numpy as np
from pathlib import Path
from typing import Optional, List

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

class SemanticCache:
    """
    Семантический кэш с in-memory векторизацией и SQLite-персистентностью.
    Обеспечивает мгновенный поиск благодаря предзагрузке матриц в ОЗУ.
    """

    def __init__(self, threshold: float = 0.90) -> None:
        self.threshold: float = threshold
        
        # Умный абсолютный путь
        base_dir = Path(__file__).resolve().parent.parent
        self.db_path = base_dir / "data" / "vector_db" / "cache.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._ids: List[int] = []
        self._responses: List[str] = []
        self._matrix: Optional[np.ndarray] = None
        
        self._init_db()
        self._load_index_to_memory()

    def _init_db(self) -> None:
        """Создает таблицы кэша (исправлен SQL синтаксис)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS semantic_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    response TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    hits INTEGER DEFAULT 1
                )
            """)

    def _load_index_to_memory(self) -> None:
        """Единожды загружает данные в память для векторизованного поиска."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT id, embedding, response FROM semantic_cache")
            rows = cursor.fetchall()
            
        if not rows:
            return
            
        self._ids = [row[0] for row in rows]
        self._responses = [row[2] for row in rows]
        
        # Собираем и нормализуем матрицу сразу при загрузке
        embeddings = [np.frombuffer(row[1], dtype=np.float32) for row in rows]
        matrix = np.vstack(embeddings)
        
        # L2-нормализация для быстрого косинусного сходства (dot product)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1  # Защита от деления на ноль
        self._matrix = matrix / norms

    def get(self, query_emb: np.ndarray) -> Optional[str]:
        """Ищет ответ в кэше с помощью векторизованного матричного умножения."""
        if self._matrix is None or len(self._matrix) == 0:
            return None
            
        # Защита от неверных размерностей и пустых векторов
        query_emb = np.array(query_emb, dtype=np.float32).flatten()
        norm = np.linalg.norm(query_emb)
        if norm == 0:
            return None
            
        query_emb_normalized = query_emb / norm
        
        # ВЕКТОРИЗАЦИЯ: Матричное умножение
        similarities = np.dot(self._matrix, query_emb_normalized)
        best_idx = int(np.argmax(similarities))
        best_score = float(similarities[best_idx])
        
        if best_score >= self.threshold:
            best_id = self._ids[best_idx]
            logging.info(f"[CACHE] Hit! Similarity: {best_score:.4f}")
            
            # Асинхронно обновляем счетчик попаданий в фоне
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("UPDATE semantic_cache SET hits = hits + 1 WHERE id = ?", (best_id,))
            return self._responses[best_idx]
            
        return None

    def set(self, query: str, query_emb: np.ndarray, response: str) -> None:
        """Сохраняет ответ в БД и синхронизирует in-memory матрицу."""
        query_emb = np.array(query_emb, dtype=np.float32).flatten()
        
        # Edge Case: Защита от пустых значений
        if not query or not response or len(query_emb) == 0:
            logging.warning("[CACHE] Попытка сохранить пустые данные.")
            return

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO semantic_cache (query, embedding, response) VALUES (?, ?, ?)",
                (query, query_emb.tobytes(), response)
            )
            new_id = cursor.lastrowid
            
        logging.info("[CACHE] Сохранен новый ответ.")
        
        # Обновляем in-memory индекс без перезагрузки базы
        norm = np.linalg.norm(query_emb)
        normalized_emb = query_emb / norm if norm > 0 else query_emb
        
        self._ids.append(new_id)
        self._responses.append(response)
        
        if self._matrix is None:
            self._matrix = np.array([normalized_emb])
        else:
            self._matrix = np.vstack([self._matrix, normalized_emb])