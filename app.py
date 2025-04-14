import logging
import asyncio
import json
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
from aiohttp.web import Request, Response
import aiohttp_jinja2
import jinja2
import aiohttp
import os
from pathlib import Path
import aiofiles

os.makedirs('media', exist_ok=True)
# Настройка логирования
logging.basicConfig(level=logging.INFO)
# Telegram Bot Token
API_TOKEN = "7335306980:AAG87GPL3RtzxCCbdgcgpBmJpJi8-TX6WpE"

# ID чата для отправки репортов
REPORTS_CHAT_ID = "-1002363390445"


# Категории репортов
REPORT_CATEGORIES = ["Нарушение правил", "Спам", "Оскорбления", "Неадекватное поведение", "Другое"]

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Класс для хранения состояний FSM (Finite State Machine)
class ReportStates(StatesGroup):
    waiting_for_type = State()  # admin или user
    waiting_for_name = State()  # имя/ник пользователя
    waiting_for_category = State()  # категория репорта
    waiting_for_description = State()  # описание проблемы
    waiting_for_proof = State()  # доказательства (необязательно)
    waiting_for_anonymity = State()  # анонимность (да/нет)

# Словарь для хранения темы репортов и соответствующих им чатов
TOPICS = {
    "Администратор": 46,  # ID топика для жалоб на администраторов
    "Участник": 44       # ID топика для жалоб на участников
}
# Хранение отчетов в памяти (в реальном проекте лучше использовать базу данных)
reports = []

# Инициализация веб-приложения
app = web.Application()
routes = web.RouteTableDef()

# Настройка шаблонизатора Jinja2
aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader('templates'))

# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Создаем кнопки правильным образом для aiogram 3.x
    buttons = [
        [KeyboardButton(text="Создать репорт")],
        [KeyboardButton(text="Просмотреть сайт репортов")]
    ]
    # Создаем клавиатуру правильным образом
    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)
    await message.answer("👋 Привет! Я бот для создания репортов на администраторов и участников.\n"+"Вы можете создать репорт или посетить сайт с репортами.", reply_markup=keyboard)

# Обработка нажатия на кнопку "Создать репорт"
@dp.message(lambda message: message.text == "Создать репорт")
async def create_report(message: types.Message, state: FSMContext):
    buttons = [
        [KeyboardButton(text="Администратор")],
        [KeyboardButton(text="Участник")]
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)
    await message.answer("Выберите, на кого вы хотите создать репорт:", reply_markup=keyboard)
    await state.set_state(ReportStates.waiting_for_type)

# Обработка типа пользователя (администратор или участник)
@dp.message(ReportStates.waiting_for_type)
async def process_type(message: types.Message, state: FSMContext):
    if message.text not in ["Администратор", "Участник"]:
        await message.answer("Пожалуйста, выберите 'Администратор' или 'Участник' используя клавиатуру.")
        return
    
    await state.update_data(report_type=message.text)
    await message.answer("Введите имя/ник пользователя:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(ReportStates.waiting_for_name)

# Обработка имени пользователя
@dp.message(ReportStates.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(user_name=message.text)
    
    buttons = []
    for category in REPORT_CATEGORIES:
        buttons.append([KeyboardButton(text=category)])
    
    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)
    await message.answer("Выберите категорию репорта:", reply_markup=keyboard)
    await state.set_state(ReportStates.waiting_for_category)

# Обработка категории репорта
@dp.message(ReportStates.waiting_for_category)
async def process_category(message: types.Message, state: FSMContext):
    if message.text not in REPORT_CATEGORIES:
        await message.answer("Пожалуйста, выберите категорию из списка используя клавиатуру.")
        return
    
    await state.update_data(category=message.text)
    await message.answer("Опишите проблему подробно:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(ReportStates.waiting_for_description)

# Обработка описания проблемы
@dp.message(ReportStates.waiting_for_description)
async def process_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    
    buttons = [[KeyboardButton(text="Пропустить")]]
    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)
    await message.answer("Отправьте доказательства (текст или ссылка на сообщение) или нажмите 'Пропустить':", 
                         reply_markup=keyboard)
    await state.set_state(ReportStates.waiting_for_proof)



# Модификация обработчика доказательств
@dp.message(ReportStates.waiting_for_proof)
async def process_proof(message: types.Message, state: FSMContext):
    data = await state.get_data()
    media_list = []  # Список для хранения информации о медиафайлах
    
    # Обработка текста как доказательства или как подписи к медиа
    caption = ""
    if message.text and message.text != "Пропустить":
        if not message.media_group_id:  # Если это просто текст без медиагруппы
            proof = message.text
            await state.update_data(proof=proof, media_list=[])
        else:
            caption = message.text  # Сохраняем подпись к медиа
    
    # Обработка фото
    if message.photo:
        file_id = message.photo[-1].file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path
        
        # Создаем уникальное имя файла
        file_name = f"photo_{file_id.replace(':', '_').replace('-', '_')}.jpg"
        file_save_path = f"media/{file_name}"
        
        # Скачиваем и сохраняем файл
        await bot.download_file(file_path, file_save_path)
        
        # Добавляем информацию о файле в список
        media_list.append({
            "type": "photo",
            "file_id": file_id,
            "file_path": file_save_path,
            "caption": caption if caption else "Без подписи"
        })
        
        proof = f"Фотография (сохранена как {file_name})"
    
    # Обработка документа
    elif message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name or f"document_{file_id.replace(':', '_').replace('-', '_')}"
        file = await bot.get_file(file_id)
        file_path = file.file_path
        
        # Скачиваем и сохраняем файл
        file_save_path = f"media/{file_name}"
        await bot.download_file(file_path, file_save_path)
        
        # Добавляем информацию о файле в список
        media_list.append({
            "type": "document",
            "file_id": file_id,
            "file_path": file_save_path,
            "caption": caption if caption else "Без подписи"
        })
        
        proof = f"Документ {file_name}"
    
    # Обработка видео
    elif message.video:
        file_id = message.video.file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path
        
        # Создаем уникальное имя файла
        file_name = f"video_{file_id.replace(':', '_').replace('-', '_')}.mp4"
        file_save_path = f"media/{file_name}"
        
        # Скачиваем и сохраняем файл
        await bot.download_file(file_path, file_save_path)
        
        # Добавляем информацию о файле в список
        media_list.append({
            "type": "video",
            "file_id": file_id,
            "file_path": file_save_path,
            "caption": caption if caption else "Без подписи"
        })
        
        proof = f"Видео (сохранено как {file_name})"
    
    # Обработка голосового сообщения
    elif message.voice:
        file_id = message.voice.file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path
        
        # Создаем уникальное имя файла
        file_name = f"voice_{file_id.replace(':', '_').replace('-', '_')}.ogg"
        file_save_path = f"media/{file_name}"
        
        # Скачиваем и сохраняем файл
        await bot.download_file(file_path, file_save_path)
        
        # Добавляем информацию о файле в список
        media_list.append({
            "type": "voice",
            "file_id": file_id,
            "file_path": file_save_path,
            "caption": caption if caption else "Без подписи"
        })
        
        proof = f"Голосовое сообщение (сохранено как {file_name})"
    
    # Если не было медиаконтента и текста
    elif not message.text or message.text == "Пропустить":
        proof = "Не предоставлены"
        media_list = []
    
    # Обновляем данные состояния
    current_media = data.get('media_list', [])
    if media_list:
        current_media.extend(media_list)
    
    await state.update_data(proof=proof, media_list=current_media)
    
    # Проверяем, есть ли медиагруппа и ожидаем все медиа из неё
    if message.media_group_id:
        # Если это часть медиагруппы, ожидаем некоторое время для получения всех медиа
        # Не меняем состояние, чтобы получить все файлы из медиагруппы
        await message.answer("Получено медиа. Отправьте остальные или напишите 'Готово', когда закончите.")
        return
    
    # Если это не часть медиагруппы или получили все медиа, переходим к следующему шагу
    buttons = [
        [KeyboardButton(text="Да, отправить анонимно")],
        [KeyboardButton(text="Нет, указать мои данные")]
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)
    await message.answer("Хотите отправить репорт анонимно?", reply_markup=keyboard)
    await state.set_state(ReportStates.waiting_for_anonymity)

# Добавим дополнительное состояние для завершения отправки медиа
@dp.message(lambda message: message.text == "Готово" and message.chat.type == "private")
async def finish_media_upload(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    
    if current_state == ReportStates.waiting_for_proof.state:
        buttons = [
            [KeyboardButton(text="Да, отправить анонимно")],
            [KeyboardButton(text="Нет, указать мои данные")]
        ]
        keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)
        await message.answer("Все медиафайлы получены. Хотите отправить репорт анонимно?", reply_markup=keyboard)
        await state.set_state(ReportStates.waiting_for_anonymity)

# Модификация отправки репорта
@dp.message(ReportStates.waiting_for_anonymity)
async def process_anonymity(message: types.Message, state: FSMContext):
    is_anonymous = message.text == "Да, отправить анонимно"
    data = await state.get_data()
    
    # Сохраняем все данные репорта
    report_data = {
        "report_type": data["report_type"],
        "user_name": data["user_name"],
        "category": data["category"],
        "description": data["description"],
        "proof": data["proof"],
        "is_anonymous": is_anonymous,
        "reporter_id": message.from_user.id if not is_anonymous else "Анонимно",
        "reporter_username": message.from_user.username if not is_anonymous else "Анонимно",
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "media_list": data.get("media_list", [])
    }
    
    # Добавляем репорт в список
    reports.append(report_data)
    
    # Сохраняем в файл
    with open("reports.json", "w", encoding="utf-8") as f:
        json.dump(reports, f, ensure_ascii=False, indent=4)
    
    # Отправляем репорт в чат
    report_message = (
        f"📢 НОВЫЙ РЕПОРТ\n\n"
        f"👤 Тип: {report_data['report_type']}\n"
        f"🔖 Имя: {report_data['user_name']}\n"
        f"📌 Категория: {report_data['category']}\n"
        f"📝 Описание: {report_data['description']}\n\n"
    )
    
    if is_anonymous:
        report_message += f"👮 Отправитель: Анонимно\n"
    else:
        report_message += f"👮 Отправитель: @{report_data['reporter_username']} (ID: {report_data['reporter_id']})\n"
    
    report_message += f"📅 Дата: {report_data['date']}"
    
    # Получаем ID топика для этого типа пользователя
    topic_id = TOPICS.get(report_data['report_type'], None)
    
    # Отправляем сообщение и медиа в чат
    media_files = data.get("media_list", [])
    
    if topic_id:
        # Сначала отправляем основное сообщение
        await bot.send_message(
            chat_id=REPORTS_CHAT_ID,
            text=report_message,
            message_thread_id=topic_id
        )
        
        # Затем отправляем все медиафайлы
        for media in media_files:
            if media["type"] == "photo":
                await bot.send_photo(
                    chat_id=REPORTS_CHAT_ID,
                    photo=types.FSInputFile(media["file_path"]),
                    caption=media["caption"],
                    message_thread_id=topic_id
                )
            elif media["type"] == "document":
                await bot.send_document(
                    chat_id=REPORTS_CHAT_ID,
                    document=types.FSInputFile(media["file_path"]),
                    caption=media["caption"],
                    message_thread_id=topic_id
                )
            elif media["type"] == "video":
                await bot.send_video(
                    chat_id=REPORTS_CHAT_ID,
                    video=types.FSInputFile(media["file_path"]),
                    caption=media["caption"],
                    message_thread_id=topic_id
                )
            elif media["type"] == "voice":
                await bot.send_voice(
                    chat_id=REPORTS_CHAT_ID,
                    voice=types.FSInputFile(media["file_path"]),
                    caption=media["caption"],
                    message_thread_id=topic_id
                )
    else:
        # То же самое, но без указания топика
        await bot.send_message(
            chat_id=REPORTS_CHAT_ID,
            text=report_message
        )
        
        for media in media_files:
            if media["type"] == "photo":
                await bot.send_photo(
                    chat_id=REPORTS_CHAT_ID,
                    photo=types.FSInputFile(media["file_path"]),
                    caption=media["caption"]
                )
            elif media["type"] == "document":
                await bot.send_document(
                    chat_id=REPORTS_CHAT_ID,
                    document=types.FSInputFile(media["file_path"]),
                    caption=media["caption"]
                )
            elif media["type"] == "video":
                await bot.send_video(
                    chat_id=REPORTS_CHAT_ID,
                    video=types.FSInputFile(media["file_path"]),
                    caption=media["caption"]
                )
            elif media["type"] == "voice":
                await bot.send_voice(
                    chat_id=REPORTS_CHAT_ID,
                    voice=types.FSInputFile(media["file_path"]),
                    caption=media["caption"]
                )
    
    await message.answer("✅ Ваш репорт успешно отправлен! Спасибо за обращение.", 
                         reply_markup=ReplyKeyboardRemove())
    
    # Сбрасываем состояние
    await state.clear()

# Веб-интерфейс для просмотра репортов
@routes.get('/')
@aiohttp_jinja2.template('index.html')
async def index(request):
    return {"reports": reports, "categories": REPORT_CATEGORIES}

# Обработка отправки репорта с сайта
@routes.post('/submit_report')
@aiohttp_jinja2.template('success.html')
async def submit_report(request):
    data = await request.post()
    
    is_anonymous = "is_anonymous" in data
    
    report_data = {
        "report_type": data.get('report_type', ''),
        "user_name": data.get('user_name', ''),
        "category": data.get('category', ''),
        "description": data.get('description', ''),
        "proof": data.get('proof', 'Не предоставлены'),
        "is_anonymous": is_anonymous,
        "reporter_id": "web" if not is_anonymous else "Анонимно",
        "reporter_username": data.get('reporter_username', 'web') if not is_anonymous else "Анонимно",
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Добавляем репорт в список
    reports.append(report_data)
    
    # Сохраняем в файл
    with open("reports.json", "w", encoding="utf-8") as f:
        json.dump(reports, f, ensure_ascii=False, indent=4)
    
    # Отправляем репорт в чат
    report_message = (
        f"📢 НОВЫЙ РЕПОРТ (с сайта)\n\n"
        f"👤 Тип: {report_data['report_type']}\n"
        f"🔖 Имя: {report_data['user_name']}\n"
        f"📌 Категория: {report_data['category']}\n"
        f"📝 Описание: {report_data['description']}\n\n"
        f"🔍 Доказательства: {report_data['proof']}\n\n"
    )
    
    if is_anonymous:
        report_message += f"👮 Отправитель: Анонимно\n"
    else:
        report_message += f"👮 Отправитель: {report_data['reporter_username']}\n"
    
    report_message += f"📅 Дата: {report_data['date']}"
    
    # Получаем ID топика для типа пользователя (администратор или участник)
    topic_id = TOPICS.get(report_data['report_type'], None)
    
    # Отправляем сообщение в чат с указанием топика
    if topic_id:
        await bot.send_message(
            chat_id=REPORTS_CHAT_ID,
            text=report_message,
            message_thread_id=topic_id
        )
    else:
        await bot.send_message(
            chat_id=REPORTS_CHAT_ID,
            text=report_message
        )
    
    return {"report": report_data}

# Обработка нажатия на кнопку "Просмотреть сайт репортов"
@dp.message(lambda message: message.text == "Просмотреть сайт репортов")
async def view_reports_site(message: types.Message):
    await message.answer("Вы можете посетить сайт репортов по ссылке: https://amogus-reports.onrender.com/")

# Обработка всех остальных сообщений
# Изменяем обработчик, чтобы он отвечал только в приватных чатах
@dp.message(lambda message: message.chat.type == "private")
async def echo(message: types.Message):
    buttons = [
        [KeyboardButton(text="Создать репорт")],
        [KeyboardButton(text="Просмотреть сайт репортов")]
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)
    await message.answer("Я вас не понял. Пожалуйста, воспользуйтесь кнопками меню.", reply_markup=keyboard)

# Создаем шаблоны HTML для веб-интерфейса
def setup_templates():
    os.makedirs('templates', exist_ok=True)
    
    # Шаблон для главной страницы
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write('''
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Система репортов</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    margin: 0;
                    padding: 20px;
                    background: linear-gradient(135deg,#ff0000,#ff9900,#ff0000,#ff9900);
                }
                .container {
                    max-width: 800px;
                    margin: 0 auto;
                    background: #fff;
                    padding: 20px;
                    border-radius: 5px;
                    box-shadow: 0 0 10px rgba(0,0,0,0.1);
                }
                h1, h2 {
                    color: #333;
                }
                form {
                    margin-bottom: 30px;
                }
                .form-group {
                    margin-bottom: 15px;
                }
                label {
                    display: block;
                    margin-bottom: 5px;
                    font-weight: bold;
                }
                input, select, textarea {
                    width: 100%;
                    padding: 8px;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                }
                .checkbox-group {
                    display: flex;
                    align-items: center;
                    margin-bottom: 15px;
                }
                .checkbox-group input {
                    width: auto;
                    margin-right: 10px;
                }
                .checkbox-group label {
                    display: inline;
                    font-weight: normal;
                }
                button {
                    background: linear-gradient(to bottom,#0004ff,#0059ff,#00ccff);
                    color: white;
                    border: none;
                    padding: 10px 15px;
                    border-radius: 4px;
                    cursor: pointer;
                }
                button:hover {
                    background: linear-gradient(to bottom,#000281,#003eb3,#0093b8);
                }
                .report {
                    background: #f9f9f9;
                    padding: 15px;
                    margin-bottom: 15px;
                    border-left: 4px solid #293af2;
                }
                .report h3 {
                    margin-top: 0;
                }
                .filters {
                    margin-bottom: 20px;
                }
                .anonymous-tag {
                    background: #f0ad4e;
                    color: white;
                    padding: 2px 5px;
                    border-radius: 3px;
                    font-size: 12px;
                    margin-left: 5px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Система репортов на администраторов и участников</h1>
                
                <h2>Создать новый репорт</h2>
                <form action="/submit_report" method="post">
                    <div class="form-group">
                        <label for="report_type">Тип пользователя:</label>
                        <select id="report_type" name="report_type" required>
                            <option value="Администратор">Администратор</option>
                            <option value="Участник">Участник</option>
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label for="user_name">Имя/ник пользователя:</label>
                        <input type="text" id="user_name" name="user_name" required>
                    </div>
                    
                    <div class="form-group">
                        <label for="category">Категория репорта:</label>
                        <select id="category" name="category" required>
                            {% for category in categories %}
                            <option value="{{ category }}">{{ category }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label for="description">Описание проблемы:</label>
                        <textarea id="description" name="description" rows="5" required></textarea>
                    </div>
                    
                    <div class="form-group">
                        <label for="proof">Доказательства (ссылка или описание):</label>
                        <textarea id="proof" name="proof" rows="3"></textarea>
                    </div>
                    
                    <div class="checkbox-group">
                        <input type="checkbox" id="is_anonymous" name="is_anonymous">
                        <label for="is_anonymous">Отправить анонимно</label>
                    </div>
                    
                    <div class="form-group" id="reporter_info">
                        <label for="reporter_username">Ваше имя или контакт:</label>
                        <input type="text" id="reporter_username" name="reporter_username">
                    </div>
                    
                    <button type="submit">Отправить репорт</button>
                </form>
                
                <h2>Последние репорты</h2>
                <div class="filters">
                    <label>Фильтр по типу: </label>
                    <select id="type-filter" onchange="filterReports()">
                        <option value="all">Все типы</option>
                        <option value="Администратор">Администраторы</option>
                        <option value="Участник">Участники</option>
                    </select>
                    
                    <label style="margin-left: 15px;">Фильтр по категории: </label>
                    <select id="category-filter" onchange="filterReports()">
                        <option value="all">Все категории</option>
                        {% for category in categories %}
                        <option value="{{ category }}">{{ category }}</option>
                        {% endfor %}
                    </select>
                </div>
                
                <div id="reports-list">
                    {% if reports %}
                        {% for report in reports %}
                        <div class="report" data-type="{{ report.report_type }}" data-category="{{ report.category }}">
                            <h3>Репорт на {{ report.report_type }}: {{ report.user_name }}
                                {% if report.is_anonymous %}
                                <span class="anonymous-tag">Анонимно</span>
                                {% endif %}
                            </h3>
                            <p><strong>Категория:</strong> {{ report.category }}</p>
                            <p><strong>Описание:</strong> {{ report.description }}</p>
                            <p><strong>Доказательства:</strong> {{ report.proof }}</p>
                            <p><strong>Отправитель:</strong> {{ report.reporter_username }}</p>
                            <p><strong>Дата:</strong> {{ report.date }}</p>
                        </div>
                        {% endfor %}
                    {% else %}
                        <p>Пока нет репортов.</p>
                    {% endif %}
                </div>
            </div>
            
            <script>
                // Функция для фильтрации репортов
                function filterReports() {
                    const typeFilter = document.getElementById('type-filter').value;
                    const categoryFilter = document.getElementById('category-filter').value;
                    const reports = document.querySelectorAll('.report');
                    
                    reports.forEach(report => {
                        const typeMatch = typeFilter === 'all' || report.dataset.type === typeFilter;
                        const categoryMatch = categoryFilter === 'all' || report.dataset.category === categoryFilter;
                        
                        if (typeMatch && categoryMatch) {
                            report.style.display = 'block';
                        } else {
                            report.style.display = 'none';
                        }
                    });
                }
                
                // Управление полем имени отправителя при выборе анонимности
                document.getElementById('is_anonymous').addEventListener('change', function() {
                    const reporterInfo = document.getElementById('reporter_info');
                    if (this.checked) {
                        reporterInfo.style.display = 'none';
                    } else {
                        reporterInfo.style.display = 'block';
                    }
                });
            </script>
        </body>
        </html>
        ''')
    
    # Шаблон для страницы успешной отправки репорта
    with open('templates/success.html', 'w', encoding='utf-8') as f:
        f.write('''
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Репорт отправлен</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    margin: 0;
                    padding: 20px;
                    background-color: #f4f4f4;
                }
                .container {
                    max-width: 800px;
                    margin: 0 auto;
                    background: #fff;
                    padding: 20px;
                    border-radius: 5px;
                    box-shadow: 0 0 10px rgba(0,0,0,0.1);
                    text-align: center;
                }
                h1 {
                    background: linear-gradient(to bottom, #0004ff, #0059ff, #00ccff);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                    margin-bottom: 20px;
                }
                .report-details {
                    text-align: left;
                    background: #f9f9f9;
                    padding: 20px;
                    border-radius: 5px;
                    margin: 20px 0;
                    border-left: 4px solid #293af2;
                }
                
                .btn {
                    display: inline-block;
                    background: linear-gradient(to bottom,#0004ff,#0059ff,#00ccff);
                    color: white;
                    text-decoration: none;
                    padding: 10px 20px;
                    border-radius: 4px;
                    margin-top: 20px;
                }
                .btn:hover {
                    background: linear-gradient(to bottom,#000281,#003eb3,#0093b8);
                }
                .anonymous-tag {
                    background: #f0ad4e;
                    color: white;
                    padding: 2px 5px;
                    border-radius: 3px;
                    font-size: 12px;
                    margin-left: 5px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Репорт успешно отправлен!</h1>
                
                <div class="report-details" class="gradient-border">
                    <h2>Детали вашего репорта
                        {% if report.is_anonymous %}
                        <span class="anonymous-tag">Анонимно</span>
                        {% endif %}
                    </h2>
                    <p><strong>Тип пользователя:</strong> {{ report.report_type }}</p>
                    <p><strong>Имя/ник пользователя:</strong> {{ report.user_name }}</p>
                    <p><strong>Категория:</strong> {{ report.category }}</p>
                    <p><strong>Описание:</strong> {{ report.description }}</p>
                    <p><strong>Доказательства:</strong> {{ report.proof }}</p>
                    <p><strong>Дата:</strong> {{ report.date }}</p>
                </div>
                
                <p>Спасибо за ваше обращение. Ваш репорт был успешно зарегистрирован и отправлен администраторам.</p>
                
                <a href="/" class="btn">Вернуться на главную</a>
            </div>
        </body>
        </html>
        ''')

async def keep_alive():
    """Отправляет периодические запросы на сервер, чтобы предотвратить его засыпание."""
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                await session.get("https://amogus-reports.onrender.com/")
                logging.info("Отправлен пинг для поддержки активности")
        except Exception as e:
            logging.error(f"Ошибка поддержки активности: {e}")
        
        # Ждем 5 минут до следующего пинга
        await asyncio.sleep(60)  # 300 секунд = 5 минут

# Функция для запуска бота и веб-сервера
async def main():
    # Настройка веб-маршрутов
    app.add_routes(routes)
    
    # Создаем шаблоны для веб-интерфейса
    setup_templates()
    
    # Загружаем существующие репорты, если есть
    if os.path.exists("reports.json"):
        try:
            with open("reports.json", "r", encoding="utf-8") as f:
                global reports
                reports = json.load(f)
        except:
            pass
    
    # Запускаем веб-сервер в отдельной задаче
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    
    print("Веб-сервер запущен на https://amogus-reports.onrender.com/")

    asyncio.create_task(keep_alive())
    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
