import logging
import re
import shutil
import sys
from pathlib import Path
from typing import Optional, Dict

# Настраиваем пути
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR / "scripts"))

try:
    from build_gold_index import build_index
except ImportError:
    build_index = None

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


class AutoSync:
    """
    Служба синхронизации знаний (HITL - Human in the Loop).
    Парсит одобренные патчи из Inbox, применяет их к файлам памяти и 
    запускает реиндексацию векторной базы.
    """
    
    # Компилируем регулярные выражения один раз на уровне класса
    FILE_PATTERN = re.compile(r"FILE:\s*(.+)")
    PATCH_PATTERN = re.compile(
        r"<<<<<<<\s*SEARCH\s*(.*?)\s*=======\s*(.*?)\s*>>>>>>>\s*REPLACE", 
        re.DOTALL
    )

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        """Инициализация с поддержкой Dependency Injection."""
        self.base_dir: Path = base_dir or BASE_DIR
        self.inbox_dir: Path = self.base_dir / "data" / "inbox"
        self.archive_dir: Path = self.base_dir / "data" / "inbox_archive"
        self.memory_dir: Path = self.base_dir / "data" / "memory"
        
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        
        # Кэш для быстрого поиска файлов
        self._file_index: Optional[Dict[str, Path]] = None

    def _get_target_path(self, filename: str) -> Optional[Path]:
        """Ленивая загрузка индекса файлов памяти для быстрого поиска."""
        if self._file_index is None:
            # Единожды сканируем директорию и собираем маппинг {имя_файла: путь}
            self._file_index = {
                p.name: p for p in self.memory_dir.rglob("*.*") if p.is_file()
            }
        return self._file_index.get(filename)

    def run(self) -> None:
        """Основной цикл обработки патчей."""
        if not self.inbox_dir.is_dir():
            logging.info("[SYNC] Папка inbox пуста или не существует.")
            return

        applied_count = 0
        
        # Ленивая итерация по файлам, без выгрузки всех путей в список
        for patch_file in self.inbox_dir.glob("*.md"):
            try:
                content = patch_file.read_text(encoding="utf-8")
                
                # Проверка без выделения памяти под новую огромную строку (ниже объясню)
                if "[x]" not in content and "[X]" not in content:
                    logging.debug(f"[SYNC] Пропуск {patch_file.name} (нет маркера одобрения)")
                    continue
                    
                logging.info(f"[SYNC] ✅ Одобрено: {patch_file.name}. Применяю...")
                
                if self._apply_patch(content):
                    archive_path = self.archive_dir / patch_file.name
                    # shutil.move может упасть, если файл уже есть в архиве, поэтому оборачиваем в try
                    shutil.move(str(patch_file), str(archive_path))
                    applied_count += 1
                else:
                    logging.error(f"[SYNC] ❌ Не удалось применить {patch_file.name}")
                    
            except Exception as e:
                # Изолируем падение одного файла, чтобы скрипт продолжил работу с остальными
                logging.error(f"[SYNC] Ошибка при обработке патча {patch_file.name}: {e}")

        if applied_count > 0:
            logging.info(f"\n🎉 Успешно обновлено файлов: {applied_count}.")
            self._trigger_reindex()
        else:
            logging.info("[SYNC] Нет новых одобренных патчей для применения.")

    def _apply_patch(self, content: str) -> bool:
        """Извлекает SEARCH/REPLACE и изменяет целевой файл."""
        file_match = self.FILE_PATTERN.search(content)
        if not file_match:
            logging.error("Не найден маркер FILE:.")
            return False
            
        target_filename = file_match.group(1).strip()
        
        patch_match = self.PATCH_PATTERN.search(content)
        if not patch_match:
            logging.error("Не найден блок SEARCH/REPLACE.")
            return False
            
        search_text = patch_match.group(1)
        replace_text = patch_match.group(2)
        
        # === МАГИЯ ОЧИСТКИ (Интегрировано безопасно) ===
        # Удаляем галочки [x] и [X], если они случайно захвачены парсером
        replace_text = re.sub(r'(?i)\[x\]', '', replace_text)
        # Убираем trailing spaces (лишние пробелы в конце строк) для чистоты Markdown
        replace_text = "\n".join(line.rstrip() for line in replace_text.splitlines())
        
        # Мгновенный поиск файла по закэшированному индексу
        target_path = self._get_target_path(target_filename)
        
        if not target_path:
            logging.error(f"Файл {target_filename} не найден в базе знаний.")
            return False
            
        try:
            file_content = target_path.read_text(encoding="utf-8")
            
            if search_text and search_text not in file_content:
                logging.warning(f"Текст для замены не найден в {target_filename}. Возможно, конфликт версий.")
                return False
                
            if not search_text.strip():
                # F-string работает быстрее. Используем rstrip() у file_content, 
                # чтобы не плодить бесконечные пустые строки при частых добавлениях.
                new_content = f"{file_content.rstrip()}\n\n{replace_text}"
            else:
                new_content = file_content.replace(search_text, replace_text)
                
            target_path.write_text(new_content, encoding="utf-8")
            return True
            
        except IOError as e:
            logging.error(f"Ошибка чтения/записи файла памяти {target_filename}: {e}")
            return False

    def _trigger_reindex(self) -> None:
        """Автоматически обновляет ChromaDB после изменения файлов."""
        logging.info("🔄 Запускаю переиндексацию векторной базы (ChromaDB)...")
        if build_index:
            try:
                gold_dir = self.memory_dir / "gold"
                build_index(batch_size=10, gold_dir=gold_dir)
                logging.info("🧠 База данных успешно обновлена!")
            except Exception as e:
                logging.error(f"Критическая ошибка при индексации: {e}")
        else:
            logging.warning("⚠️ Не удалось импортировать индексатор. Обновите базу вручную.")


if __name__ == "__main__":
    AutoSync().run()