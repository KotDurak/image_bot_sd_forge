
"""
Конфигурация пакетов генераций.
Все изменения цен и пакетов — только здесь.
"""

from typing import Dict

PACKAGES: Dict[str, dict] = {
    "test_1": {
        "stars": 1,
        "credits": 1,
        "label": "🧪 Тестовая генерация (1 ⭐)",
        "desc": "Для отладки платежей"
    },
    "starter": {
        "stars": 2,
        "credits": 1,
        "label": "🎨 1 генерация",
        "desc": "Попробовать бота"
    },
    "standard": {
        "stars": 18,
        "credits": 10,
        "label": "✨ 10 генераций",
        "desc": "Выгода 10%"
    },
    "pro": {
        "stars": 85,
        "credits": 50,
        "label": "🔥 50 генераций",
        "desc": "Выгода 15%"
    },
    "mega": {
        "stars": 400,
        "credits": 250,
        "label": "🚀 250 генераций",
        "desc": "Выгода 20%"
    }
}

# Вспомогательная функция для быстрого доступа по ключу
def get_package(key: str) -> dict | None:
    return PACKAGES.get(key)

# Получаем все ключи для кнопок/валидации
PACKAGE_KEYS = list(PACKAGES.keys())