import os
import re
import logging
import shutil
from pathlib import Path
from typing import Optional, List

import requests
from dotenv import load_dotenv
from tqdm import tqdm
import time

logging.basicConfig(level=logging.INFO, format="%(message)s")


def call_llm_api(prompt: str, api_key: str, retries: int = 3) -> Optional[str]:
    """Отправляет чанк текста в API с железобетонной защитой от таймаутов."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/ivan-moskvin-data",
        "X-Title": "PCAR Distiller",
        "Connection": "close" 
    }
    
    payload = {
        # Используем быструю Flash-модель
        "model": "x-ai/grok-4.1-fast", 
        "messages": [{"role": "user", "content": prompt}]
    }

    for attempt in range(retries):
        try:
            # БРОНЕЖИЛЕТ: Единый таймаут 300 секунд (5 минут). Никаких кортежей!
            response = requests.post(url, headers=headers, json=payload, timeout=300)
            response.raise_for_status()
            
            choices = response.json().get('choices', [])
            if not choices:
                return None
                
            return choices[0].get('message', {}).get('content', '')

        except requests.exceptions.RequestException as e:
            logging.warning(f"⚠️ Попытка {attempt + 1}/{retries} провалилась: {e}")
            if attempt < retries - 1:
                time.sleep(5) # Пауза перед новым рывком
            else:
                logging.error("❌ Все попытки исчерпаны для этого чанка.")
                
    return None


def parse_and_append_sections(llm_response: str, out_dir: Path) -> int:
    """Парсит ответ и ДОПИСЫВАЕТ (append) данные в Markdown файлы."""
    pattern = re.compile(r'===\s*(.*?)\s*===')
    sections = pattern.split(llm_response)
    
    valid_files = {
        "people": "people.md",
        "projects": "projects.md",
        "health": "health_and_life.md",
        "tech": "tech_stack.md",
        "misc": "misc.md"
    }

    saved_count = 0
    
    for i in range(1, len(sections), 2):
        section_name = sections[i].strip().lower()
        section_text = sections[i + 1].strip()
        
        if not section_text:
            continue
            
        filename = valid_files.get(section_name)
        if not filename:
            safe_name = re.sub(r'[^a-z0-9_]', '', section_name.replace(' ', '_'))
            filename = f"extra_{safe_name}.md"
            
        file_path = out_dir / filename
        
        try:
            # Важно: используем режим "a" (append), чтобы не затереть данные из предыдущих чанков
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(f"\n{section_text}\n")
            saved_count += 1
        except IOError as e:
            logging.error(f"❌ Ошибка записи: {e}")
            
    return saved_count


def chunk_text(text: str, max_chars: int = 100_000) -> List[str]:
    """Разбивает огромный текст на чанки по 100к символов."""
    lines = text.splitlines()
    chunks = []
    current_chunk = []
    current_len = 0

    for line in lines:
        if current_len + len(line) > max_chars:
            chunks.append("\n".join(current_chunk))
            current_chunk = [line]
            current_len = len(line)
        else:
            current_chunk.append(line)
            current_len += len(line)
            
    if current_chunk:
        chunks.append("\n".join(current_chunk))
        
    return chunks


def main() -> None:
    load_dotenv()
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        logging.error("❌ Не найден OPENROUTER_API_KEY!")
        return

    base_dir = Path(__file__).resolve().parent.parent
    text_file = base_dir / "data" / "processed" / "full_logs_text.txt"
    out_dir = base_dir / "data" / "memory"
    
    if not text_file.exists():
        logging.error("❌ Файл с текстом не найден.")
        return

    # Очищаем папку памяти перед новой генерацией, так как мы будем дописывать в файлы
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    logging.info("📄 Читаю текстовый дамп...")
    with open(text_file, "r", encoding="utf-8") as f:
        logs_content = f.read()

    # Бьем текст на куски ~по 500 000 символов
    # Бьем текст на куски ~по 100 000 символов (это безопасно для серверов)
    chunks = chunk_text(logs_content, max_chars=100_000)
    logging.info(f"📏 Текст разбит на {len(chunks)} частей для безопасной обработки.")

    for idx, chunk in enumerate(tqdm(chunks, desc="Обработка частей")):
        prompt = f"""
        Твоя задача — провести глубокую дистилляцию знаний из логов пользователя. 
        Ты должен выжать максимум полезной информации, не упустив ни одного уникального факта.

        ИНСТРУКЦИИ:
        1. Ищи КОНКРЕТИКУ: имена, названия библиотек, цифры весов, даты, специфические термины.
        2. Если информация ВАЖНАЯ, но не подходит под категории PEOPLE, PROJECTS, HEALTH или TECH — обязательно вынеси её в секцию MISC.
        3. Если ты видишь повторяющуюся тему, не указанную в списке (например, Финансы), создай для неё отдельный заголовок (например, ===STUDY===).
        4. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО выдумывать статистику. Пиши только то, что реально есть в тексте.

        ФОРМАТ ОТВЕТА (строго соблюдай маркеры ===НАЗВАНИЕ===):
        ===PEOPLE===
        ===PROJECTS===
        ===HEALTH===
        ===TECH===
        ===MISC===

        ФРАГМЕНТ ЛОГОВ ({idx+1}/{len(chunks)}):
        {chunk}
        """
        
        llm_response = call_llm_api(prompt, api_key)
        
        if not llm_response:
            logging.warning(f"⚠️ Чанк {idx+1} пропущен. Продолжаю со следующего...")
            continue
            
        parse_and_append_sections(llm_response, out_dir)
        
        # Пауза между запросами, чтобы не словить ошибку 429 (Too Many Requests)
        time.sleep(3)
        
    logging.info("🎉 Готово! Дистилляция завершена.")


if __name__ == "__main__":
    main()