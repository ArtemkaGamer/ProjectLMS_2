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

API_TOKEN = '7744367169:AAE_CnE7Y53k2Ib1gW_U8Bm5L9VGQj7AtnQ'

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Настройки пагинации
MAX_PAGES = 3
MOVIES_PER_PAGE = 5

# Название кинотеатра и настройки залов
CINEMA_NAME = "🌟 Stellar Cinema"
WELCOME_STICKER = "CAACAgIAAxkBAAEBPKpoDhwKOhYtFehUUKr2NQ2XDAOVWwACRwADWbv8JVyd1qxN32EsNgQ"

# Конфигурация залов
HALLS_CONFIG = {
    "Зал 1": {
        "seats_count": 30,
        "seats_per_row": 5,
        "description": "Стандартный зал с удобными креслами",
        "emoji": "🪑"
    },
    "Зал 2": {
        "seats_count": 25,
        "seats_per_row": 5,
        "description": "Зал с увеличенным расстоянием между рядами",
        "emoji": "🚀"
    },
    "Зал 3": {
        "seats_count": 40,
        "seats_per_row": 8,
        "description": "Большой зал для премьерных показов",
        "emoji": "🎪"
    },
    "VIP Зал": {
        "seats_count": 10,
        "seats_per_row": 2,
        "description": "Премиум зал с диванами и сервисом",
        "emoji": "🛋️",
        "is_vip": True
    }
}

# Состояния для бронирования
class Form(StatesGroup):
    movie = State()
    full_name = State()
    phone = State()
    seat = State()

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS movies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        show_date TEXT NOT NULL,
        ticket_price INTEGER NOT NULL,
        hall TEXT NOT NULL
    )
    """)
    
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
        seat_number INTEGER,
        booking_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    cursor.execute("SELECT COUNT(*) FROM movies")
    if cursor.fetchone()[0] == 0:
        test_movies = [
            ("Аватар", "2023-12-15 18:00", 350, "Зал 1"),
            ("Интерстеллар", "2023-12-15 21:00", 300, "Зал 2"),
            ("Дюна", "2023-12-16 15:00", 400, "Зал 3"),
            ("Начало", "2023-12-16 18:00", 250, "Зал 1"),
            ("Темный рыцарь", "2023-12-16 21:00", 350, "Зал 2"),
            ("Оppenheimer", "2023-12-17 20:00", 800, "VIP Зал"),
        ]
        cursor.executemany("INSERT INTO movies (title, show_date, ticket_price, hall) VALUES (?, ?, ?, ?)", test_movies)
    
    conn.commit()
    conn.close()

init_db()

# Основная клавиатура
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Расписание"), KeyboardButton(text="Забронировать")],
        [KeyboardButton(text="О нас")]
    ],
    resize_keyboard=True
)

# Получение списка занятых мест для фильма
def get_booked_seats(movie_title, show_date):
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute("""
    SELECT seat_number FROM bookings 
    WHERE movie_title = ? AND show_date = ?
    """, (movie_title, show_date))
    booked_seats = [row[0] for row in cursor.fetchall()]
    conn.close()
    return booked_seats

# Генерация клавиатуры с местами
def generate_seats_keyboard(movie_title, show_date, hall_name):
    hall_config = HALLS_CONFIG.get(hall_name, HALLS_CONFIG["Зал 1"])
    booked_seats = get_booked_seats(movie_title, show_date)
    keyboard = []
    row_buttons = []
    
    for seat in range(1, hall_config["seats_count"] + 1):
        if seat in booked_seats:
            emoji = "❌"  # Занятое место
        else:
            emoji = "💺" if not hall_config.get("is_vip", False) else "🛋️"  # Кресло или диван
            
        row_buttons.append(InlineKeyboardButton(
            text=f"{emoji} {seat}",
            callback_data=f"seat_taken_{seat}" if seat in booked_seats else f"seat_{seat}"
        ))
        
        # Формируем ряды согласно конфигурации
        if seat % hall_config["seats_per_row"] == 0 or seat == hall_config["seats_count"]:
            keyboard.append(row_buttons)
            row_buttons = []
    
    # Добавляем информацию о зале
    info_button = InlineKeyboardButton(
        text=f"ℹ️ {hall_name}: {hall_config['description']}",
        callback_data="hall_info"
    )
    keyboard.append([info_button])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

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
        hall_emoji = HALLS_CONFIG.get(hall, {}).get("emoji", "🎬")
        message += f"{hall_emoji} <b>{hd.quote(title)}</b>\n📅 {hd.quote(date)}\n💵 {price}₽\n🏛 {hall}\n\n"
    
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
        hall_emoji = HALLS_CONFIG.get(hall, {}).get("emoji", "🎬")
        keyboard.append([InlineKeyboardButton(
            text=f"{hall_emoji} {title} ({date}) - {price}₽",
            callback_data=f"book_{title}_{date}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# Сохранение бронирования
def save_booking(user_id, full_name, phone, movie_title, show_date, ticket_price, hall, seat_number):
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO bookings (user_id, full_name, phone, movie_title, show_date, ticket_price, hall, seat_number)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, full_name, phone, movie_title, show_date, ticket_price, hall, seat_number))
    conn.commit()
    conn.close()

# Обработка команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer_sticker(WELCOME_STICKER)
    
    welcome_text = (
        f"✨ Добро пожаловать в {CINEMA_NAME} — место, где оживают мечты! ✨\n\n"
        "🎬 Мы предлагаем вам уникальный киноопыт с лучшими фильмами в потрясающем качестве.\n"
        "💫 Современные залы с Dolby Atmos, удобные кресла и неповторимая атмосфера.\n\n"
        "Выберите действие:"
    )
    
    await message.answer(
        welcome_text,
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
    
    await state.update_data(phone=phone)
    
    data = await state.get_data()
    hall_name = data['hall']
    hall_config = HALLS_CONFIG.get(hall_name, HALLS_CONFIG["Зал 1"])
    
    seat_type = "диваны 🛋️" if hall_config.get("is_vip", False) else "места 💺"
    
    await message.answer(
        f"📍 Выберите {seat_type} в зале {hall_name}:\n"
        f"🛋️ - свободные {seat_type}\n"
        "❌ - занятые места",
        reply_markup=generate_seats_keyboard(data['movie_title'], data['show_date'], hall_name)
    )
    await state.set_state(Form.seat)

# Обработка информации о зале
@dp.callback_query(F.data == "hall_info")
async def hall_info(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    hall_name = data['hall']
    hall_config = HALLS_CONFIG.get(hall_name, HALLS_CONFIG["Зал 1"])
    
    info_text = (
        f"ℹ️ <b>Информация о зале {hall_name}:</b>\n\n"
        f"{hall_config['emoji']} {hall_config['description']}\n"
        f"🔢 Всего мест: {hall_config['seats_count']}\n"
    )
    
    if hall_config.get("is_vip", False):
        info_text += (
            "\n🌟 <b>VIP-услуги:</b>\n"
            "• Мягкие диваны вместо кресел\n"
            "• Персональный сервис\n"
            "• Бесплатные напитки и закуски\n"
        )
    
    await callback.answer(info_text, show_alert=True)

# Обработка выбора места
@dp.callback_query(F.data.startswith("seat_"), Form.seat)
async def select_seat(callback: types.CallbackQuery, state: FSMContext):
    if callback.data.startswith("seat_taken_"):
        await callback.answer("❌ Это место уже занято! Выберите другое.", show_alert=True)
        return
    
    seat_number = int(callback.data.split("_")[1])
    data = await state.get_data()
    hall_name = data['hall']
    
    booked_seats = get_booked_seats(data['movie_title'], data['show_date'])
    if seat_number in booked_seats:
        await callback.message.edit_reply_markup(
            reply_markup=generate_seats_keyboard(data['movie_title'], data['show_date'], hall_name)
        )
        await callback.answer("❌ Это место только что заняли! Выберите другое.", show_alert=True)
        return
    
    save_booking(
        user_id=callback.from_user.id,
        full_name=data['full_name'],
        phone=data['phone'],
        movie_title=data['movie_title'],
        show_date=data['show_date'],
        ticket_price=data['ticket_price'],
        hall=hall_name,
        seat_number=seat_number
    )
    
    hall_config = HALLS_CONFIG.get(hall_name, HALLS_CONFIG["Зал 1"])
    is_vip = hall_config.get("is_vip", False)
    
    confirmation = (
        f"✅ <b>{'VIP-' if is_vip else ''}Бронирование успешно завершено!</b>\n\n"
        f"<b>Ваши данные:</b>\n"
        f"👤 ФИО: {data['full_name']}\n"
        f"📱 Телефон: {data['phone']}\n\n"
        f"<b>Информация о сеансе:</b>\n"
        f"🎬 Фильм: {data['movie_title']}\n"
        f"📅 Дата и время: {data['show_date']}\n"
        f"💵 Стоимость билета: {data['ticket_price']}₽\n"
        f"🏛 Зал: {hall_name} {hall_config['emoji']}\n"
        f"{'🛋️' if is_vip else '💺'} Место: {seat_number}\n\n"
    )
    
    if is_vip:
        confirmation += (
            "🌟 <b>VIP-услуги включены:</b>\n"
            "- Доступ в VIP-лаунж\n"
            "- Приветственный напиток\n"
            "- Плед и дополнительные подушки\n\n"
        )
    
    confirmation += "Спасибо за бронирование! Приятного просмотра!"
    
    await callback.message.answer(confirmation, reply_markup=main_keyboard)
    await state.clear()
    await callback.answer()

# Обработка кнопки "О нас"
@dp.message(Command("about_us"))
@dp.message(F.text.lower() == "о нас")
async def about_us(message: types.Message):
    about_text = (
        f"🌟 <b>{CINEMA_NAME} — больше чем просто кинотеатр</b> 🌟\n\n"
        "🎥 Основанный в 2010 году, наш кинотеатр стал культурным центром города, "
        "где каждый может насладиться лучшими фильмами в неповторимой атмосфере.\n\n"
        "🏆 <b>Наши достижения:</b>\n"
        "• Лучший кинотеатр города 2022-2023\n"
        "• Обладатель премии «Золотой экран» за качество обслуживания\n"
        "• Первый в регионе кинотеатр с системой Dolby Atmos\n\n"
        "💫 <b>Наши залы:</b>\n"
    )
    
    # Добавляем информацию о каждом зале
    for hall_name, config in HALLS_CONFIG.items():
        about_text += (
            f"{config['emoji']} <b>{hall_name}</b>: {config['description']}\n"
            f"🔢 Вместимость: {config['seats_count']} {'диванов' if config.get('is_vip', False) else 'мест'}\n\n"
        )
    
    about_text += (
        "Мы создаем не просто просмотр фильмов, а незабываемые впечатления!"
    )
    
    await message.answer(about_text)

# Запуск бота
async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
