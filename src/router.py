import logging
import numpy as np
from typing import Dict, List, Optional
from chromadb.utils import embedding_functions

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

class SemanticRouter:
    """
    Векторный маршрутизатор запросов (Semantic Router).
    Определяет намерение пользователя с помощью матричного умножения
    и предварительно рассчитанных центроидов (center of mass).
    """

    # Шаблоны перенесены в константы класса (не нужно пересоздавать при каждом инстансе)
    INTENT_TEMPLATES: Dict[str, List[str]] = {
        "chat": [
            "привет", "как дела", "кто ты", "спасибо", "пока", "доброе утро",
            "расскажи анекдот", "что делаешь"
        ],
        "factoid": [
            "какой вес", "когда был дефицит", "сколько миллиметров грыжа", 
            "какую базу данных использовал", "какая версия", "где учился",
            "сколько задач решил", 
            "что я сейчас учу", "напомни мне", "какие у меня навыки", "что я говорил про"
        ],
        "conceptual": [
            "объясни архитектуру", "в чем стратегия развития", 
            "как работает парсер", "расскажи подробнее про проект",
            "почему выбрал этот инструмент"
        ]
    }

    CONFIDENCE_THRESHOLD: float = 0.3

    def __init__(self, emb_fn: Optional[any] = None) -> None:
        logging.info("Инициализация нейро-роутера и предрасчет матриц...")
        self.emb_fn = emb_fn or embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        
        self.intent_labels: List[str] = []
        centroids: List[np.ndarray] = []

        # Предрасчет и нормализация центроидов для будущей векторизации
        for intent, examples in self.INTENT_TEMPLATES.items():
            embeddings = np.array(self.emb_fn(examples))
            # Вычисляем центр масс кластера (средний вектор)
            centroid = np.mean(embeddings, axis=0)
            
            # Предварительная L2-нормализация вектора
            norm = np.linalg.norm(centroid)
            if norm > 0:
                centroid = centroid / norm
                
            self.intent_labels.append(intent)
            centroids.append(centroid)
            
        # Собираем центроиды в единую матрицу формы (K, D)
        self.centroid_matrix: np.ndarray = np.vstack(centroids)

    def route(self, query: Optional[str]) -> str:
        """Определяет интент запроса через векторизованное косинусное сходство."""
        clean_query = str(query).strip() if query else ""
        
        # Edge case: пустой запрос или None
        if not clean_query:
            logging.warning("[ROUTER] Получен пустой запрос. Возврат 'chat'.")
            return "chat"

        # Получаем вектор запроса
        query_emb = np.array(self.emb_fn([clean_query])[0])
        norm = np.linalg.norm(query_emb)
        
        # Edge case: нулевой вектор (крайне редко, но вызывает DivisionByZero)
        if norm == 0:
            return "chat"
            
        # Нормализуем вектор запроса
        query_emb_normalized = query_emb / norm

        # ВЕКТОРИЗАЦИЯ: Умножение матрицы на вектор вместо цикла
        # Дает массив косинусных сходств для всех интентов одновременно
        similarities = np.dot(self.centroid_matrix, query_emb_normalized)

        # O(1) поиск максимального значения в массиве
        best_idx = np.argmax(similarities)
        best_score = similarities[best_idx]
        best_intent = self.intent_labels[best_idx]

        logging.info(f"\n[ROUTER] Анализируем: '{clean_query}'")
        for label, score in zip(self.intent_labels, similarities):
            logging.info(f"  -> Сходство с [{label}]: {score:.3f}")

        # Fallback при низкой уверенности
        if best_score < self.CONFIDENCE_THRESHOLD:
            logging.info(f"Уверенность {best_score:.3f} ниже порога. Fallback на 'conceptual'.")
            return "conceptual"

        return best_intent


if __name__ == "__main__":
    router = SemanticRouter()
    
    test_queries = [
        "Привет, железка!",
        "Какая база данных используется в ASSE?",
        "Объясни, как работает твоя архитектура?",
        "",    # Edge case (пустая строка)
        None   # Edge case (None)
    ]
    
    for q in test_queries:
        result = router.route(q)
        logging.info(f"✅ РЕШЕНИЕ: Интент '{result}'\n")