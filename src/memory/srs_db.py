import sqlite3
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import TypedDict

from .sm2 import calculate_sm2

# Переходим на SQLite для обеспечения ACID и низкого потребления RAM
SRS_DB_FILE = Path("data/memory/srs_cards.sqlite")

class CardData(TypedDict):
    id: str
    question: str
    ground_truth: str
    interval: int
    ease_factor: float
    repetitions: int
    next_review_date: str
    created_at: str

class SRSDatabase:
    def __init__(self, db_path: Path = SRS_DB_FILE) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Создает структуру базы данных, если она отсутствует, и настраивает I/O."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            # WAL-режим критичен для маломощных SSD/SD-карт: снижает количество операций записи
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cards (
                    id TEXT PRIMARY KEY,
                    question TEXT NOT NULL,
                    ground_truth TEXT NOT NULL,
                    interval INTEGER NOT NULL,
                    ease_factor REAL NOT NULL,
                    repetitions INTEGER NOT NULL,
                    next_review_date TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            # Индекс для O(log N) поиска просроченных карточек
            conn.execute("CREATE INDEX IF NOT EXISTS idx_due_date ON cards(next_review_date);")

    def add_card(self, question: str, ground_truth: str) -> CardData:
        """Добавляет новую карточку в базу."""
        if not question.strip() or not ground_truth.strip():
            raise ValueError("Поля question и ground_truth не могут быть пустыми.")

        now_iso = datetime.now(timezone.utc).isoformat()
        card: CardData = {
            "id": str(uuid.uuid4()),
            "question": question,
            "ground_truth": ground_truth,
            "interval": 0,
            "ease_factor": 2.5,
            "repetitions": 0,
            "next_review_date": now_iso,
            "created_at": now_iso
        }

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO cards (id, question, ground_truth, interval, ease_factor, repetitions, next_review_date, created_at)
                VALUES (:id, :question, :ground_truth, :interval, :ease_factor, :repetitions, :next_review_date, :created_at)
            """, card)
        return card

    def get_due_cards(self) -> list[CardData]:
        """Возвращает карточки, которые нужно повторить сегодня (O(K))."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            # Использование индекса idx_due_date
            cursor = conn.execute("SELECT * FROM cards WHERE next_review_date <= ?", (now_iso,))
            return [dict(row) for row in cursor.fetchall()] # type: ignore

    def update_card_after_review(self, card_id: str, quality: int) -> CardData | None:
        """Обновляет параметры карточки после ответа с атомарной транзакцией."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT interval, ease_factor, repetitions FROM cards WHERE id = ?", (card_id,))
            row = cursor.fetchone()

            if not row:
                return None

            new_interval, new_ef, new_reps, next_date = calculate_sm2(
                quality=quality,
                repetitions=row["repetitions"],
                previous_interval=row["interval"],
                previous_ease_factor=row["ease_factor"]
            )

            update_data = {
                "id": card_id,
                "interval": new_interval,
                "ease_factor": new_ef,
                "repetitions": new_reps,
                "next_review_date": next_date.isoformat()
            }

            conn.execute("""
                UPDATE cards 
                SET interval = :interval, 
                    ease_factor = :ease_factor, 
                    repetitions = :repetitions, 
                    next_review_date = :next_review_date
                WHERE id = :id
            """, update_data)

            # Возвращаем обновленный стейт
            cursor = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,))
            return dict(cursor.fetchone()) # type: ignore
    
    def get_stats(self) -> dict:
        """Возвращает базовую статистику по карточкам для дашборда."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 1. Всего карточек
            cursor.execute("SELECT COUNT(*) FROM cards")
            total_cards = cursor.fetchone()[0] or 0
            
            # 2. Карточек в долгосрочной памяти (интервал >= 21 дня)
            cursor.execute("SELECT COUNT(*) FROM cards WHERE interval >= 21")
            long_term = cursor.fetchone()[0] or 0
            
            # 3. Средний Ease Factor
            cursor.execute("SELECT AVG(ease_factor) FROM cards")
            avg_ef = cursor.fetchone()[0] or 2.5
            
            return {
                "total": total_cards,
                "long_term": long_term,
                "avg_ease": round(avg_ef, 2)
            }
    
    def delete_card(self, card_id: int) -> None:
        """Удаляет карточку из базы данных по её ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cards WHERE id = ?", (card_id,))
            conn.commit()