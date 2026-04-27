import logging
import heapq
from typing import Dict, Any, List

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

class EWAFilter:
    """
    Экспоненциальное взвешивание контекста (EWA) и прунинг (Pruning).
    Отвечает за оценку, фильтрацию и сжатие выдачи векторной базы 
    для формирования максимально релевантного контекста для LLM.
    """
    
    # Константа класса: веса не должны пересоздаваться при каждом инстанцировании
    SOURCE_WEIGHTS: Dict[str, float] = {
        "02_projects.md": 1.5,
        "03_tech_stack.md": 1.3,
        "01_profile.md": 1.0,
        "05_strategy.md": 1.0,
        "04_health.md": 0.3
    }

    def __init__(self, top_k: int = 12) -> None:
        self.top_k: int = top_k

    def process(self, raw_results: Dict[str, Any]) -> str:
        """
        Ранжирует сырые факты из БД и возвращает топ-K релевантных кусков.
        Использует приоритетную очередь (heap) для алгоритмической оптимизации.
        """
        # Edge Cases: безопасное извлечение с защитой от IndexError
        try:
            documents: List[str] = raw_results.get('documents', [[]])[0]
            metadatas: List[Dict[str, str]] = raw_results.get('metadatas', [[]])[0]
            distances: List[float] = raw_results.get('distances', [[]])[0]
        except IndexError:
            logging.error("[EWA] Некорректная структура ответа базы (пустые массивы).")
            return ""

        if not documents:
            return ""
            
        # Защита от рассинхронизации данных (ChromaDB иногда может сбоить)
        if not (len(documents) == len(metadatas) == len(distances)):
            logging.error("[EWA] Рассинхронизация списков в ответе ChromaDB.")
            return ""

        def _compute_score(idx: int) -> float:
            """O(1) вычисление итогового веса для конкретного элемента."""
            base_similarity = 1.0 / (1.0 + distances[idx])
            source = metadatas[idx].get("source", "unknown")
            source_multiplier = self.SOURCE_WEIGHTS.get(source, 1.0)
            return base_similarity * source_multiplier

        # ОПТИМИЗАЦИЯ: O(N log K) поиск лучших индексов без полного цикла сортировки
        top_indices = heapq.nlargest(
            min(self.top_k, len(documents)), 
            range(len(documents)), 
            key=_compute_score
        )
        
        # Склеиваем только победителей, игнорируя случайно попавшие пустые строки
        best_chunks = [
            str(documents[i]).strip() 
            for i in top_indices 
            if str(documents[i]).strip()
        ]
        
        logging.info(f"[EWA] Контекст сжат: из {len(documents)} кусков оставлено {len(best_chunks)}.")
        
        return "\n\n".join(best_chunks)