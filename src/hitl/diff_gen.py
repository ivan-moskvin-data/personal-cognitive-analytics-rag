import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


class PatchGenerator:
    """
    Генератор патчей знаний (формат SEARCH/REPLACE).
    Формирует предложения по обновлению файлов и безопасно сохраняет их в Inbox 
    для последующего подтверждения человеком (Human-in-the-Loop).
    """

    def __init__(self, inbox_dir: Optional[Union[Path, str]] = None) -> None:
        """
        Инициализация генератора. Поддерживает Dependency Injection (DI)
        для переопределения папки Inbox (полезно для Unit-тестов).
        """
        if inbox_dir:
            self.inbox_dir: Path = Path(inbox_dir)
        else:
            self.inbox_dir = Path(__file__).resolve().parent.parent.parent / "data" / "inbox"
            
        # Папка создается единожды при старте компонента, а не при каждом сохранении файла
        try:
            self.inbox_dir.mkdir(parents=True, exist_ok=True)
        except IOError as e:
            logging.critical(f"[HITL] Не удалось создать папку Inbox: {e}")

    def create_patch_block(self, file_path: str, search_text: str, replace_text: str) -> str:
        """Формирует текстовый блок патча (O(1) конкатенация строк)."""
        clean_file = str(file_path).strip() if file_path else "UNKNOWN_FILE"
        clean_search = str(search_text).strip() if search_text else ""
        clean_replace = str(replace_text).strip() if replace_text else ""

        # Используем неявную конкатенацию литералов, что читается чище, чем многострочный f-string
        return (
            f"FILE: {clean_file}\n"
            f"<<<<<<< SEARCH\n{clean_search}\n"
            f"=======\n{clean_replace}\n"
            f">>>>>>> REPLACE\n"
        )

    def save_to_inbox(self, patch_content: str, task_name: str = "update") -> Optional[Path]:
        """Безопасно сохраняет сформированный патч на жесткий диск."""
        
        # Edge Case: Защита от создания пустых или мусорных файлов
        if not patch_content or not str(patch_content).strip():
            logging.warning("[HITL] Попытка сохранить пустой патч. Игнорирую.")
            return None

        # Санитаризация имени: удаляем спецсимволы, чтобы не сломать файловую систему ОС (Path Traversal)
        safe_task_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', str(task_name))[:50]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        file_path = self.inbox_dir / f"patch_{timestamp}_{safe_task_name}.md"
        
        try:
            file_path.write_text(patch_content, encoding="utf-8")
            logging.info(f"[HITL] Создано предложение правки: {file_path.name}")
            return file_path
        except IOError as e:
            logging.error(f"[HITL] Ошибка записи файла на диск: {e}")
            return None