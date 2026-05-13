import os
import re
import logging
import requests
import asyncio
import numpy as np
from typing import List, Set, Optional, Dict, Any
from transitions import Machine, EventData
from dotenv import load_dotenv
import chromadb
from chromadb.utils import embedding_functions
from pathlib import Path

from router import SemanticRouter
from cache import SemanticCache
from ewa import EWAFilter
from telemetry import track_usage
from memory.loader import MemoryLoader
from hitl.diff_gen import PatchGenerator

# Настройка логирования
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

class PCARBrain:
    """
    Оркестратор PCAR на базе конечного автомата (FSM).
    Управляет жизненным циклом и маршрутизацией запроса пользователя.
    """

    OPENROUTER_URL: str = "https://openrouter.ai/api/v1/chat/completions"
    
    STATES: List[str] = [
        'IDLE',             # Ожидание запроса
        'ROUTING',          # Анализ интента
        'CACHE_CHECK',      # Проверка кэша
        'RETRIEVING',       # Поиск в БД (ChromaDB / SQLite)
        'CONTEXT_ASSEMBLY', # Сборка и сжатие фактов
        'SYNTHESIZING'      # Генерация ответа через LLM
    ]

    _SIMPLE_INTENTS: Set[str] = {"привет", "как дела", "кто ты", "спасибо"}

    # Декларативное описание переходов
    TRANSITIONS: List[Dict[str, str]] = [
        {'trigger': 'process_query', 'source': 'IDLE', 'dest': 'ROUTING', 'after': '_do_route'},
        {'trigger': 'route_to_cache', 'source': 'ROUTING', 'dest': 'CACHE_CHECK', 'after': '_do_cache_check'},
        {'trigger': 'route_to_llm', 'source': 'ROUTING', 'dest': 'SYNTHESIZING', 'after': '_do_synthesize'},
        {'trigger': 'cache_hit', 'source': 'CACHE_CHECK', 'dest': 'SYNTHESIZING', 'after': '_do_synthesize'},
        {'trigger': 'cache_miss', 'source': 'CACHE_CHECK', 'dest': 'RETRIEVING', 'after': '_do_retrieve'},
        {'trigger': 'retrieve_done', 'source': 'RETRIEVING', 'dest': 'CONTEXT_ASSEMBLY', 'after': '_do_assemble'},
        {'trigger': 'assembly_done', 'source': 'CONTEXT_ASSEMBLY', 'dest': 'SYNTHESIZING', 'after': '_do_synthesize'},
        {'trigger': 'reset', 'source': '*', 'dest': 'IDLE', 'before': '_clear_state'},
    ]

    def __init__(self, api_key: Optional[str] = None) -> None:
        load_dotenv()
        self._api_key: str = api_key or os.getenv("OPENROUTER_API_KEY", "").strip()
        
        if not self._api_key:
            raise ValueError("❌ Не найден OPENROUTER_API_KEY в переменных окружения!")
            
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {self._api_key}"})

        print("Подключение к хранилищу памяти...")
        base_dir = Path(__file__).resolve().parent.parent
        db_path = base_dir / "data" / "vector_db"
        
        # Подключаем ChromaDB
        self.db_client = chromadb.PersistentClient(path=str(db_path))
        self.emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        self.collection = self.db_client.get_collection(name="pcar_gold", embedding_function=self.emb_fn)

        # Подключаем наши модули (Роутер и Кэш)
        self.semantic_router = SemanticRouter(emb_fn=self.emb_fn)
        self.cache = SemanticCache()
        self.ewa = EWAFilter(top_k=7)
        self.patch_gen = PatchGenerator()

        # Настройка FSM
        self.machine = Machine(
            model=self,
            states=self.STATES,
            transitions=self.TRANSITIONS,
            initial='IDLE',
            send_event=True
        )
        
        # Переменные состояния
        self.current_query: str = ""
        self.current_query_emb: Optional[np.ndarray] = None
        self.raw_retrieval_results: Dict = {}
        self.current_context: str = ""
        self.last_answer: str = ""
        self.last_answer = ""
        
        # --- МЕТРИКИ ---
        self.current_intent = "unknown"
        self.is_cache_hit = False

    def _clear_state(self, event: EventData) -> None:
        self.current_query = ""
        self.current_query_emb = None
        self.current_context = ""

    def _do_route(self, event: EventData) -> None:
        raw_query = event.kwargs.get('query')
        self.current_query = str(raw_query).strip() if raw_query else ""
        
        if not self.current_query:
            self.reset()
            return
            
        intent = self.semantic_router.route(self.current_query)
        self.current_intent = intent
        print(f"[ORCHESTRATOR] Интент: {intent.upper()}")
        
        if intent == "chat":
            self.route_to_llm()
        else:
            self.route_to_cache()

    def _do_cache_check(self, event: EventData) -> None:
        """Проверка семантического кэша."""
        # 1. Превращаем запрос в вектор
        query_emb = np.array(self.emb_fn([self.current_query])[0])
        self.current_query_emb = query_emb # Сохраняем вектор в память агента
        
        # 2. Ищем похожий вектор в базе SQLite
        cached_response = self.cache.get(query_emb)
        
        if cached_response:
            print("[CACHE] ⚡ Найден точный ответ! Отдаю из локальной памяти.")
            self.is_cache_hit = True
            self.last_answer = cached_response
            self.cache_hit() # Прыгаем сразу на выдачу ответа
        else:
            print("[CACHE] 🔍 В кэше пусто. Идем искать знания в базе.")
            self.is_cache_hit = False
            self.cache_miss() # Прыгаем на поиск в ChromaDB

    def _do_retrieve(self, event: EventData) -> None:
        """Поиск сырых данных в ChromaDB."""
        results = self.collection.query(
            query_texts=[self.current_query],
            n_results=20,
            include=["documents", "metadatas", "distances"] 
        )
        self.raw_retrieval_results = results
        self.retrieve_done()

    def _do_assemble(self, event: EventData) -> None:
        """Сборка и сжатие фактов через модуль EWA."""
        # Пропускаем 20 кусков через наш фильтр и получаем чистый текст
        self.current_context = self.ewa.process(self.raw_retrieval_results)
        self.assembly_done() # Переходим в SYNTHESIZING

    @track_usage("llm_generation")
    def _do_synthesize(self, event: EventData) -> None:
        """Генерация ответа или выдача из кэша."""
        
        if event.transition.source == 'CACHE_CHECK':
            print(f"\n🧠 АГЕНТ (из кэша): {self.last_answer}\n")
            self.reset()
            return

        # --- МАГИЯ ПАМЯТИ: Вызываем MemoryLoader ---
        memory_loader = MemoryLoader()
        system_msg = memory_loader.build_system_prompt(self.current_context)
            
        payload: Dict[str, Any] = {
            "model": "deepseek/deepseek-v4-flash",
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": self.current_query}
            ]
        }
        
        try:
            response = self._session.post(self.OPENROUTER_URL, json=payload, timeout=15)
            response.raise_for_status()
            
            response_data = response.json()
            answer = response_data.get('choices', [{}])[0].get('message', {}).get('content', 'Ответ не получен.')
            self.last_answer = answer
            
            # --- HITL: ПРОВЕРКА НА НАЛИЧИЕ ПАТЧЕЙ (НОВОЕ) ---
            patches = []
            clean_answer = answer
            if "<<<<<<< SEARCH" in answer and ">>>>>>> REPLACE" in answer:
                # Ищем все блоки патчей через регулярное выражение
                patch_pattern = re.compile(r"(FILE:.*?<<<<<<< SEARCH.*?=======.*?>>>>>>> REPLACE)", re.DOTALL)
                patches = patch_pattern.findall(answer)
                
                for patch in patches:
                    self.patch_gen.save_to_inbox(patch)
                
                # Удаляем патч-блоки из текста, чтобы получить clean_answer
                clean_answer = re.sub(r"FILE:.*?<<<<<<< SEARCH.*?=======.*?>>>>>>> REPLACE", "", answer, flags=re.DOTALL).strip()
                
                print(f"\n📥 [HITL] Входящие: Агент создал {len(patches)} предложение(й) правок! Проверьте папку data/inbox/")
            
            # СОХРАНЕНИЕ В КЭШ: Запоминаем сгенерированный ответ на будущее
            if self.current_query_emb is not None:
                # В кэш сохраняем только clean_answer (без патч-блоков)
                self.cache.set(self.current_query, self.current_query_emb, clean_answer)
            
            # Формируем финальный ответ с уведомлением о патчах
            if patches:
                self.last_answer = clean_answer + f"\n\n---\n📥 *Подготовлено предложений: {len(patches)}. Проверь вкладку «Входящие знания»!*"
            else:
                self.last_answer = clean_answer
                
            print(f"\n🧠 АГЕНТ: {self.last_answer}\n")
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Ошибка сети или API: {e}")
            print("\n❌ Произошла ошибка при обращении к серверу нейросети.\n")
        except ValueError:
            logging.error("API вернул невалидный JSON.")
            print("\n❌ Ошибка обработки ответа от сервера.\n")
        finally:
            self.reset()
    
    async def get_llm_response(self, prompt: str) -> str:
        """
        Прямой вызов LLM в обход кэша, RAG и роутера.
        Используется исключительно для внутренних (фоновых) задач агента.
        """
        def _request():
            payload = {
                "model": "deepseek/deepseek-v4-flash",
                "messages": [{"role": "user", "content": prompt}]
            }
            # Увеличенный таймаут для больших генераций
            res = self._session.post(self.OPENROUTER_URL, json=payload, timeout=120)
            res.raise_for_status()
            return res.json().get('choices', [{}])[0].get('message', {}).get('content', '')
            
        return await asyncio.to_thread(_request)

if __name__ == "__main__":
    try:
        bot = PCARBrain()
        print("🤖 PCAR Brain (v2.0 MVP) активирован.")
        print("Введи свой вопрос (или 'exit' для выхода).\n")
        
        while True:
            user_input = input("Ты: ").strip()
            if user_input.lower() in {'exit', 'quit', 'выход'}:
                print("Отключение мозга...")
                break
            if user_input:
                bot.process_query(query=user_input)
                
    except Exception as e:
        logging.critical(f"Критическая ошибка запуска: {e}")