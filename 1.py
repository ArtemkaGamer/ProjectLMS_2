import sqlite3
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.markdown import html_decoration as hd
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

API_TOKEN = '7555505954:AAGwbkcLkHOxQUVsd2zpX2ObmnlThhdWpfE'

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Настройки пагинации
MAX_PAGES = 3
MOVIES_PER_PAGE = 5

# Состояния для бронирования
class Form(StatesGroup):
    movie = State()
    full_name = State()
    phone = State()

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    
    # Создаем таблицу фильмов, если её нет
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS movies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        show_date TEXT NOT NULL,
        ticket_price INTEGER NOT NULL,
        hall TEXT NOT NULL
    )
    """)
    
    # Создаем таблицу бронирований, если её нет
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        full_name TEXT,
        phone TEXT,
        movie_title TEXT,
        show_date TEXT,
        ticket_price INTEGER,
        hall TEXT,
        booking_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Добавляем тестовые данные, если таблица пуста
    cursor.execute("SELECT COUNT(*) FROM movies")
    if cursor.fetchone()[0] == 0:
        test_movies = [
            ("Аватар", "2023-12-15 18:00", 350, "Зал 1"),
            ("Интерстеллар", "2023-12-15 21:00", 300, "Зал 2"),
            ("Дюна", "2023-12-16 15:00", 400, "Зал 1"),
            ("Начало", "2023-12-16 18:00", 250, "Зал 3"),
            ("Темный рыцарь", "2023-12-16 21:00", 350, "Зал 2"),
            ("Матрица", "2023-12-17 16:00", 300, "Зал 1"),
            ("Побег из Шоушенка", "2023-12-17 19:00", 200, "Зал 3"),
            ("Крестный отец", "2023-12-17 22:00", 250, "Зал 2"),
            ("Форрест Гамп", "2023-12-18 17:00", 300, "Зал 1"),
            ("Зеленая миля", "2023-12-18 20:00", 350, "Зал 3")
        ]
        cursor.executemany("INSERT INTO movies (title, show_date, ticket_price, hall) VALUES (?, ?, ?, ?)", test_movies)
    
    conn.commit()
    conn.close()

init_db()

# Основная клавиатура
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Расписание"), KeyboardButton(text="Забронировать")]
    ],
    resize_keyboard=True
)

# Получение списка фильмов
def get_movies():
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute("SELECT title, show_date, ticket_price, hall FROM movies ORDER BY show_date")
    movies = cursor.fetchall()
    conn.close()
    return movies

# Получение информации о фильме
def get_movie_info(title, date):
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute("SELECT title, show_date, ticket_price, hall FROM movies WHERE title = ? AND show_date = ?", (title, date))
    movie = cursor.fetchone()
    conn.close()
    return movie

# Получение страницы с фильмами
def get_movies_page(page=1):
    movies = get_movies()
    total_pages = min(MAX_PAGES, (len(movies) + MOVIES_PER_PAGE - 1) // MOVIES_PER_PAGE)
    page = max(1, min(page, total_pages))
    
    start = (page - 1) * MOVIES_PER_PAGE
    end = start + MOVIES_PER_PAGE
    page_movies = movies[start:end]
    
    message = f"<b>Расписание фильмов – страница {page} из {total_pages}</b>\n\n"
    for title, date, price, hall in page_movies:
        message += f"🎬 <b>{hd.quote(title)}</b>\n📅 {hd.quote(date)}\n💵 {price}₽\n🏛 Зал: {hd.quote(hall)}\n\n"
    
    return message, page, total_pages

# Генерация клавиатуры пагинации
def get_pagination_keyboard(page, total_pages):
    buttons = []
    
    if page > 1:
        buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"page_{page-1}"))
    if page < total_pages and page < MAX_PAGES:
        buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"page_{page+1}"))
    
    return InlineKeyboardMarkup(inline_keyboard=[buttons]) if buttons else None

# Генерация клавиатуры с фильмами для бронирования
def get_movies_booking_keyboard():
    movies = get_movies()
    keyboard = []
    for title, date, price, hall in movies:
        keyboard.append([InlineKeyboardButton(
            text=f"{title} ({date}) - {price}₽",
            callback_data=f"book_{title}_{date}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# Сохранение бронирования
def save_booking(user_id, full_name, phone, movie_title, show_date, ticket_price, hall):
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO bookings (user_id, full_name, phone, movie_title, show_date, ticket_price, hall)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, full_name, phone, movie_title, show_date, ticket_price, hall))
    conn.commit()
    conn.close()

# Обработка команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🎥 Добро пожаловать в бот кинотеатра!\n\n"
        "Выберите действие:",
        reply_markup=main_keyboard
    )

# Обработка команды /restart
@dp.message(Command("restart"))
async def cmd_restart(message: types.Message):
    await message.answer(
        "🔄 Сброс настроек. Выберите действие:",
        reply_markup=main_keyboard
    )

# Обработка кнопки "Расписание"
@dp.message(F.text.lower() == "расписание")
async def show_schedule(message: types.Message):
    schedule_text, page, total_pages = get_movies_page(1)
    keyboard = get_pagination_keyboard(page, total_pages)
    await message.answer(schedule_text, reply_markup=keyboard)

# Обработка команды /schedule
@dp.message(Command("schedule"))
async def cmd_schedule(message: types.Message):
    schedule_text, page, total_pages = get_movies_page(1)
    keyboard = get_pagination_keyboard(page, total_pages)
    await message.answer(schedule_text, reply_markup=keyboard)

# Обработка пагинации
@dp.callback_query(F.data.startswith("page_"))
async def process_pagination(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[1])
    schedule_text, current_page, total_pages = get_movies_page(page)
    keyboard = get_pagination_keyboard(current_page, total_pages)
    
    await callback.message.edit_text(
        text=schedule_text,
        reply_markup=keyboard
    )
    await callback.answer()

# Обработка кнопки "Забронировать"
@dp.message(F.text.lower() == "забронировать")
async def start_booking(message: types.Message, state: FSMContext):
    await message.answer(
        "🎟 Выберите фильм для бронирования:",
        reply_markup=get_movies_booking_keyboard()
    )
    await state.set_state(Form.movie)

# Обработка выбора фильма
@dp.callback_query(F.data.startswith("book_"), Form.movie)
async def select_movie(callback: types.CallbackQuery, state: FSMContext):
    _, title, date = callback.data.split("_", 2)
    movie_info = get_movie_info(title, date)
    
    if not movie_info:
        await callback.message.answer("❌ Ошибка: фильм не найден")
        await state.clear()
        return
    
    await state.update_data(
        movie_title=title,
        show_date=date,
        ticket_price=movie_info[2],
        hall=movie_info[3]
    )
    
    await callback.message.answer("✍️ Введите ваше ФИО полностью:")
    await state.set_state(Form.full_name)
    await callback.answer()

# Обработка ФИО
@dp.message(Form.full_name)
async def process_full_name(message: types.Message, state: FSMContext):
    if len(message.text.split()) < 2:
        await message.answer("❌ Пожалуйста, введите ФИО полностью (минимум 2 слова)")
        return
    
    await state.update_data(full_name=message.text)
    await message.answer("📱 Введите ваш номер телефона для связи:")
    await state.set_state(Form.phone)

# Обработка номера телефона
@dp.message(Form.phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text
    if not phone.replace("+", "").isdigit():
        await message.answer("❌ Пожалуйста, введите корректный номер телефона")
        return
    
    data = await state.get_data()
    
    # Сохраняем бронирование
    save_booking(
        user_id=message.from_user.id,
        full_name=data['full_name'],
        phone=phone,
        movie_title=data['movie_title'],
        show_date=data['show_date'],
        ticket_price=data['ticket_price'],
        hall=data['hall']
    )
    
    # Формируем сообщение с подтверждением
    confirmation = (
        "✅ <b>Бронирование успешно завершено!</b>\n\n"
        f"<b>Ваши данные:</b>\n"
        f"👤 ФИО: {data['full_name']}\n"
        f"📱 Телефон: {phone}\n\n"
        f"<b>Информация о сеансе:</b>\n"
        f"🎬 Фильм: {data['movie_title']}\n"
        f"📅 Дата и время: {data['show_date']}\n"
        f"💵 Стоимость билета: {data['ticket_price']}₽\n"
        f"🏛 Зал: {data['hall']}\n\n"
        "Спасибо за бронирование! Приятного просмотра!"
    )
    
    await message.answer(confirmation, reply_markup=main_keyboard)
    await state.clear()

# Запуск бота
async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())