import json
import os
from flask import Flask, request, render_template
from aiogram import Bot, Dispatcher
import asyncio

# Настройки
TELEGRAM_TOKEN = "7335306980:AAG87GPL3RtzxCCbdgcgpBmJpJi8-TX6WpE"  # Замените на ваш токен от BotFather
CHAT_ID = "-1002363390445"  # Замените на ID чата
REPORTS_FILE = "reports.json"

# ID тем в чате (нужно получить через Telegram API или вручную)
TOPIC_ADMIN_COMPLAINTS = 46  # Замените на ID темы "Жалобы на админов"
TOPIC_USER_COMPLAINTS = 44   # Замените на ID темы "Жалобы на участников"

app = Flask(__name__)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)
bot_running = False

# Загрузка существующих репортов
def load_reports():
    if os.path.exists(REPORTS_FILE):
        with open(REPORTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

# Сохранение репортов
def save_reports(reports):
    with open(REPORTS_FILE, "w", encoding="utf-8") as f:
        json.dump(reports, f, ensure_ascii=False, indent=4)

# Отправка репортов в Telegram с учетом темы
async def send_report_to_telegram(report, category):
    global bot_running
    try:
        if bot_running:
            topic_id = TOPIC_ADMIN_COMPLAINTS if category == "admin" else TOPIC_USER_COMPLAINTS
            await bot.send_message(
                chat_id=CHAT_ID,
                text=f"Анонимный репорт:\n{report}",
                message_thread_id=topic_id  # Указываем тему
            )
            return True
    except Exception as e:
        print(f"Ошибка отправки: {e}")
    return False

# Главная страница
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        report = request.form.get("report")
        category = request.form.get("category")  # "admin" или "user"
        if report and category in ["admin", "user"]:
            reports = load_reports()
            report_data = {"text": report, "category": category}
            reports.append(report_data)
            save_reports(reports)
            # Пробуем отправить сразу
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = loop.run_until_complete(send_report_to_telegram(report, category))
            if success:
                reports.remove(report_data)  # Удаляем из файла, если отправлено
                save_reports(reports)
            return "Репорт отправлен или сохранен!"
        return "Ошибка: выберите категорию и введите репорт!"
    return render_template("index.html")

# Отправка сохраненных репортов при запуске бота
async def send_pending_reports():
    reports = load_reports()
    if reports:
        for report_data in reports[:]:  # Копируем список для безопасного удаления
            success = await send_report_to_telegram(report_data["text"], report_data["category"])
            if success:
                reports.remove(report_data)
        save_reports(reports)

# Запуск бота
async def start_bot():
    global bot_running
    bot_running = True
    print("Бот запущен!")
    await send_pending_reports()  # Отправляем сохраненные репорты
    await dp.start_polling()

if __name__ == "__main__":
    # Запуск Flask и бота в одном цикле
    loop = asyncio.get_event_loop()
    loop.create_task(start_bot())
    app.run(debug=True, use_reloader=False)