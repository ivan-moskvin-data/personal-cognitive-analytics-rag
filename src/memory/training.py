import logging
from typing import Optional
from nicegui import ui

# Импорты предполагают наличие строгих типов из предыдущих шагов
from memory.srs_db import SRSDatabase, CardData
from memory.evaluator import SRSEvaluator
from .state import app_state

logger = logging.getLogger(__name__)

class AnkiTrainerUI:
    """Изолированный класс UI для предотвращения гонки состояний (Race Conditions)."""
    
    def __init__(self, db: SRSDatabase, evaluator: SRSEvaluator) -> None:
        self.db = db
        self.evaluator = evaluator
        self.current_card: Optional[CardData] = None
        self.is_evaluating: bool = False

    @ui.refreshable
    def render(self) -> None:
        """Отрисовывает интерфейс тренировки памяти."""
        due_cards = self.db.get_due_cards()

        with ui.element('div').classes('w-full h-full flex flex-col bg-[#0e0e10] p-0 m-0 overflow-hidden relative items-center justify-center'):
            if not due_cards:
                self._render_success_screen()
                return

            self.current_card = due_cards[0]
            self._render_card_screen(len(due_cards))

    def _render_success_screen(self) -> None:
        """Экран пустого инбокса."""
        with ui.column().classes('items-center gap-4'):
            ui.icon('task_alt', size='64px').classes('text-green-500 mb-4')
            ui.label('На сегодня всё!').classes('text-3xl font-medium text-gray-200')
            ui.label('Твой цифровой мозг синхронизирован.').classes('text-gray-500')

    def _render_card_screen(self, cards_left: int) -> None:
        """Экран активной карточки."""
        if not self.current_card:
            return

        with ui.element('div').classes('w-full max-w-2xl bg-[#1e1f20] rounded-[24px] p-8 shadow-2xl border border-white/5 flex flex-col gap-6 relative'):
            ui.label(f'Осталось карточек: {cards_left}').classes('absolute top-4 right-6 text-[12px] text-gray-500 font-semibold tracking-widest uppercase')
            
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
                
                # Встроенный метод .refresh() от декоратора @ui.refreshable
                ui.button('Следующая карточка', on_click=self.render.refresh) \
                    .classes('w-full py-3 mt-4 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-medium transition-colors')

            submit_btn = ui.button('Проверить') \
                .classes('w-full py-3 mt-2 bg-[#2b2c2f] hover:bg-[#3f4045] text-gray-200 rounded-xl font-medium transition-colors')
            
            # Связываем обработчик без глубокой вложенности lambda
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
        """Асинхронно обрабатывает ответ и управляет состояниями UI."""
        user_text = str(answer_input.value).strip()
        if not user_text or self.is_evaluating or not self.current_card: 
            return

        self.is_evaluating = True
        
        # 1. UI: Блокировка ввода (Защита от двойного сабмита)
        submit_btn.props(remove='color')
        submit_btn.text = 'Проверка...'
        submit_btn.classes(replace='w-full py-3 mt-2 bg-[#171719] text-gray-500 rounded-xl font-medium cursor-not-allowed')
        answer_input.props('disable')

        try:
            # 2. Бизнес-логика
            result = await self.evaluator.evaluate_answer(
                question=self.current_card["question"],
                ground_truth=self.current_card["ground_truth"],
                user_answer=user_text
            )
            self.db.update_card_after_review(self.current_card["id"], result["score"])

            # 3. UI: Отрисовка результатов
            colors = {5: 'text-green-400', 4: 'text-green-400', 3: 'text-yellow-400', 2: 'text-orange-400', 1: 'text-red-400', 0: 'text-red-500'}
            score_label.text = f'Оценка ИИ: {result["score"]}/5'
            score_label.classes(replace=f'text-lg font-bold {colors.get(result["score"], "text-white")}')
            
            feedback_text.text = result["feedback"]
            truth_text.set_content(f"**Эталонный ответ:**\n{self.current_card['ground_truth']}")

            submit_btn.classes(add='hidden')
            feedback_container.classes(remove='hidden')

        except Exception as e:
            # 4. Graceful Degradation: Откат UI при сбое LLM
            logger.error("Ошибка при проверке ответа", extra={"error": str(e)})
            ui.notify("Сбой нейросети или БД. Попробуй еще раз.", type="negative")
            
            submit_btn.text = 'Проверить'
            submit_btn.classes(replace='w-full py-3 mt-2 bg-[#2b2c2f] hover:bg-[#3f4045] text-gray-200 rounded-xl font-medium transition-colors')
            answer_input.props(remove='disable')
            
        finally:
            # 5. Гарантированный сброс блокировки
            self.is_evaluating = False

# Точка входа для роутера
def mount_training_page() -> None:
    db = SRSDatabase()
    evaluator = SRSEvaluator(app_state.bot)
    trainer = AnkiTrainerUI(db, evaluator)
    trainer.render()