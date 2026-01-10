import os
import uuid
import sqlite3
from flask import Flask, request, jsonify, send_file, render_template_string

# === Настройки путей ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'instance', 'shop.db')
FILES_DIR = os.path.join(BASE_DIR, 'static', 'files')

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(FILES_DIR, exist_ok=True)

app = Flask(__name__)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS digital_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT CHECK(type IN ('pdf', 'key')) NOT NULL,
                file_path TEXT,          -- для PDF
                key_value TEXT,          -- для ключа
                instruction TEXT         -- инструкция для покупателя
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS issued_tokens (
                token TEXT PRIMARY KEY,
                item_id INTEGER,
                used BOOLEAN DEFAULT 0,
                FOREIGN KEY(item_id) REFERENCES digital_items(id)
            )
        """)

init_db()

# === Главная страница: управление товарами ===
@app.route('/')
def dashboard():
    with get_db() as conn:
        items = conn.execute("SELECT * FROM digital_items ORDER BY id DESC").fetchall()
    return render_template_string("""
    <!doctype html>
    <title>Цифровой магазин</title>
    <h2>📦 Управление товарами</h2>
    
    <h3>➕ Добавить PDF</h3>
    <form method=post enctype=multipart/form-data action="/add_pdf">
      Название: <input name="name" required><br>
      Инструкция: <textarea name="instruction" placeholder="Что делать после скачивания?"></textarea><br>
      Файл (PDF): <input type=file name=file required><br>
      <button type=submit>Загрузить PDF</button>
    </form>
    
    <h3>➕ Добавить ключ активации</h3>
    <form method=post action="/add_key">
      Название: <input name="name" required><br>
      Ключ: <input name="key_value" required><br>
      Инструкция: <textarea name="instruction" placeholder="Как активировать?"></textarea><br>
      <button type=submit>Сохранить ключ</button>
    </form>

    <hr>
    <h3>📋 Ваши товары</h3>
    <table border=1 cellpadding=5>
      <tr><th>ID</th><th>Название</th><th>Тип</th><th>Действие</th></tr>
      {% for item in items %}
      <tr>
        <td>{{ item.id }}</td>
        <td>{{ item.name }}</td>
        <td>{{ item.type }}</td>
        <td>
          {% if item.type == 'pdf' %}
            <a href="/get_link/{{ item.id }}" target="_blank">Получить ссылку</a>
          {% else %}
            <code>{{ item.key_value }}</code> (выдаётся при заказе)
          {% endif %}
        </td>
      </tr>
      {% endfor %}
    </table>
    """, items=items)

# === Добавить PDF ===
@app.route('/add_pdf', methods=['POST'])
def add_pdf():
    name = request.form['name']
    instruction = request.form.get('instruction', '')
    file = request.files['file']
    if not file.filename.lower().endswith('.pdf'):
        return "Только PDF!", 400
    filename = str(uuid.uuid4()) + ".pdf"
    filepath = os.path.join(FILES_DIR, filename)
    file.save(filepath)
    with get_db() as conn:
        conn.execute(
            "INSERT INTO digital_items (name, type, file_path, instruction) VALUES (?, ?, ?, ?)",
            (name, 'pdf', filepath, instruction)
        )
    return "<script>alert('PDF добавлен!'); window.location='/'</script>"

# === Добавить ключ ===
@app.route('/add_key', methods=['POST'])
def add_key():
    name = request.form['name']
    key_value = request.form['key_value']
    instruction = request.form.get('instruction', '')
    with get_db() as conn:
        conn.execute(
            "INSERT INTO digital_items (name, type, key_value, instruction) VALUES (?, ?, ?, ?)",
            (name, 'key', key_value, instruction)
        )
    return "<script>alert('Ключ добавлен!'); window.location='/'</script>"

# === Получить одноразовую ссылку на PDF ===
@app.route('/get_link/<int:item_id>')
def get_link(item_id):
    with get_db() as conn:
        item = conn.execute("SELECT * FROM digital_items WHERE id = ?", (item_id,)).fetchone()
    if not item or item['type'] != 'pdf':
        return "Товар не найден", 404
    token = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            "INSERT INTO issued_tokens (token, item_id) VALUES (?, ?)",
            (token, item_id)
        )
    link = f"{request.url_root}download?token={token}"
    return f"""
    <h3>✅ Ссылка готова!</h3>
    <p><strong>Скопируйте:</strong></p>
    <input type="text" value="{link}" size="80" onclick="this.select()" readonly>
    <p style="color:#666;">Инструкция: {item['instruction'] or '—'}</p>
    <br><a href="/">← Назад</a>
    """

# === Выдача файла по токену (одноразово) ===
@app.route('/download')
def download():
    token = request.args.get('token')
    if not token:
        return "Токен не указан", 400
    with get_db() as conn:
        row = conn.execute("""
            SELECT i.file_path, i.instruction, t.used
            FROM issued_tokens t
            JOIN digital_items i ON t.item_id = i.id
            WHERE t.token = ?
        """, (token,)).fetchone()
        if not row:
            return "Ссылка не найдена", 404
        if row['used']:
            return "Ссылка уже использована", 410
        conn.execute("UPDATE issued_tokens SET used = 1 WHERE token = ?", (token,))
        filepath = row['file_path']
    if not os.path.exists(filepath):
        return "Файл удалён", 404
    return send_file(filepath, as_attachment=True)

# === API для Яндекс Маркета: выдать цифровой товар по item_id ===
@app.route('/api/deliver/<int:item_id>')
def api_deliver(item_id):
    with get_db() as conn:
        item = conn.execute("SELECT * FROM digital_items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        return jsonify({"error": "Товар не найден"}), 404

    if item['type'] == 'pdf':
        token = str(uuid.uuid4())
        with get_db() as conn:
            conn.execute("INSERT INTO issued_tokens (token, item_id) VALUES (?, ?)", (token, item_id))
        code = f"{request.url_root}download?token={token}"
    else:  # key
        code = item['key_value']

    return jsonify({
        "code": code,
        "description": item['instruction'] or "Ваш цифровой товар"
    })

# === Health check ===
@app.route('/health')
def health():
    return "OK", 200

if __name__ == '__main__':
    app.run(debug=True)