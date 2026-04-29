"""Менеджер состояния приложения PCAR (Singleton)."""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from hitl.auto_sync import AutoSync
import uuid


HISTORY_DIR = Path(__file__).resolve().parent.parent / "data" / "history"
METADATA_FILE = HISTORY_DIR / "metadata.json"

# Убедимся, что директория для истории существует
HISTORY_DIR.mkdir(parents=True, exist_ok=True)


class AppState:
    """Менеджер состояния приложения (Singleton)."""

    _instance: Optional["AppState"] = None

    def __new__(cls) -> "AppState":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        self.bot = None
        self.current_chat_id: Optional[str] = None
        self.messages: List[Dict[str, str]] = []
        self.chats_meta: Dict[str, Dict[str, Any]] = {}
        self.pinned_chat_ids: List[str] = []
        self.folders: Dict[str, List[str]] = {}

        self._load_metadata()
        self._init_bot()
        self._init_chat_state()

    def _init_bot(self) -> None:
        """Инициализирует бота PCARBrain."""
        if self.bot is None:
            sys.path.append(str(Path(__file__).resolve().parent.parent))
            from orchestrator import PCARBrain
            self.bot = PCARBrain()

    def _load_metadata(self) -> None:
        """Загружает метаданные чатов из JSON файла."""
        if METADATA_FILE.exists():
            try:
                with open(METADATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.chats_meta = data.get("chats_meta", {})
                    self.pinned_chat_ids = data.get("pinned_chat_ids", [])
                    self.folders = data.get("folders", {})
            except Exception:
                pass

    def _save_metadata(self) -> None:
        """Сохраняет метаданные чатов в JSON файл."""
        metadata = {
            "chats_meta": self.chats_meta,
            "pinned_chat_ids": self.pinned_chat_ids,
            "folders": self.folders
        }
        with open(METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    def _init_chat_state(self) -> None:
        """Инициализирует состояние чата при старте."""
        if not self.chats_meta:
            self.current_chat_id = str(uuid.uuid4())
            self.chats_meta[self.current_chat_id] = {"title": "Новый чат", "folderId": None}
            self._save_metadata()
        else:
            last_chat_id = list(self.chats_meta.keys())[-1]
            self.current_chat_id = last_chat_id

        self.messages = self._load_chat_from_disk(self.current_chat_id)
        if not self.messages:
            self.messages = [
                {"role": "assistant", "content": "Привет! Я твой цифровой мозг. Все наши разговоры теперь сохраняются, даже если ты обновишь страницу!"}
            ]

    def _load_chat_from_disk(self, chat_id: str) -> List[Dict[str, str]]:
        """Загружает историю чата из файла."""
        chat_file = HISTORY_DIR / f"{chat_id}.json"
        if chat_file.exists():
            try:
                with open(chat_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_chat_to_disk(self, chat_id: Optional[str] = None) -> None:
        """Сохраняет текущую сессию чата в файл."""
        if chat_id is None:
            chat_id = self.current_chat_id
        if chat_id:
            chat_file = HISTORY_DIR / f"{chat_id}.json"
            with open(chat_file, "w", encoding="utf-8") as f:
                json.dump(self.messages, f, ensure_ascii=False, indent=2)

    def create_new_chat(self) -> None:
        """Создает новый чат и переключается на него."""
        chat_id = str(uuid.uuid4())
        self.current_chat_id = chat_id
        self.messages = [
            {"role": "assistant", "content": "Привет! Я твой цифровой мозг. Все наши разговоры теперь сохраняются, даже если ты обновишь страницу!"}
        ]
        self.chats_meta[chat_id] = {"title": "Новый чат", "folderId": None}
        self._save_metadata()
        self._save_chat_to_disk(chat_id)

    def switch_chat(self, chat_id: str) -> None:
        """Переключает контекст на выбранный чат."""
        if self.current_chat_id != chat_id:
            self.current_chat_id = chat_id
            self.messages = self._load_chat_from_disk(chat_id)

    def auto_rename_chat(self, prompt: str) -> None:
        """Авто-переименование чата по первым 30 символам первого сообщения."""
        if self.current_chat_id:
            current_title = self.chats_meta.get(self.current_chat_id, {}).get("title", "")
            if current_title == "Новый чат":
                new_title = prompt[:30] + ("..." if len(prompt) > 30 else "")
                self.chats_meta[self.current_chat_id]["title"] = new_title
                self._save_metadata()

    def toggle_pin(self, chat_id: str) -> None:
        """Переключает статус закрепления чата."""
        if chat_id in self.pinned_chat_ids:
            self.pinned_chat_ids.remove(chat_id)
        else:
            self.pinned_chat_ids.append(chat_id)
        self._save_metadata()

    def update_chat_title(self, chat_id: str, new_title: str) -> None:
        """Обновляет название чата."""
        if chat_id in self.chats_meta:
            self.chats_meta[chat_id]["title"] = new_title
            self._save_metadata()

    def apply_patch(self, patch_file: Path) -> None:
        """Помечает патч как одобренный и запускает AutoSync."""
        content = patch_file.read_text(encoding="utf-8")
        patch_file.write_text(f"[x]\n{content}", encoding="utf-8")
        AutoSync().run()

    def delete_patch(self, patch_file: Path) -> None:
        """Удаляет файл патча."""
        patch_file.unlink()


# Глобальный экземпляр для удобства
app_state = AppState()
