async def parse_key_value_args(context, allowed_keys: set | None = None) -> tuple[dict, str | None]:
    """
    Парсит аргументы вида key=value из команды.
    Возвращает: (dict_аргументов, ошибка_или_None)

    allowed_keys — если указано, проверяет, что ключи из этого набора (опционально)
    """
    args = {}
    current_key = None

    for arg in context.args:
        if '=' in arg:
            key, val = arg.split('=', 1)
            key_clean = key.lower().strip()
            if allowed_keys and key_clean not in allowed_keys:
                return {}, f"❌ Неизвестный параметр `{key_clean}`"
            args[key_clean] = val.strip()
            current_key = key_clean
        elif current_key is not None:
            args[current_key] += ' ' + arg
        else:
            return {}, f"❌ Неверный формат: `{arg}`. Ожидается `ключ=значение`"

    # Чистка значений
    for k in args:
        args[k] = args[k].strip().strip("\"'").strip()

    return args, None