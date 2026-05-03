from datetime import datetime, timedelta, timezone

MIN_EASE_FACTOR: float = 1.3
MIN_QUALITY: int = 0
MAX_QUALITY: int = 5

def calculate_sm2(
    quality: int, 
    repetitions: int, 
    previous_interval: int, 
    previous_ease_factor: float,
    current_time: datetime | None = None
) -> tuple[int, float, int, datetime]:
    """
    Рассчитывает новые параметры для карточки по алгоритму SM-2.
    
    :param quality: Оценка ответа (0-5), где 0 - полный бред, 5 - идеальный ответ.
    :param repetitions: Количество успешных повторений подряд (>= 0).
    :param previous_interval: Предыдущий интервал в днях (>= 0).
    :param previous_ease_factor: Предыдущий коэффициент легкости (>= 1.3).
    :param current_time: Контекст текущего времени (для тестов и UTC).
    :return: Кортеж (new_interval, new_ease_factor, new_repetitions, next_review_date).
    :raises ValueError: Если входные данные выходят за границы алгоритма.
    """
    # 1. Strict input validation
    if not (MIN_QUALITY <= quality <= MAX_QUALITY):
        raise ValueError(f"Параметр quality должен быть в диапазоне {MIN_QUALITY}-{MAX_QUALITY}")
    if repetitions < 0:
        raise ValueError("Параметр repetitions не может быть отрицательным")
    if previous_interval < 0:
        raise ValueError("Параметр previous_interval не может быть отрицательным")
    if previous_ease_factor < MIN_EASE_FACTOR:
        raise ValueError(f"Параметр previous_ease_factor не может быть ниже {MIN_EASE_FACTOR}")

    # 2. Timezone-aware date handling
    if current_time is None:
        current_time = datetime.now(timezone.utc)

    # 3. SM-2 Logic calculation
    if quality >= 3:
        if repetitions == 0:
            interval = 1
        elif repetitions == 1:
            interval = 6
        else:
            interval = round(previous_interval * previous_ease_factor)
        
        repetitions += 1
        ease_factor = previous_ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    else:
        repetitions = 0
        interval = 1
        ease_factor = previous_ease_factor

    ease_factor = max(MIN_EASE_FACTOR, ease_factor)
    next_review_date = current_time + timedelta(days=interval)
    
    return interval, round(ease_factor, 2), repetitions, next_review_date