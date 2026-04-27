import logging
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd
import chromadb
from chromadb.utils import embedding_functions
from tqdm import tqdm

# Настройка логирования для production-ready скриптов
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def init_chroma_collection(db_path: Path, collection_name: str = "pcar_memory") -> chromadb.Collection:
    """Инициализирует локальный клиент ChromaDB и возвращает настроенную коллекцию."""
    client = chromadb.PersistentClient(path=str(db_path))
    emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    return client.get_or_create_collection(
        name=collection_name,
        embedding_function=emb_fn
    )


def populate_vector_db(df: pd.DataFrame, collection: chromadb.Collection, batch_size: int = 5000) -> None:
    """
    Векторизует и загружает данные в ChromaDB порциями.
    Вся предобработка выполняется до цикла с помощью векторизованных методов C-бэкенда.
    """
    # Edge Cases: защита от пустого датасета и отсутствия колонок
    required_cols = {'content', 'role', 'timestamp', 'session_id'}
    if df.empty or not required_cols.issubset(df.columns):
        logging.error("DataFrame пуст или отсутствуют обязательные колонки.")
        return

    # Edge Case ChromaDB: БД падает, если ей передать пустые строки или NaN в documents. Фильтруем.
    df = df[df['content'].astype(str).str.strip().astype(bool)].copy()
    
    if df.empty:
        logging.warning("После удаления пустых строк данных не осталось.")
        return

    # 1. Векторизованная конвертация дат в строки (без циклов)
    df['timestamp'] = df['timestamp'].astype(str)

    # 2. Генерируем метаданные разом через оптимизированный метод Pandas (C-бэкенд)
    metadatas: List[Dict[str, Any]] = df[['role', 'timestamp', 'session_id']].to_dict(orient="records")
    documents: List[str] = df['content'].tolist()
    ids: List[str] = [f"id_{idx}" for idx in df.index]

    total_records = len(df)
    logging.info(f"🚀 Начинаем векторизацию {total_records} записей...")

    # 3. Инсерт батчами: нарезаем уже готовые списки (это быстрее, чем резать DataFrame на каждой итерации)
    for i in tqdm(range(0, total_records, batch_size), desc="Загрузка батчей"):
        collection.add(
            ids=ids[i:i + batch_size],
            documents=documents[i:i + batch_size],
            metadatas=metadatas[i:i + batch_size]
        )


def main() -> None:
    """Главный пайплайн ETL: Parquet -> ChromaDB."""
    base_dir = Path(__file__).resolve().parent.parent
    data_path = base_dir / "data" / "processed" / "cleaned_logs.parquet"
    db_path = base_dir / "data" / "vector_db"

    if not data_path.exists():
        logging.error(f"❌ Файл с данными не найден: {data_path}")
        return

    try:
        df = pd.read_parquet(data_path)
    except Exception as e:
        logging.error(f"❌ Ошибка чтения Parquet: {e}")
        return

    collection = init_chroma_collection(db_path)
    populate_vector_db(df, collection)
    
    logging.info(f"🎉 Успех! Векторная база сохранена по пути: {db_path}")


if __name__ == "__main__":
    main()