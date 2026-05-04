import json
import logging
from typing import Protocol, TypedDict

# Настраиваем логгер для модуля. На уровне приложения он должен быть сконфигурирован для вывода в JSON.
logger = logging.getLogger(__name__)

class EvaluationResult(TypedDict):
    """Строгая типизация результата оценки."""
    score: int
    feedback: str

class LLMClient(Protocol):
    """
    Протокол (Duck Typing) для инъекции зависимости. 
    Гарантирует, что переданный бот имеет нужный асинхронный метод.
    """
    async def get_llm_response(self, prompt: str) -> str:
        ...

class SRSEvaluator:
    def __init__(self, bot_client: LLMClient) -> None:
        """
        :param bot_client: Клиент для работы с LLM, реализующий протокол LLMClient.
        """
        self.bot = bot_client

    def _extract_json_from_text(self, text: str) -> str:
        """
        Изолирует JSON-объект из сырого текста. 
        Защита от "галлюцинаций" LLM, когда она добавляет мусор до или после JSON.
        """
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and start < end:
            return text[start:end+1]
        return text

    async def evaluate_answer(self, question: str, ground_truth: str, user_answer: str) -> EvaluationResult:
        """
        Оценивает ответ пользователя с помощью LLM (Zero-Trust подход к парсингу).
        """
        prompt = (
            "Ты — строгий, но справедливый экзаменатор. Твоя задача — оценить ответ ученика на вопрос.\n"
            "Оценивай только СМЫСЛ. Игнорируй опечатки, регистр и стиль речи.\n\n"
            f"ВОПРОС: {question}\n"
            f"ЭТАЛОННЫЙ ОТВЕТ: {ground_truth}\n"
            f"ОТВЕТ УЧЕНИКА: {user_answer}\n\n"
            "Критерии оценки (score):\n"
            "5 - Идеально. Смысл передан полностью и точно.\n"
            "4 - Хорошо. Мелкие неточности или забыта некритичная деталь.\n"
            "3 - Удовлетворительно. Понял суть, но объяснил коряво или упустил важную часть.\n"
            "2 - Слабо. Уловлен только отдаленный смысл, много ошибок.\n"
            "1 - Неверно. Ответ не соответствует эталону.\n"
            "0 - Полный бред, ответ \"не знаю\" или пустой.\n\n"
            "Напиши короткий комментарий (feedback) на 1-2 предложения.\n"
            "Ответь СТРОГО в формате JSON без markdown-разметки:\n"
            '{"score": <оценка 0-5>, "feedback": "<твой комментарий>"}'
        )

        response_text = ""
        try:
            response_text = await self.bot.get_llm_response(prompt)
            json_str = self._extract_json_from_text(response_text)
            
            result = json.loads(json_str)
            
            # Строгая санитизация и приведение типов (Zero-Trust к LLM)
            raw_score = result.get("score", 0)
            score = max(0, min(5, int(raw_score)))
            feedback = str(result.get("feedback", "Оценка принята."))
            
            return {"score": score, "feedback": feedback}
            
        except json.JSONDecodeError as e:
            # Логируем контекст падения: что именно сломало парсер
            logger.error(
                "LLM JSON parsing failed", 
                extra={"error": str(e), "raw_response": response_text}
            )
            return {"score": 0, "feedback": "Ошибка парсинга ответа нейросети."}
        except (ValueError, TypeError) as e:
            logger.error(
                "LLM Invalid data types in JSON", 
                extra={"error": str(e), "raw_response": response_text}
            )
            return {"score": 0, "feedback": "Некорректный формат данных от нейросети."}
        except Exception as e:
            # Ловим сетевые таймауты или падения самого бота
            logger.exception(
                "System error during LLM evaluation", 
                extra={"error": str(e)}
            )
            return {"score": 0, "feedback": "Внутренняя системная ошибка при оценке."}