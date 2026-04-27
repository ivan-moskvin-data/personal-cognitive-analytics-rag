import logging
from pathlib import Path
from typing import Iterator, Tuple, Dict, List
import chromadb
from chromadb.utils import embedding_functions

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def _generate_chunks(gold_dir: Path) -> Iterator[Tuple[str, Dict[str, str], str]]:
    """
    Ленивый генератор для чтения файлов и разбивки на чанки.
    Отдает данные поштучно, не загружая все файлы в ОЗУ одновременно.
    """
    doc_id = 0
    # O(1) проверка наличия файлов без конвертации в список
    file_generator = gold_dir.glob("*.md")
    
    for filepath in file_generator:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                # Разбиваем на параграфы, отсекая мусорные/короткие строки
                for chunk in f.read().split("\n\n"):
                    clean_chunk = chunk.strip()
                    if len(clean_chunk) > 10:
                        yield clean_chunk, {"source": filepath.name}, f"gold_{doc_id}"
                        doc_id += 1
        except IOError as e:
            logging.error(f"[ОШИБКА I/O] Не удалось прочитать файл {filepath.name}: {e}")


def build_index(batch_size: int = 100) -> None:
    """
    Создает или перезаписывает векторную базу ChromaDB на основе Markdown-файлов.
    Использует батчевую загрузку и ленивую генерацию для экономии памяти.
    """
    base_dir: Path = Path(__file__).resolve().parent.parent
    gold_dir: Path = base_dir / "data" / "memory" / "gold"
    db_path: Path = base_dir / "data" / "vector_db"

    if not gold_dir.exists() or not any(gold_dir.iterdir()):
        logging.error(f"❌ Директория {gold_dir} не найдена или пуста!")
        return

    logging.info("Инициализация ChromaDB...")
    try:
        client = chromadb.PersistentClient(path=str(db_path))
        embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        
        # Безопасное удаление старой коллекции (Chroma кидает ValueError, если её нет)
        try:
            client.delete_collection("pcar_gold")
        except Exception:
            pass
            
        collection = client.create_collection(
            name="pcar_gold", 
            embedding_function=embedding_function
        )
    except Exception as e:
        logging.critical(f"❌ Ошибка подключения или настройки ChromaDB: {e}")
        return

    # Буферы для батчевой вставки
    docs_batch: List[str] = []
    meta_batch: List[Dict[str, str]] = []
    ids_batch: List[str] = []
    
    total_indexed = 0

    logging.info("Начинаю чтение и индексацию файлов...")

    # Потребляем генератор, держа в ОЗУ только один batch_size
    for chunk, meta, chunk_id in _generate_chunks(gold_dir):
        docs_batch.append(chunk)
        meta_batch.append(meta)
        ids_batch.append(chunk_id)

        if len(docs_batch) == batch_size:
            collection.add(documents=docs_batch, metadatas=meta_batch, ids=ids_batch)
            total_indexed += len(docs_batch)
            docs_batch.clear()
            meta_batch.clear()
            ids_batch.clear()

    # Записываем остатки (хвост), если они есть
    if docs_batch:
        collection.add(documents=docs_batch, metadatas=meta_batch, ids=ids_batch)
        total_indexed += len(docs_batch)

    logging.info(f"✅ Индексация завершена! Загружено {total_indexed} кусков знаний.")

if __name__ == "__main__":
    build_index()