"""Утилиты для работы с промптами: извлечение, перевод, валидация."""
import re
import logging
from telegram import Update
from telegram.ext import ContextTypes

from utils.translate import translate_prompt_free
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, DEFAULT_MODEL

logger = logging.getLogger(__name__)

CYRILLIC_RE = re.compile(r'[а-яА-ЯёЁ]')
MIN_VALID_TAG_RATIO = 0.8
# ПРАВКА 1: Добавили \- и \(\) чтобы пропускать теги вроде "one-shoulder" или "(solo)"
TAGS_PATTERN = re.compile(r'^[a-zA-Z0-9_\s,\-\(\)]+$')
TAG_BODY_RE = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_ .()\-]*$')
SPECIAL_TAG_RE = re.compile(r'^<(?:lora|lyco|embedding|embed):[^<>]+>$', re.I)
# Разговорные слова => это не тег, а просьба

CONVERSATIONAL_RE = re.compile(
    r'\b(please|draw|generate|create|make me|can you|could you| depicting|of a )\b',
    re.I
)


def extract_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str | None:
    """
    Извлекает текст промпта из команды /gen или обычного сообщения.
    Возвращает строку или None (если промпт пуст).
    """
    if context.args:
        return " ".join(context.args)

    text = update.message.text
    return text.replace("/gen", "", 1).strip() or None


def _split_loose_tags(text: str) -> list[str]:
    """
    Дробит промпт на теги, мирясь с пунктуацией пользователя.
    'Footwork. Smiling' -> ['Footwork', 'Smiling']
    '<lora:...v1.0...:0.8>' -> остаётся одним целым тегом.
    """
    tags = []
    for fragment in re.split(r'[,;\n]', text):
        fragment = fragment.strip()
        if not fragment:
            continue

        if fragment.startswith('<'):
            tags.append(fragment)          # LoRA/Embedding не трогаем
            continue

        # Точка + пробел внутри фрагмента — скорее всего, конец тега
        for sub in re.split(r'\.\s+', fragment):
            sub = re.sub(r'[.!?;:]+\s*$', '', sub).strip()
            if sub:
                tags.append(sub)
    return tags


def _is_valid_tag(tag: str) -> bool:
    if SPECIAL_TAG_RE.fullmatch(tag):
        return True

    if CYRILLIC_RE.search(tag):
        return False

    # Danbooru-тег — это короткая визуальная метка, не предложение
    words = tag.split()
    if len(words) > 4 or len(tag) > 60:
        return False

    if CONVERSATIONAL_RE.search(tag):
        return False

    return bool(TAG_BODY_RE.fullmatch(tag))


def is_likely_tags(text: str) -> bool:
    """Готовые теги, даже если пользователь поставил точку или один мусорный тег."""
    tags = _split_loose_tags(text)
    if not tags:
        return False

    valid_count = sum(1 for tag in tags if _is_valid_tag(tag))
    ratio = valid_count / len(tags)

    logger.debug(f"Tag ratio: {ratio:.2f} ({valid_count}/{len(tags)})")
    return ratio >= MIN_VALID_TAG_RATIO

def normalize_prompt(text: str) -> str:
    """Собираем теги обратно в чистый вид: без 'Footwork.' и хвостовых точек."""
    return ", ".join(_split_loose_tags(text))


async def get_llm_tags(raw_prompt: str) -> str | None:
    """
    Запрашивает теги у LLM.
    Возвращает строку тегов или None, если LLM вернула мусор/ошибку.
    """
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL,
            max_retries=0
        )

        # ПРАВКА 2: Оптимизированный, сухой системный промпт.
        # Убрали "магические" фразы про safety, они тратят токены и не работают.
        system_prompt = """ROLE: You are a stateless text-to-tag converter (Danbooru dictionary).
        TASK: Convert user request into concise visual tags in English, comma-separated.

        CRITICAL RULES:
        1. OUTPUT FORMAT: ONLY tags separated by commas. No sentences, no explanations, no markdown.
        2. SUBJECT: Start with a count tag (1girl, 1boy, etc.) ONLY if a HUMAN person/character is EXPLICITLY mentioned. 
           - Animals, creatures, robots, vehicles, objects, nature -> NO human tags, even if anthropomorphic (e.g., lizard in spacesuit = lizard, NOT 1boy).
           - If no person is mentioned -> add "no humans" to prevent accidental character generation.
        3. VISUAL ONLY: Describe ONLY what is explicitly requested. Use visual consequences, not abstract concepts (e.g., use 'broken furniture, debris' instead of 'destroying, chaos').
        4. TAG STRUCTURE: Split compound ideas into 1-2 word tags. 
        5. NO QUALITY TAGS: NEVER generate quality tags (masterpiece, best quality) — the system adds them.
        6. FORBIDDEN: young, little, childish, loli, shota, underage. Never output these.

        EXAMPLES:
        Input: "девушка в красном платье танцует под дождём"
        Output: 1girl, red dress, dancing, rain, wet, outdoors, dynamic pose
        Input: "Рокси Мигурдия, соло, плоская грудь, маленькое тело, синие волосы, две косы"
        Output: roxy migurdia, solo, flat chest, petite body, blue hair, twin braids
        Input: "Самолёт пролетающий над городом"
        Output: airplane, flying, cityscape, sky, clouds, no humans
        Input: "ящерица в космосе в скафандре"
        Output: lizard, spacesuit, space, stars, no humans, creature focus"""

        # ПРАВКА 3: Отключаем reasoning для экономии токенов и времени
        response = await client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw_prompt}
            ],
            temperature=0.2,  # Понизили до 0.2 для максимальной детерминированности тегов
            timeout=30,       # 60 секунд для тегов - это слишком много, 30 хватит за глаза
            extra_body={      # Безопасный способ передать специфичные параметры провайдеру
                "reasoning": {
                    "effort": "none"
                }
            }
        )

        result = response.choices[0].message.content.strip()

        # Валидация: ловим только классические отказы LLM
        forbidden = ["sorry", "i cannot", "i am unable", "давайте поговорим", "извините", "я не могу"]
        if any(phrase in result.lower() for phrase in forbidden):
            logger.warning(f"LLM вернула запрещенную фразу: {result}")
            return None

        return result

    except Exception as e:
        logger.error(f"Ошибка при запросе к LLM: {e}")
        return None


async def prepare_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, raw_prompt: str) -> str | None:
    """
    Основная логика обработки промпта с Graceful Degradation (Планом Б).
    Возвращает готовый английский промпт или None (с уведомлением пользователя).
    """
    raw_prompt = raw_prompt.strip()
    if not raw_prompt:
        return None

    # ШАГ 1: Это уже готовые теги? (Самый быстрый путь)
    if is_likely_tags(raw_prompt):
        logger.info("Распознаны готовые теги, пропускаем LLM.")
        return normalize_prompt(raw_prompt)  # важно: не raw_prompt с точкой в конце

    # ШАГ 2: Пытаемся получить теги через LLM
    llm_result = await get_llm_tags(raw_prompt)
    if llm_result:
        logger.info(f"Успешно получили теги от LLM: {llm_result}")
        return llm_result

    # ШАГ 3: План Б. LLM не справился или упал. Используем старый переводчик.
    logger.warning("LLM не справился, используем fallback-переводчик.")
    if CYRILLIC_RE.search(raw_prompt):
        translated = await translate_prompt_free(raw_prompt)

        # Проверяем, справился ли переводчик
        if not CYRILLIC_RE.search(translated):
            return translated
        else:
            await update.message.reply_text(
                "❌ Не удалось обработать промпт. Пожалуйста, используй английские теги через запятую.\n"
                "💡 Пример: `1girl, blue_hair, smiling`",
                parse_mode="Markdown"
            )
            return None
    else:
        logger.info("Английский текст без запятых, отправляем как есть.")
        return raw_prompt