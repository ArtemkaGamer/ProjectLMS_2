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
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import re
from datetime import datetime

API_TOKEN = '7744367169:AAE_CnE7Y53k2Ib1gW_U8Bm5L9VGQj7AtnQ'
CINEMA_NAME = "🌟 Stellar Cinema"
WELCOME_STICKER = "CAACAgIAAxkBAAEBPKpoDhwKOhYtFehUUKr2NQ2XDAOVWwACRwADWbv8JVyd1qxN32EsNgQ"
MOVIES_PER_PAGE = 5
FILMRU_BASE_URL = "https://www.film.ru"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

HALLS_CONFIG = {
    "Зал 1": {
        "seats_count": 25,
        "seats_per_row": 5,
        "description": "Стандартный зал с удобными креслами",
        "emoji": "🪑"
    },
    "Зал 2": {
        "seats_count": 20,
        "seats_per_row": 5,
        "description": "Зал с улучшенной акустикой",
        "emoji": "🎧"
    },
    "Зал 3": {
        "seats_count": 15,
        "seats_per_row": 5,
        "description": "Малый зал для камерных показов",
        "emoji": "🎬"
    },
    "VIP Зал": {
        "seats_count": 10,
        "seats_per_row": 2,
        "description": "Премиум зал с диванами и сервисом",
        "emoji": "🛋️",
        "is_vip": True
    }
}

class Form(StatesGroup):
    movie = State()
    full_name = State()
    phone = State()
    seat = State()

def init_db():
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS movies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        show_date TEXT NOT NULL,
        ticket_price INTEGER NOT NULL,
        hall TEXT NOT NULL,
        filmru_url TEXT,
        genres TEXT
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
            ("Аватар", "2024-01-20 18:00", 350, "Зал 1", "/movies/avatar", "фантастика, боевик, приключения"),
            ("Интерстеллар", "2024-01-20 21:00", 300, "Зал 2", "/movies/interstellar", "фантастика, драма, приключения"),
            ("Дюна", "2024-01-21 15:00", 400, "Зал 3", "/movies/duna", "фантастика, драма"),
            ("Оппенгеймер", "2024-01-21 20:00", 500, "VIP Зал", "/movies/oppenheimer", "биография, драма, история"),
        ]
        cursor.executemany(
            "INSERT INTO movies (title, show_date, ticket_price, hall, filmru_url, genres) VALUES (?, ?, ?, ?, ?, ?)", 
            test_movies
        )
    
    conn.commit()
    conn.close()

init_db()

async def get_movie_info_from_filmru(path):
    try:
        url = f"{FILMRU_BASE_URL}{path}"
        ua = UserAgent()
        headers = {
            'User-Agent': ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            'Referer': FILMRU_BASE_URL
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'lxml')
        
        title = soup.find('h2')
        title = title.get_text(strip=True) if title else "Название не найдено"
        
        rating = ""
        rating_block = soup.find('a', class_='wrapper_movies_scores_score')
        if rating_block:
            rating_text = rating_block.get_text(strip=True)
            rating_match = re.search(r'[\d\.]+', rating_text)
            rating = rating_match.group(0) if rating_match else "Рейтинг не указан"
        else:
            rating = "Рейтинг не указан"
        
        meta_block = soup.find('h1')
        year = ""
        if meta_block:
            year_tag = meta_block.find('span')
            year = year_tag.get_text(strip=True) if year_tag else ""
        
        description = soup.find('div', class_='wrapper_movies_text')
        if not description:
            description = soup.find('p', itemprop='description')
        description = description.get_text(" ", strip=True) if description else "Описание отсутствует"
        
        actors = []
        crew_block = soup.find('div', class_='wrapper_movies_crew')
        if not crew_block:
            return actors
        
        actor_elements = crew_block.find_all('a', href=lambda x: x and '/person/' in x)
        
        for actor_element in actor_elements:
            name_tag = actor_element.find('strong')
            if name_tag:
                actor_name = name_tag.get_text(strip=True)
                actors.append(actor_name)

        return {
            'title': title,
            'rating': rating,
            'year': year,
            'description': description,
            'actors': ', '.join(actors) if actors else "Актеры не указаны",
            'url': url
        }
    except Exception as e:
        logger.error(f"Ошибка парсинга Film.ru: {str(e)}")
        return None

def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Расписание"), KeyboardButton(text="Забронировать")],
            [KeyboardButton(text="Личный кабинет"), KeyboardButton(text="О нас")]
        ],
        resize_keyboard=True
    )

def generate_movies_keyboard(page=1):
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute("SELECT title, show_date, ticket_price, hall FROM movies ORDER BY show_date")
    movies = cursor.fetchall()
    conn.close()
    
    total_pages = (len(movies) + MOVIES_PER_PAGE - 1) // MOVIES_PER_PAGE
    start = (page - 1) * MOVIES_PER_PAGE
    end = start + MOVIES_PER_PAGE
    page_movies = movies[start:end]
    
    keyboard = []
    for title, date, price, hall in page_movies:
        hall_emoji = HALLS_CONFIG.get(hall, {}).get("emoji", "🎬")
        keyboard.append([
            InlineKeyboardButton(
                text=f"{hall_emoji} {title} ({date}) - {price}₽",
                callback_data=f"movie_{title}_{date}"
            )
        ])
    
    pagination = []
    if page > 1:
        pagination.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"page_{page-1}"))
    if page < total_pages:
        pagination.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"page_{page+1}"))
    
    if pagination:
        keyboard.append(pagination)
    
    keyboard.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def generate_seats_keyboard(movie_title, show_date, hall_name):
    hall_config = HALLS_CONFIG.get(hall_name, HALLS_CONFIG["Зал 1"])
    booked_seats = get_booked_seats(movie_title, show_date)
    keyboard = []
    row_buttons = []
    
    for seat in range(1, hall_config["seats_count"] + 1):
        if seat in booked_seats:
            emoji = "❌"
        else:
            emoji = "💺" if not hall_config.get("is_vip", False) else "🛋️"
            
        row_buttons.append(InlineKeyboardButton(
            text=f"{emoji} {seat}",
            callback_data=f"seat_taken_{seat}" if seat in booked_seats else f"seat_{seat}"
        ))
        
        if seat % hall_config["seats_per_row"] == 0 or seat == hall_config["seats_count"]:
            keyboard.append(row_buttons)
            row_buttons = []
    
    info_button = InlineKeyboardButton(
        text=f"ℹ️ {hall_name}: {hall_config['description']}",
        callback_data="hall_info"
    )
    keyboard.append([info_button])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

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

def get_movie_info(title, date):
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute("""
    SELECT title, show_date, ticket_price, hall, filmru_url, genres 
    FROM movies WHERE title = ? AND show_date = ?
    """, (title, date))
    movie = cursor.fetchone()
    conn.close()
    return movie

def save_booking(user_id, full_name, phone, movie_title, show_date, ticket_price, hall, seat_number):
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO bookings (user_id, full_name, phone, movie_title, show_date, ticket_price, hall, seat_number)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, full_name, phone, movie_title, show_date, ticket_price, hall, seat_number))
    conn.commit()
    conn.close()

def delete_booking(booking_id):
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
    conn.commit()
    conn.close()

def get_user_bookings(user_id):
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, movie_title, show_date, ticket_price, hall, seat_number 
    FROM bookings WHERE user_id = ? ORDER BY show_date
    """, (user_id,))
    bookings = cursor.fetchall()
    conn.close()
    return bookings

def get_user_active_bookings(user_id):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, movie_title, show_date, ticket_price, hall, seat_number 
    FROM bookings WHERE user_id = ? AND show_date > ? ORDER BY show_date
    """, (user_id, now))
    bookings = cursor.fetchall()
    conn.close()
    return bookings

def generate_bookings_keyboard(bookings, is_active=False):
    keyboard = []
    for booking in bookings:
        booking_id, title, date, price, hall, seat = booking
        text = f"🎬 {title} ({date}) - {hall}, место {seat}"
        if is_active:
            keyboard.append([
                InlineKeyboardButton(text=text, callback_data=f"booking_info_{booking_id}"),
                InlineKeyboardButton(text="❌ Удалить", callback_data=f"delete_booking_{booking_id}")
            ])
        else:
            keyboard.append([InlineKeyboardButton(text=text, callback_data=f"booking_info_{booking_id}")])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="personal_account")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer_sticker(WELCOME_STICKER)
    await message.answer(
        f"✨ Добро пожаловать в {CINEMA_NAME} — место, где оживают мечты! ✨\n\n"
        "🎬 Мы предлагаем вам уникальный киноопыт с лучшими фильмами в потрясающем качестве.\n"
        "💫 Современные залы с Dolby Atmos, удобные кресла и неповторимая атмосфера.\n\n"
        "Выберите действие:",
        reply_markup=main_keyboard()
    )

@dp.message(Command("restart"))
async def cmd_restart(message: types.Message):
    await message.answer("🔄 Сброс настроек.", reply_markup=main_keyboard())

@dp.message(F.text.lower() == "расписание")
async def show_schedule(message: types.Message):
    await message.answer("🎬 Расписание фильмов:", reply_markup=generate_movies_keyboard(1))

@dp.message(F.text.lower() == "личный кабинет")
async def personal_account(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📜 История заказов", callback_data="booking_history"),
            InlineKeyboardButton(text="🎟 Актуальные заказы", callback_data="active_bookings")
        ],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
    ])
    await message.answer("Личный кабинет:", reply_markup=keyboard)

@dp.callback_query(F.data == "personal_account")
async def back_to_personal_account(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📜 История заказов", callback_data="booking_history"),
            InlineKeyboardButton(text="🎟 Актуальные заказы", callback_data="active_bookings")
        ],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
    ])
    await callback.message.edit_text("Личный кабинет:", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "booking_history")
async def show_booking_history(callback: types.CallbackQuery):
    bookings = get_user_bookings(callback.from_user.id)
    if not bookings:
        await callback.message.edit_text("У вас пока нет истории заказов.", reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="personal_account")]]
        ))
    else:
        await callback.message.edit_text("📜 История ваших заказов:", 
            reply_markup=generate_bookings_keyboard(bookings))
    await callback.answer()

@dp.callback_query(F.data == "active_bookings")
async def show_active_bookings(callback: types.CallbackQuery):
    bookings = get_user_active_bookings(callback.from_user.id)
    if not bookings:
        await callback.message.edit_text("У вас нет активных заказов.", reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="personal_account")]]
        ))
    else:
        await callback.message.edit_text("🎟 Ваши активные заказы:", 
            reply_markup=generate_bookings_keyboard(bookings, is_active=True))
    await callback.answer()

@dp.callback_query(F.data.startswith("delete_booking_"))
async def delete_booking_handler(callback: types.CallbackQuery):
    booking_id = int(callback.data.split("_")[2])
    delete_booking(booking_id)
    
    bookings = get_user_active_bookings(callback.from_user.id)
    if not bookings:
        await callback.message.edit_text("Бронирование удалено. У вас нет активных заказов.", 
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="personal_account")]]
            ))
    else:
        await callback.message.edit_text("Бронирование удалено. Ваши активные заказы:", 
            reply_markup=generate_bookings_keyboard(bookings, is_active=True))
    await callback.answer("Бронирование удалено!")

@dp.callback_query(F.data.startswith("booking_info_"))
async def show_booking_info(callback: types.CallbackQuery):
    booking_id = int(callback.data.split("_")[2])
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute("""
    SELECT movie_title, show_date, ticket_price, hall, seat_number, full_name, phone 
    FROM bookings WHERE id = ?
    """, (booking_id,))
    booking = cursor.fetchone()
    conn.close()
    
    if booking:
        title, date, price, hall, seat, name, phone = booking
        message_text = (
            f"🎬 Фильм: <b>{title}</b>\n"
            f"📅 Дата: <b>{date}</b>\n"
            f"🏛 Зал: <b>{hall}</b>\n"
            f"💺 Место: <b>{seat}</b>\n"
            f"💵 Цена: <b>{price}₽</b>\n\n"
            f"👤 ФИО: <b>{name}</b>\n"
            f"📱 Телефон: <b>{phone}</b>"
        )
        
        is_active = datetime.now().strftime("%Y-%m-%d %H:%M") < date
        back_callback = "active_bookings" if is_active else "booking_history"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data=back_callback)]
        ])
        
        await callback.message.edit_text(message_text, reply_markup=keyboard)
    else:
        await callback.message.edit_text("Бронирование не найдено.", reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="personal_account")]]
        ))
    
    await callback.answer()

@dp.callback_query(F.data.startswith("page_"))
async def handle_pagination(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[1])
    await callback.message.edit_reply_markup(reply_markup=generate_movies_keyboard(page))
    await callback.answer()

@dp.callback_query(F.data.startswith("movie_"))
async def show_movie_details(callback: types.CallbackQuery):
    _, title, date = callback.data.split("_", 2)
    movie_info = get_movie_info(title, date)
    
    if not movie_info:
        await callback.answer("❌ Фильм не найден")
        return
    
    movie_details = await get_movie_info_from_filmru(movie_info[4])
    
    if not movie_details:
        await callback.answer("❌ Не удалось получить информацию о фильме")
        return
    
    message_text = (
        f"🎬 Название: <b>{movie_info[0]}</b>\n"
        f"⭐ Рейтинг: <b>{movie_details.get('rating', 'N/A')}</b>\n"
        f"📅 Год: <b>{movie_details.get('year', 'N/A')}</b>\n"
        f"🎭 Жанры: <b>{movie_info[5] if len(movie_info) > 5 and movie_info[5] else 'Не указаны'}</b>\n\n"
        f"<b>Описание:</b>\n{movie_details.get('description', 'Нет описания')}\n\n"
        f"<b>В главных ролях:</b>\n{movie_details.get('actors', 'Актеры не указаны')}\n\n"
        f"🔗 <a href='{FILMRU_BASE_URL}{movie_info[4]}'>Страница на Film.ru</a>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎫 Забронировать", callback_data=f"book_{title}_{date}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="page_1")]
    ])
    
    if movie_details.get('poster_url'):
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=movie_details['poster_url'],
            caption=message_text,
            reply_markup=keyboard
        )
    else:
        await callback.message.edit_text(message_text, reply_markup=keyboard)
    
    await callback.answer()

@dp.callback_query(F.data.startswith("book_"))
async def start_booking_from_inline(callback: types.CallbackQuery, state: FSMContext):
    _, title, date = callback.data.split("_", 2)
    movie_info = get_movie_info(title, date)
    
    if not movie_info:
        await callback.message.answer("❌ Фильм не найден")
        await state.clear()
        return
    
    await state.update_data(
        movie_title=title,
        show_date=date,
        ticket_price=movie_info[2],
        hall=movie_info[3]
    )
    await callback.message.answer("✍️ Введите ваше ФИО:")
    await state.set_state(Form.full_name)
    await callback.answer()

@dp.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("Выберите действие:", reply_markup=None)
    await callback.message.answer("Главное меню:", reply_markup=main_keyboard())
    await callback.answer()

@dp.message(F.text.lower() == "забронировать")
async def start_booking(message: types.Message, state: FSMContext):
    await message.answer("🎟 Выберите фильм:", reply_markup=generate_movies_keyboard(1))
    await state.set_state(Form.movie)

@dp.callback_query(F.data.startswith("book_"), Form.movie)
async def select_movie(callback: types.CallbackQuery, state: FSMContext):
    _, title, date = callback.data.split("_", 2)
    movie_info = get_movie_info(title, date)
    
    if not movie_info:
        await callback.message.answer("❌ Фильм не найден")
        await state.clear()
        return
    
    await state.update_data(
        movie_title=title,
        show_date=date,
        ticket_price=movie_info[2],
        hall=movie_info[3]
    )
    await callback.message.answer("✍️ Введите ваше ФИО:")
    await state.set_state(Form.full_name)
    await callback.answer()

@dp.message(Form.full_name)
async def process_full_name(message: types.Message, state: FSMContext):
    if len(message.text.split()) < 2:
        await message.answer("❌ Введите ФИО полностью (минимум 2 слова)")
        return
    
    await state.update_data(full_name=message.text)
    await message.answer("📱 Введите ваш телефон:")
    await state.set_state(Form.phone)

@dp.message(Form.phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text
    if not phone.replace("+", "").isdigit():
        await message.answer("❌ Введите корректный телефон")
        return
    
    await state.update_data(phone=phone)
    data = await state.get_data()
    hall_name = data['hall']
    hall_config = HALLS_CONFIG.get(hall_name, HALLS_CONFIG["Зал 1"])
    
    seat_type = "диваны 🛋️" if hall_config.get("is_vip", False) else "места 💺"
    await message.answer(
        f"📍 Выберите {seat_type} в зале {hall_name}:",
        reply_markup=generate_seats_keyboard(data['movie_title'], data['show_date'], hall_name)
    )
    await state.set_state(Form.seat)

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

@dp.callback_query(F.data.startswith("seat_"), Form.seat)
async def select_seat(callback: types.CallbackQuery, state: FSMContext):
    if callback.data.startswith("seat_taken_"):
        await callback.answer("❌ Место занято!", show_alert=True)
        return
    
    seat_number = int(callback.data.split("_")[1])
    data = await state.get_data()
    hall_name = data['hall']
    
    booked_seats = get_booked_seats(data['movie_title'], data['show_date'])
    if seat_number in booked_seats:
        await callback.message.edit_reply_markup(
            reply_markup=generate_seats_keyboard(data['movie_title'], data['show_date'], hall_name)
        )
        await callback.answer("❌ Место только что заняли!", show_alert=True)
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
        f"✅ <b>Бронирование завершено!</b>\n\n"
        f"<b>Ваши данные:</b>\n"
        f"👤 ФИО: {data['full_name']}\n"
        f"📱 Телефон: {data['phone']}\n\n"
        f"<b>Сеанс:</b>\n"
        f"🎬 Фильм: {data['movie_title']}\n"
        f"📅 Дата: {data['show_date']}\n"
        f"💵 Цена: {data['ticket_price']}₽\n"
        f"🏛 Зал: {hall_name} {hall_config['emoji']}\n"
        f"{'🛋️' if is_vip else '💺'} Место: {seat_number}\n\n"
    )
    
    if is_vip:
        confirmation += "🌟 <b>Включены VIP-услуги</b>\n"
    
    confirmation += "Спасибо! Приятного просмотра!"
    
    await callback.message.answer(confirmation, reply_markup=main_keyboard())
    await state.clear()
    await callback.answer()

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
    
    for hall_name, config in HALLS_CONFIG.items():
        about_text += (
            f"{config['emoji']} <b>{hall_name}</b>: {config['description']}\n"
            f"🔢 Вместимость: {config['seats_count']} {'диванов' if config.get('is_vip', False) else 'мест'}\n\n"
        )
    
    about_text += "Мы создаем не просто просмотр фильмов, а незабываемые впечатления!"
    await message.answer(about_text)

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())