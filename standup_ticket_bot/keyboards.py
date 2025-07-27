# keyboards.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Текст на кнопках
BTN_ALL = "Все концерты"
BTN_21 = "Ближайшие 21 день"
BTN_7 = "Ближайшие 7 дней"
BTN_3 = "Ближайшие 3 дня"

# Собираем клавиатуру
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_ALL)],
        [KeyboardButton(text=BTN_21)],
        [KeyboardButton(text=BTN_7)],
        [KeyboardButton(text=BTN_3)],
    ],
    resize_keyboard=True,  # чтобы подогналась под экран
    one_time_keyboard=False
)
