from presets import get_preset_list

for name, key in get_preset_list():
    callback_data = f"preset_{key}"
    print(f"Кнопка: {name:20} | callback_data: {callback_data:25} | len: {len(callback_data.encode('utf-8'))} байт")

    # Проверка правил Telegram
    is_ascii = callback_data.isascii()
    in_range = 1 <= len(callback_data) <= 64
    print(f"  ASCII: {is_ascii}, Длина: {in_range} {'✓' if is_ascii and in_range else '❌'}")