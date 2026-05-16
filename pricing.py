
"""
Конфигурация пакетов генераций.
Все изменения цен и пакетов — только здесь.
"""

from typing import Dict

PACKAGES: Dict[str, dict] = {
    "starter": {
        "stars": 2,
        "credits": 1,
        "label": "🎨 1 генерация",
        "desc": "Попробовать бота",
        "price_rub": 5  # 5.0 ₽ за картинку
    },
    "standard": {
        "stars": 18,
        "credits": 10,
        "label": "✨ 10 генераций",
        "desc": "Выгода 10% (4.5 ₽/карт.)",
        "price_rub": 45
    },
    "pro": {
        "stars": 85,
        "credits": 50,
        "label": "🔥 50 генераций",
        "desc": "Выгода 24% (3.8 ₽/карт.)",  # 🔥 Исправлено с 15% → 24%
        "price_rub": 190
    },
    "mega": {
        "stars": 400,
        "credits": 250,
        "label": "🚀 250 генераций",
        "desc": "Выгода 36% (3.2 ₽/карт.)",  # 🔥 Исправлено с 20% → 36%
        "price_rub": 800
    }
}

# Вспомогательная функция для быстрого доступа по ключу
def get_package(key: str) -> dict | None:
    return PACKAGES.get(key)

# Получаем все ключи для кнопок/валидации
PACKAGE_KEYS = list(PACKAGES.keys())