import logging
import json
import asyncio
from typing import Optional, Any
from nicegui import ui

# Импорты предполагают наличие строгих типов из предыдущих шагов
from memory.srs_db import SRSDatabase, CardData
from memory.evaluator import SRSEvaluator

logger = logging.getLogger(__name__)

class AnkiTrainerUI:
    """
    Изолированный класс UI для тренировки и генерации карточек.
    Предотвращает гонку состояний (Race Conditions) между сессиями.
    """
    
    def __init__(self, db: SRSDatabase, evaluator: SRSEvaluator) -> None:
        self.db = db
        self.evaluator = evaluator  # LLM клиент получаем через DI, а не через глобальный импорт
        self.current_card: Optional[CardData] = None
        self.is_evaluating: bool = False

    def render(self) -> None:
        """Главный интерфейс с вкладками (Тренировка / Генератор)."""
        with ui.element('div').classes('w-full h-full flex flex-col bg-[#0e0e10] p-0 m-0 overflow-hidden relative items-center'):
            
            with ui.tabs().classes('w-full max-w-2xl mt-8 bg-[#171719] rounded-xl text-gray-400') as tabs:
                tab_review = ui.tab('Тренировка').classes('font-medium')
                tab_generate = ui.tab('Добавить материал').classes('font-medium')

            with ui.tab_panels(tabs, value=tab_review).classes('w-full flex-1 bg-transparent p-0 m-0'):
                
                with ui.tab_panel(tab_review).classes('w-full h-full flex flex-col items-center justify-center p-4'):
                    self.render_review_panel()

                with ui.tab_panel(tab_generate).classes('w-full h-full flex flex-col items-center p-4 overflow-y-auto custom-scrollbar'):
                    self.render_generator_panel()

    @ui.refreshable
    def render_review_panel(self) -> None:
        """Отрисовывает интерфейс тренировки памяти (Active Recall)."""
        due_cards = self.db.get_due_cards()

        if not due_cards:
            self._render_success_screen()
            return

        self.current_card = due_cards[0]
        self._render_card_screen(len(due_cards))

    def delete_current_card(self) -> None:
        """Удаляет текущую карточку и переходит к следующей."""
        if self.current_card:
            self.db.delete_card(self.current_card["id"])
            ui.notify("Карточка удалена навсегда", type="warning", icon="delete")
            self.current_card = None
            self.render_review_panel.refresh()

    def _render_success_screen(self) -> None:
        with ui.column().classes('items-center gap-4 mt-32'):
            ui.icon('task_alt', size='64px').classes('text-green-500 mb-4')
            ui.label('На сегодня всё!').classes('text-3xl font-medium text-gray-200')
            ui.label('Твой цифровой мозг синхронизирован.').classes('text-gray-500')

    def _render_card_screen(self, cards_left: int) -> None:
        if not self.current_card:
            return

        with ui.element('div').classes('w-full max-w-2xl bg-[#1e1f20] rounded-[24px] p-8 shadow-2xl border border-white/5 flex flex-col gap-6 relative mt-8'):
            # Блок с счетчиком и кнопкой удаления в правом верхнем углу
            with ui.row().classes('absolute top-4 right-6 items-center gap-4'):
                ui.label(f'Осталось карточек: {cards_left}').classes('text-[12px] text-gray-500 font-semibold tracking-widest uppercase')
                ui.button(icon='delete', on_click=self.delete_current_card) \
                    .props('flat round size=sm') \
                    .classes('text-gray-500 hover:text-red-400 transition-colors')
            
            ui.label('ВОПРОС').classes('text-[12px] text-indigo-400 font-bold tracking-widest uppercase mt-4')
            ui.markdown(self.current_card["question"]).classes('text-xl text-gray-200 leading-relaxed')

            ui.label('ТВОЙ ОТВЕТ').classes('text-[12px] text-gray-500 font-bold tracking-widest uppercase mt-4')
            
            answer_input = ui.textarea(placeholder='Сформулируй ответ своими словами...') \
                .props('dark outlined autogrow') \
                .classes('w-full text-gray-200 bg-[#171719] rounded-xl')
            
            feedback_container = ui.column().classes('w-full gap-4 hidden')
            
            with feedback_container:
                ui.separator().classes('bg-white/5 my-2')
                score_label = ui.label('').classes('text-lg font-bold')
                feedback_text = ui.label('').classes('text-gray-300')
                truth_text = ui.markdown('').classes('text-sm text-gray-500 p-4 bg-[#171719] rounded-xl border border-white/5')
                
                ui.button('Следующая карточка', on_click=self.render_review_panel.refresh) \
                    .classes('w-full py-3 mt-4 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-medium transition-colors')

            submit_btn = ui.button('Проверить') \
                .classes('w-full py-3 mt-2 bg-[#2b2c2f] hover:bg-[#3f4045] text-gray-200 rounded-xl font-medium transition-colors')
            
            submit_btn.on('click', lambda: self.submit_answer(
                answer_input, feedback_container, score_label,
                feedback_text, truth_text, submit_btn
            ))

    async def submit_answer(
        self, 
        answer_input: ui.textarea, 
        feedback_container: ui.column, 
        score_label: ui.label, 
        feedback_text: ui.label, 
        truth_text: ui.markdown, 
        submit_btn: ui.button
    ) -> None:
        user_text = str(answer_input.value).strip()
        if not user_text or self.is_evaluating or not self.current_card: 
            return

        self.is_evaluating = True
        submit_btn.props(remove='color')
        submit_btn.text = 'Проверка...'
        submit_btn.classes(replace='w-full py-3 mt-2 bg-[#171719] text-gray-500 rounded-xl font-medium cursor-not-allowed')
        answer_input.props('disable')

        try:
            result = await self.evaluator.evaluate_answer(
                question=self.current_card["question"],
                ground_truth=self.current_card["ground_truth"],
                user_answer=user_text
            )
            self.db.update_card_after_review(self.current_card["id"], result["score"])

            colors = {5: 'text-green-400', 4: 'text-green-400', 3: 'text-yellow-400', 2: 'text-orange-400', 1: 'text-red-400', 0: 'text-red-500'}
            score_label.text = f'Оценка ИИ: {result["score"]}/5'
            score_label.classes(replace=f'text-lg font-bold {colors.get(result["score"], "text-white")}')
            
            feedback_text.text = result["feedback"]
            truth_text.set_content(f"**Эталонный ответ:**\n{self.current_card['ground_truth']}")

            submit_btn.classes(add='hidden')
            feedback_container.classes(remove='hidden')

        except Exception as e:
            logger.error("Ошибка при проверке ответа", extra={"error": str(e)})
            ui.notify("Сбой нейросети или БД. Попробуй еще раз.", type="negative")
            submit_btn.text = 'Проверить'
            submit_btn.classes(replace='w-full py-3 mt-2 bg-[#2b2c2f] hover:bg-[#3f4045] text-gray-200 rounded-xl font-medium transition-colors')
            answer_input.props(remove='disable')
            
        finally:
            self.is_evaluating = False

    def render_generator_panel(self) -> None:
        with ui.element('div').classes('w-full max-w-2xl bg-[#1e1f20] rounded-[24px] p-8 shadow-2xl border border-white/5 flex flex-col gap-4 mt-8'):
            ui.label('Генератор знаний').classes('text-2xl font-medium text-white mb-2')
            ui.label('Вставь сюда тему или конспект, который ты выучил.').classes('text-sm text-gray-400 mb-4')
            
            material_input = ui.textarea(placeholder='Например: Темы из SQL (JOIN, Window Functions)...') \
                .props('dark outlined autogrow') \
                .classes('w-full text-gray-200 bg-[#171719] rounded-xl')
            
            loading_spinner = ui.row().classes('w-full justify-center hidden my-4 items-center gap-3')
            with loading_spinner:
                ui.spinner(size='md', color='indigo-400')
                ui.label('Анализирую тему...').classes('text-indigo-400 font-medium')

            gen_btn = ui.button('Создать задания') \
                .classes('w-full py-3 mt-4 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-medium transition-colors')

            gen_btn.on('click', lambda: self.start_generation(material_input, gen_btn, loading_spinner))

    def _extract_json_array(self, text: str) -> str:
        """Изолирует JSON-массив из сырого текста (Zero-Trust)."""
        start = text.find('[')
        end = text.rfind(']')
        if start != -1 and end != -1 and start < end:
            return text[start:end+1]
        raise ValueError("JSON-массив не найден в ответе LLM")

    async def start_generation(
        self, 
        material_input: ui.textarea, 
        gen_btn: ui.button, 
        loading_spinner: ui.row
    ) -> None:
        """Безопасная генерация карточек с валидацией схемы."""
        text = str(material_input.value).strip()
        if not text: 
            return
        
        gen_btn.classes(add='hidden')
        loading_spinner.classes(remove='hidden')
        
        try:
            prompt = (
                "Ты — эксперт по методике обучения SuperMemo. Твоя задача — провести глубокую декомпозицию учебного материала.\n"
                "Создай МАКСИМАЛЬНО возможное количество атомарных карточек.\n\n"
                "ПРАВИЛА:\n"
                "1. ПРИНЦИП АТОМАРНОСТИ: Одна карточка — один узкий факт. Не смешивай несколько нюансов.\n"
                "2. ПОЛНЫЙ ОХВАТ: Не пропускай детали синтаксиса, пограничные случаи и исключения.\n"
                "3. ФОРМАТ: Если в тексте есть список, создай отдельную карточку на КАЖДЫЙ пункт.\n"
                "4. КОД: Если в материале есть примеры кода, создай вопросы по конкретным строчкам.\n"
                "5. СТИЛЬ: Вопросы должны быть короткими и четкими.\n\n"
                'ВЫХОДНЫЕ ДАННЫЕ: Выведи ТОЛЬКО JSON-массив: [{"q": "вопрос", "a": "ответ"}]\n\n'
                f"МАТЕРИАЛ:\n{text}"
            )
            
            raw_response = await self.evaluator.bot.get_llm_response(prompt)
            
            # 1. Защита парсинга
            json_str = self._extract_json_array(raw_response)
            parsed_data: Any = json.loads(json_str)
            
            # 2. Строгая валидация схемы перед записью в БД
            if not isinstance(parsed_data, list):
                raise ValueError("Ожидался список карточек")
                
            added = 0
            for item in parsed_data:
                # Type Guard: пропускаем мусор, если LLM ошиблась в структуре одного элемента
                if isinstance(item, dict) and isinstance(item.get("q"), str) and isinstance(item.get("a"), str):
                    self.db.add_card(question=item["q"].strip(), ground_truth=item["a"].strip())
                    added += 1
            
            if added == 0:
                raise ValueError("LLM не сгенерировала валидных вопросов")

            ui.notify(f'Добавлено {added} новых карточек!', type='positive')
            material_input.value = ''
            self.render_review_panel.refresh() 
            
        except json.JSONDecodeError as e:
            logger.error("Ошибка парсинга JSON генератора", extra={"error": str(e), "raw": raw_response})
            ui.notify("Ошибка формата ответа от нейросети.", type='negative')
        except Exception as e:
            logger.exception("Ошибка при генерации карточек", extra={"error": str(e)})
            ui.notify("Не удалось создать карточки. Системная ошибка.", type='negative')
        finally:
            loading_spinner.classes(add='hidden')
            gen_btn.classes(remove='hidden')

# Вызов из layout.py должен передавать глобальный bot через параметры функции
def mount_training_page(bot_client) -> None:
    db = SRSDatabase()
    evaluator = SRSEvaluator(bot_client)
    trainer = AnkiTrainerUI(db, evaluator)
    trainer.render()