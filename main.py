import json
import sqlite3
from datetime import date, timedelta

from flask import Flask, request

import vk_api
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.utils import get_random_id

# ==========================
# НАСТРОЙКИ
# ==========================

TOKEN = "vk1.a.f13iBuWgfpa-ZlPU3V8pV2hzd-npoaeoKf0ED6VHX0aemJED2cx3RYHMDw3_oCiRQd0FvIHdeMnosmMfZ-_GDQKXv86CpctFQPDd2mM4hB7uAgLi3lj-xK3p4xJGZDnsGQaeKtwODiNy0k4dqLo5VSpZy03WhNcSrE7XWhYXMcRzV4LArfbyc5IXCfFso6zPb5JEkJJioqdBmesCqN6vLg"

GROUP_ID = 240294205

MASTER_ID = 553405223

CONFIRMATION_TOKEN = "553405223"

SECRET_KEY = "nails48Lena"

# ==========================
# VK
# ==========================

vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()

# ==========================
# БАЗА
# ==========================

db = sqlite3.connect("appointments.db", check_same_thread=False)

cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS appointments(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE,
    day TEXT,
    time TEXT
)
""")

db.commit()

# ==========================
# ПАМЯТЬ
# ==========================

user_state = {}

# ==========================
# FLASK
# ==========================

app = Flask(__name__)

# ==========================
# КЛАВИАТУРЫ
# ==========================

def start_keyboard():

    keyboard = VkKeyboard(one_time=False)

    keyboard.add_button(
        "Старт",
        color=VkKeyboardColor.POSITIVE
    )

    return keyboard.get_keyboard()


def days_keyboard():

    keyboard = VkKeyboard(one_time=False)

    # Показываем календарь на 21 день вперёд
    today = date.today()

    for i in range(21):
        d = today + timedelta(days=i)

        keyboard.add_button(
            d.strftime("%d.%m.%Y"),
            color=VkKeyboardColor.PRIMARY
        )

        if (i + 1) % 3 == 0 and i != 20:
            keyboard.add_line()

    return keyboard.get_keyboard()


def time_keyboard(day):

    keyboard = VkKeyboard(one_time=False)

    if day == "Понедельник":
        times = ["10:00", "13:00", "16:00"]
    else:
        times = ["19:00"]

    free_slots = []

    for t in times:

        cursor.execute(
            "SELECT * FROM appointments WHERE day=? AND time=?",
            (day, t)
        )

        if not cursor.fetchone():
            free_slots.append(t)

    if not free_slots:

        keyboard.add_button(
            "Нет свободного времени",
            color=VkKeyboardColor.SECONDARY
        )

    else:

        for i, t in enumerate(free_slots):

            keyboard.add_button(
                t,
                color=VkKeyboardColor.POSITIVE
            )

            if i < len(free_slots) - 1:
                keyboard.add_line()

    return keyboard.get_keyboard()


def confirm_keyboard():

    keyboard = VkKeyboard(one_time=True)

    keyboard.add_button(
        "Подтвердить запись",
        color=VkKeyboardColor.POSITIVE
    )

    return keyboard.get_keyboard()


def cancel_keyboard():

    keyboard = VkKeyboard(one_time=False)

    keyboard.add_button(
        "Отменить запись",
        color=VkKeyboardColor.NEGATIVE
    )

    return keyboard.get_keyboard()

# ==========================
# ОТПРАВКА
# ==========================

def send_message(user_id, message, keyboard=None):

    vk.messages.send(
        user_id=user_id,
        random_id=get_random_id(),
        message=message,
        keyboard=keyboard
    )


# ==========================
# УВЕДОМЛЕНИЕ МАСТЕРУ
# ==========================

def notify_master_new(user_id, day, time):

    user = vk.users.get(user_ids=user_id)[0]

    text = (
        f"📌 Новая запись\n\n"
        f"Клиент: {user['first_name']} {user['last_name']}\n"
        f"ID: {user_id}\n\n"
        f"День: {day}\n"
        f"Время: {time}"
    )

    send_message(MASTER_ID, text)


def notify_master_cancel(user_id, day, time):

    user = vk.users.get(user_ids=user_id)[0]

    text = (
        f"❌ Отмена записи\n\n"
        f"Клиент: {user['first_name']} {user['last_name']}\n"
        f"ID: {user_id}\n\n"
        f"День: {day}\n"
        f"Время: {time}"
    )

    send_message(MASTER_ID, text)

# ==========================
# ЛОГИКА
# ==========================

def handle_message(user_id, text):

    text = text.strip()

    if text.lower() in ["начать", "старт", "start"]:

        send_message(
            user_id,
            "Здравствуйте! 👋\n\nНа какой день хотите записаться?",
            days_keyboard()
        )

        return

    if len(text) == 10 and text.count(".") == 2:

        user_state[user_id] = {
            "day": text
        }

        send_message(
            user_id,
            f"Вы выбрали: {text}\n\nВыберите время:",
            time_keyboard(text)
        )

        return

    if ":" in text:

        if user_id not in user_state:
            return

        user_state[user_id]["time"] = text

        send_message(
            user_id,
            f"День: {user_state[user_id]['day']}\n"
            f"Время: {text}\n\n"
            f"Подтвердить запись?",
            confirm_keyboard()
        )

        return

    if text == "Подтвердить запись":

        if user_id not in user_state:
            return

        day = user_state[user_id]["day"]
        time = user_state[user_id]["time"]

        cursor.execute(
            "SELECT * FROM appointments WHERE day=? AND time=?",
            (day, time)
        )

        if cursor.fetchone():

            send_message(
                user_id,
                "К сожалению, это время уже занято."
            )

            return

        cursor.execute(
            """
            INSERT OR REPLACE INTO appointments
            (user_id, day, time)
            VALUES (?, ?, ?)
            """,
            (user_id, day, time)
        )

        db.commit()

        notify_master_new(
            user_id,
            day,
            time
        )

        send_message(
            user_id,
            "✅ Вы успешно записаны.",
            cancel_keyboard()
        )

        return

    if text == "Отменить запись":

        cursor.execute(
            """
            SELECT day,time
            FROM appointments
            WHERE user_id=?
            """,
            (user_id,)
        )

        row = cursor.fetchone()

        if not row:

            send_message(
                user_id,
                "У вас нет активной записи."
            )

            return

        day, time = row

        cursor.execute(
            """
            DELETE FROM appointments
            WHERE user_id=?
            """,
            (user_id,)
        )

        db.commit()

        notify_master_cancel(
            user_id,
            day,
            time
        )

        send_message(
            user_id,
            "Запись успешно отменена.",
            start_keyboard()
        )

# ==========================
# CALLBACK API
# ==========================

@app.route("/", methods=["POST"])

def callback():

    data = request.json

    if data["type"] == "confirmation":
        return CONFIRMATION_TOKEN

    if data.get("secret") != SECRET_KEY:
        return "ok"

    if data["type"] == "message_new":

        message = data["object"]["message"]

        user_id = message["from_id"]

        text = message.get("text", "")

        handle_message(
            user_id,
            text
        )

        return "ok"

    return "ok"


@app.route("/", methods=["GET"])
def index():
    return "VK Bot is running"


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=10000
    )
