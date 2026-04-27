import json
import html
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd


def parse_my_activity(file_path: Path) -> pd.DataFrame:
    """
    Извлекает и очищает логи диалогов из MyActivity.json, используя 
    векторизованные операции Pandas для максимальной производительности.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data: List[Dict[str, Any]] = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"⚠️ Ошибка чтения {file_path}: {e}")
        return pd.DataFrame()

    if not data:
        return pd.DataFrame()

    # Собираем "сырые" данные в список для однократной передачи в DataFrame
    records = []
    for i, item in enumerate(data):

        if not isinstance(item, dict):
            continue

        session_id = f"dialog_{i}"
        timestamp = item.get('time')
        
        # Данные пользователя
        title = item.get('title', '')
        if title:
            records.append({
                'session_id': session_id,
                'timestamp': timestamp,
                'role': 'user',
                'content': title
            })
            
        # Данные модели
        safe_html_list = item.get('safeHtmlItem', [])
        if isinstance(safe_html_list, list) and safe_html_list:
            model_text = safe_html_list[0].get('html', '')
            if model_text:
                records.append({
                    'session_id': session_id,
                    'timestamp': timestamp,
                    'role': 'model',
                    'content': model_text
                })

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    
    # Инициализация пустых списков для тегов
    df['topic_tags'] = [[] for _ in range(len(df))]

    # Векторизованная обработка времени (O(1) на уровне Python)
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')

    # Создаем маски для фильтрации ролей
    is_user = df['role'] == 'user'
    is_model = df['role'] == 'model'

    # Векторизованная очистка реплик пользователя
    if is_user.any():
        df.loc[is_user, 'content'] = (
            df.loc[is_user, 'content']
            .str.replace(r'^Отправлен запрос\s+', '', regex=True)
            .str.strip()
        )

    # Векторизованная очистка реплик модели + сдвиг времени
    if is_model.any():
        df.loc[is_model, 'timestamp'] += pd.Timedelta(seconds=1)
        
        # Очистка HTML через векторизованные строковые методы C-бэкенда pandas
        model_content = df.loc[is_model, 'content'].str.replace(r'<[^>]+>', ' ', regex=True)
        model_content = model_content.map(html.unescape)
        model_content = model_content.str.replace(r'\s+', ' ', regex=True).str.strip()
        
        df.loc[is_model, 'content'] = model_content

    # Фильтрация пустых строк и сброс индексов
    df = df[df['content'].astype(bool).fillna(False)].reset_index(drop=True)
    
    return df


def main() -> None:
    """Основной пайплайн обработки конкретного файла логов."""
    BASE_DIR = Path(__file__).resolve().parent.parent
    raw_path = BASE_DIR / "data" / "raw"
    processed_path = BASE_DIR / "data" / "processed"
    processed_path.mkdir(parents=True, exist_ok=True)

    print(f"🔍 Ищем целевой файл в папке: {raw_path}")

    # СНАЙПЕРСКИЙ ПОИСК: ищем строго файл МоиДействия.json
    # rglob по-прежнему поможет, если файл зарыт в Takeout/My Activity/Gemini/
    target_filename = "МоиДействия.json"
    json_files = list(raw_path.rglob(target_filename))
    
    if not json_files:
        print(f"❌ Файл {target_filename} не найден в data/raw. Проверь имя и путь!")
        return

    all_dfs = []
    for file in json_files:
        print(f"📦 Нашел и обрабатываю: {file.name}")
        # Тут наша функция parse_my_activity с защитой от ошибок
        df = parse_my_activity(file)
        if not df.empty:
            all_dfs.append(df)

    if not all_dfs:
        print("❌ Не удалось извлечь данные из найденного файла.")
        return

    # Собираем данные в финальную таблицу
    final_df = pd.concat(all_dfs, ignore_index=True)
    
    # Удаляем дубликаты (на случай, если файл попался дважды)
    final_df = final_df.drop_duplicates(subset=['timestamp', 'content'])
    
    output_file = processed_path / "cleaned_logs.parquet"
    final_df.to_parquet(output_file, index=False)
    
    print(f"✅ Успех! Извлечено чистых реплик: {len(final_df)}")
    print(f"💾 Файл сохранен: {output_file}")

if __name__ == "__main__":
    main()