from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import config
from models.user_quota import grant_unlimited, ban_user, reset_usage
import logging
from models.ads import get_campaign_report, get_all_campaign_impressions
import csv
import io
from db.async_core import async_db

logger = logging.getLogger(__name__)

async def unlimited_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/unlimited <user_id> — выдать/забрать безлимит"""
    if update.effective_user.id not in config.ADMINS:  # твой список админов
        return

    if not context.args:
        await update.message.reply_text("Используй: `/unlimited 8039643413`")
        return

    try:
        target_id = int(context.args[0])
        await grant_unlimited(target_id, grant=True)
        await update.message.reply_text(f"✅ Безлимит выдан user_{target_id}")
    except ValueError:
        await update.message.reply_text("❌ Неверный user_id")


async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ban <user_id> — забанить пользователя"""

    # Проверка прав админа
    if update.effective_user.id not in config.ADMINS:
        await update.effective_message.reply_text("🔒 Только для админов.")
        return

    if not context.args:
        await update.effective_message.reply_text("Используй: `/ban 123456789`")
        return

    try:
        target_id = int(context.args[0])
        # Если второй аргумент не '0', 'false', 'no' — баним, иначе разбаниваем
        ban = len(context.args) < 2 or context.args[1].lower() not in ('0', 'false', 'no')

        # Выполняем бан/разбан
        await ban_user(target_id, ban)
        ban_info = 'забанен' if ban else 'разбанен'

        # 🔥 Безопасный ответ: проверяем, что сообщение существует
        if update.effective_message:
            await update.effective_message.reply_text(f"🔒 user_{target_id} {ban_info}.")
        else:
            # Логируем на случай, если не смогли ответить
            logger.info(f"🔒 user_{target_id} {ban_info} (ответ не отправлен: message=None)")

    except ValueError:
        if update.effective_message:
            await update.effective_message.reply_text("❌ Неверный user_id")
        else:
            logger.error(f"❌ Неверный user_id в /ban от user_{update.effective_user.id}")
    except Exception as e:
        logger.error(f"❌ Ошибка в /ban: {e}", exc_info=True)
        if update.effective_message:
            await update.effective_message.reply_text("❌ Внутренняя ошибка. Проверь логи.")


async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/reset <user_id> — сбросить счётчик (для тестов)"""
    if update.effective_user.id not in config.ADMINS:
        return

    if not context.args:
        await update.message.reply_text("Используй: `/reset 123456789`")
        return

    try:
        target_id = int(context.args[0])
        await reset_usage(target_id)
        await update.message.reply_text(f"🔄 Счётчик сброшен для user_{target_id}")
    except ValueError:
        await update.message.reply_text("❌ Неверный user_id")


async def debug_add_credits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Только для админов: начислить кредиты без оплаты"""
    if update.effective_user.id not in config.ADMINS:
        return

    user_credits = int(context.args[0]) if context.args else 5
    user_id = update.effective_user.id

    from models.user_quota import add_paid_credits
    await add_paid_credits(user_id, user_credits)

    await update.message.reply_text(f"🔧 DEBUG: user_{user_id} начислено {user_credits} кредитов.")


async def ad_report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in config.ADMINS:
        return

    # 🔍 1. Определяем источник апдейта ЯВНО
    if update.callback_query is not None:
        # Нажатие кнопки пагинации
        await update.callback_query.answer()
        try:
            # Формат: ad_page_123_2
            _, _, ad_id_str, page_str = update.callback_query.data.split("_")
            ad_id, page = int(ad_id_str), int(page_str)
        except (ValueError, IndexError):
            await update.callback_query.edit_message_text("❌ Ошибка данных кнопки.")
            return

    elif update.message is not None:
        # Команда /ad_report
        args = context.args
        if not args:
            await update.message.reply_text(
                "❌ Использование: `/ad_report <ID> [стр]`\nПример: `/ad_report 1` или `/ad_report 1 2`",
                parse_mode="Markdown"
            )
            return
        try:
            ad_id = int(args[0])
            page = int(args[1]) if len(args) > 1 else 1
        except ValueError:
            await update.message.reply_text("❌ ID и страница должны быть числами.")
            return
    else:
        # Игнорируем неподдерживаемые типы апдейтов (edited_message, channel_post и т.д.)
        return

    # 📊 2. Получаем данные
    report = await get_campaign_report(ad_id, page)
    if not report:
        text = f"❌ Кампания #{ad_id} не найдена."
        if update.callback_query:
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return

    # 📝 3. Формируем текст
    c = report["campaign"]
    status_emoji = "🟢" if c["is_active"] else ("🔴" if c["remaining"] == 0 else "⏸")
    bought = c["shown_count"] + c["remaining"]

    text = (
        f"📊 **Отчёт: {c['title']}**\n"
        f"🆔 ID: `{c['id']}` | Тип: `{c['ad_type']}`\n"
        f"📦 Куплено: `{bought}` | ✅ Показано: `{c['shown_count']}` | ⏳ Осталось: `{c['remaining']}`\n"
        f"📅 Создана: `{c['created_at'][:10]}` | Статус: {status_emoji}\n\n"
        f"📋 **История показов** (стр. {report['current_page']}/{report['pages']}):\n"
    )

    if not report["impressions"]:
        text += "_Показов пока нет_\n"
    else:
        for i, imp in enumerate(report["impressions"], 1):
            time_str = imp["time"][11:16] if len(imp["time"]) > 16 else imp["time"]
            prompt_short = (imp["prompt"][:45] + "...") if imp["prompt"] and len(imp["prompt"]) > 45 else (imp["prompt"] or "—")
            text += f"{i}. `{time_str}` | User: `{imp['user_id']}`\n   `{prompt_short}`\n"

    # 🎛 4. Кнопки
    keyboard = []
    if report["pages"] > 1:
        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"ad_page_{ad_id}_{page-1}"))
        if page < report["pages"]:
            nav_row.append(InlineKeyboardButton("Вперёд ➡️", callback_data=f"ad_page_{ad_id}_{page+1}"))
        if nav_row:
            keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton("📥 Скачать CSV", callback_data=f"ad_csv_req_{ad_id}")])
    markup = InlineKeyboardMarkup(keyboard) if keyboard else None

    # 📤 5. Отправляем/Обновляем
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
    elif update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)


async def ad_report_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает кнопки пагинации отчёта"""
    query = update.callback_query
    await query.answer()

    # ad_page_123_2 → ad_id=123, page=2
    _, _, ad_id_str, page_str = query.data.split("_")
    context.args = [ad_id_str, page_str]
    await ad_report_cmd(update, context)


async def ad_csv_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает кнопку 'Скачать CSV'"""
    query = update.callback_query
    await query.answer("⏳ Готовлю файл...")

    ad_id = int(query.data.split("_")[-1])

    # Проверяем существование
    report = await get_campaign_report(ad_id)
    if not report:
        await query.edit_message_text("❌ Кампания не найдена.")
        return

    impressions = await get_all_campaign_impressions(ad_id,
                                                     anonymize=config.AD_REPORT_ANONYMIZE,
                                                     salt=config.AD_REPORT_SALT)
    if not impressions:
        await query.edit_message_text("📭 Для этой кампании пока нет показов.")
        return

    # Генерация CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Время показа", "User ID", "Промпт"])
    for imp in impressions:
        writer.writerow([imp["time"], imp["user_id"], imp["prompt"]])

    await query.message.reply_document(
        document=io.BytesIO(output.getvalue().encode("utf-8-sig")),
        filename=f"ad_report_{ad_id}_{report['campaign']['title'][:20]}.csv",
        caption=f"📊 Экспорт: {len(impressions)} показов"
    )

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Общая статистика бота"""
    if update.effective_user.id not in config.ADMINS:
        return

    try:
        # 1. Всего пользователей
        cursor = await async_db.conn.execute("SELECT COUNT(*) FROM user_settings")
        total_users = (await cursor.fetchone())[0]

        # 2. Новых пользователей сегодня
        cursor = await async_db.conn.execute(
            "SELECT COUNT(*) FROM user_settings WHERE date(created_at) = date('now')"
        )
        new_today = (await cursor.fetchone())[0]

        # 3. Всего генераций (сумма requests_count)
        cursor = await async_db.conn.execute(
            "SELECT COALESCE(SUM(requests_count), 0) FROM user_settings"
        )
        total_gens = (await cursor.fetchone())[0]

        # 4. Всего активированных реферальных кодов (для оценки виральности)
        cursor = await async_db.conn.execute(
            "SELECT COUNT(*) FROM user_promo_uses"
        )
        total_ref_uses = (await cursor.fetchone())[0]

        text = (
            "📊 **Статистика бота**\n\n"
            f"👥 Всего пользователей: `{total_users}`\n"
            f"🐣 Новых сегодня: `{new_today}`\n"
            f"🎨 Всего генераций: `{total_gens}`\n"
            f"🐾 Реферальных активаций: `{total_ref_uses}`\n"
        )

        await update.message.reply_text(text, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"❌ Ошибка в /stats: {e}", exc_info=True)
        await update.message.reply_text("❌ Не удалось получить статистику. Проверь логи.")


async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Топ-10 самых активных пользователей по реальным генерациям"""
    if update.effective_user.id not in config.ADMINS:
        return

    try:
        # Твой проверенный запрос
        cursor = await async_db.conn.execute(
            """SELECT us.user_id, us.username, COUNT(gs.id) as requests_count 
               FROM user_settings as us 
               LEFT JOIN generation_requests as gs ON us.user_id = gs.user
               GROUP BY us.user_id
               HAVING COUNT(gs.id) > 0
               ORDER BY requests_count DESC 
               LIMIT 10"""
        )
        rows = await cursor.fetchall()

        if not rows:
            await update.message.reply_text("📭 Пока нет пользователей с завершенными генерациями.")
            return

        text = "🏆 *Топ-10 художников*\n\n"
        for i, row in enumerate(rows, 1):
            uid, username, count = row

            # Берем имя или ID
            name = username or f"User_{uid}"

            #  БЕЗОПАСНОСТЬ: Экранируем символы, которые ломают Markdown
            # В обычном Markdown опасны в основном _ и *
            safe_name = str(name).replace("_", "\\_").replace("*", "\\*")

            text += f"{i}. `{safe_name}` ({uid}) — *{count}* артов\n"

        # Используем обычный Markdown вместо строгого MarkdownV2
        await update.message.reply_text(text, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"❌ Ошибка в /top: {e}", exc_info=True)
        await update.message.reply_text("❌ Не удалось получить топ.")


async def user_info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Детальная информация о пользователе: /user_info <user_id>"""
    if update.effective_user.id not in config.ADMINS:
        return

    if not context.args:
        await update.message.reply_text("Используй: `/user_info 123456789`", parse_mode="Markdown")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Неверный user_id. Должно быть число.")
        return

    try:
        # 1. Получаем настройки (без requests_count, он нам больше не нужен)
        cursor = await async_db.conn.execute(
            "SELECT username, created_at, model, preset FROM user_settings WHERE user_id = ?",
            (target_id,)
        )
        user_row = await cursor.fetchone()

        if not user_row:
            await update.message.reply_text(f"❌ Пользователь `{target_id}` не найден в базе.", parse_mode="Markdown")
            return

        username, created_at, model, preset = user_row

        # 2. 🔥 Считаем РЕАЛЬНОЕ количество генераций из generation_requests
        cursor = await async_db.conn.execute(
            "SELECT COUNT(id) FROM generation_requests WHERE user = ?",
            (target_id,)
        )
        real_req_count = (await cursor.fetchone())[0]

        # 3. Получаем квоты
        cursor = await async_db.conn.execute(
            "SELECT is_unlimited, is_banned, free_used, free_limit, paid_credits, paid_used FROM user_quota WHERE user_id = ?",
            (target_id,)
        )
        quota_row = await cursor.fetchone()

        if quota_row:
            is_unl, is_ban, free_used, free_lim, paid_cred, paid_used = quota_row
            quota_text = (
                f"🔓 Безлимит: `{'Да' if is_unl else 'Нет'}`\n"
                f"🚫 Бан: `{'Да' if is_ban else 'Нет'}`\n"
                f"🎁 Бесплатные: `{free_used}` / `{free_lim}` использовано\n"
                f"💳 Платные: `{paid_cred}` доступно, `{paid_used}` использовано"
            )
        else:
            quota_text = "⚠️ Запись в user_quota отсутствует (возможно, еще не генерировал)"

        # 4. Проверяем реферальную активность
        cursor = await async_db.conn.execute(
            "SELECT COUNT(*) FROM user_promo_uses WHERE user_id = ?", (target_id,)
        )
        ref_uses = (await cursor.fetchone())[0]

        # БЕЗОПАСНОСТЬ: Экранируем символы для Markdown
        safe_name = (username or f"User_{target_id}").replace("_", "\\_").replace("*", "\\*")

        text = (
            f" *Карточка пользователя*\n\n"
            f"🆔 ID: `{target_id}`\n"
            f"📛 Имя: `{safe_name}`\n"
            f" Регистрация: `{created_at[:10] if created_at else 'Н/Д'}`\n"
            f"🎨 Всего генераций: `{real_req_count}`\n"  # 🔥 Используем реальное число
            f"⚙️ Текущая модель: `{model or 'default'}`\n"
            f"📦 Текущий пресет: `{preset or 'default'}`\n"
            f"🐾 Активаций промокодов: `{ref_uses}`\n\n"
            f"*Баланс и лимиты:*\n{quota_text}"
        )

        await update.message.reply_text(text, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"❌ Ошибка в /user_info: {e}", exc_info=True)
        await update.message.reply_text("❌ Внутренняя ошибка при получении данных.")