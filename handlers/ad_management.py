import csv
import json
import io
import logging
from telegram import Update
from telegram.ext import ContextTypes
from db.async_core import async_db
from config import ADMINS

logger = logging.getLogger(__name__)


async def handle_ad_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимает .csv/.json от админа → валидирует → вставляет в БД"""
    if update.effective_user.id not in ADMINS:
        return

    doc = update.message.document
    if not doc:
        return

    file_ext = doc.file_name.lower().split('.')[-1]
    if file_ext not in ('csv', 'json'):
        return  # Игнорируем другие файлы

    # Скачиваем в память (никакого мусора на диске)
    file_obj = await doc.get_file()
    file_bytes = await file_obj.download_as_bytearray()
    content = file_bytes.decode('utf-8-sig')  # utf-8-sig для Excel

    campaigns = []
    try:
        if file_ext == 'csv':
            reader = csv.DictReader(io.StringIO(content))
            for row in reader:
                campaigns.append({
                    "title": row.get("title", "").strip(),
                    "ad_type": row.get("ad_type", "photo").strip().lower(),
                    "content": row.get("content", "").strip(),
                    "target_link": row.get("target_link", "").strip(),
                    "btn_text": row.get("btn_text", "👀 Перейти").strip(),
                    "remaining": int(row.get("remaining", 0))
                })
        else:
            data = json.loads(content)
            campaigns = data if isinstance(data, list) else [data]
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка парсинга: {e}")
        return

    if not campaigns:
        await update.message.reply_text("📭 Файл пуст или не содержит данных.")
        return

    # 🛡 Транзакционная вставка с валидацией
    success, errors = 0, []
    try:
        await async_db.conn.execute("BEGIN TRANSACTION")
        for i, camp in enumerate(campaigns, 1):
            # Минимальная валидация
            if not camp.get("title") or not camp.get("content") or not camp.get("target_link"):
                errors.append(f"Строка {i}: пропущены title, content или target_link")
                continue
            if camp.get("remaining", 0) <= 0:
                errors.append(f"Строка {i}: remaining должен быть > 0")
                continue
            if camp.get("ad_type") not in ("photo", "text"):
                errors.append(f"Строка {i}: ad_type должен быть 'photo' или 'text'")
                continue

            await async_db.conn.execute(
                """INSERT INTO ad_campaigns 
                   (title, ad_type, content, target_link, btn_text, remaining, is_active) 
                   VALUES (?, ?, ?, ?, ?, ?, 1)""",
                (camp["title"], camp["ad_type"], camp["content"],
                 camp["target_link"], camp["btn_text"], camp["remaining"])
            )
            success += 1

        await async_db.conn.commit()
    except Exception as db_err:
        await async_db.conn.rollback()
        await update.message.reply_text(f"❌ Ошибка БД (транзакция отменена): {db_err}")
        return

    # 📤 Отчёт
    text = f"✅ Успешно добавлено: {success} кампаний"
    if errors:
        text += f"\n⚠️ Пропущено ({len(errors)}):\n" + "\n".join(errors[:5])
        if len(errors) > 5:
            text += f"\n...и ещё {len(errors) - 5}"

    await update.message.reply_text(text)
    logger.info(f"📥 Импорт рекламы: {success} ок, {len(errors)} ошибок")


async def send_ad_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет готовый шаблон CSV"""
    if update.effective_user.id not in ADMINS:
        return

    template = "title,ad_type,content,target_link,btn_text,remaining\nМой Бренд,photo,https://i.imgur.com/demo.jpg,https://t.me/mybot,🚀 Перейти,100"
    await update.message.reply_document(
        document=io.BytesIO(template.encode("utf-8-sig")),
        filename="ad_template.csv",
        caption="📥 Шаблон для загрузки рекламы.\nЗаполни файл и отправь мне обратно!"
    )