from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI
import psycopg2
import os

# بارگذاری متغیرهای محیطی
load_dotenv()

app = Flask(name)
CORS(app)

# -----------------------------
# اتصال به GapGPT
# -----------------------------
client = OpenAI(
    api_key=os.getenv("GAPGPT_API_KEY"),
    base_url="https://api.gapgpt.app/v1"
)


# -----------------------------
# اتصال به دیتابیس Supabase
# -----------------------------
def get_db_connection():
    return psycopg2.connect(
        os.getenv("DATABASE_URL"),
        sslmode="require"
    )


# -----------------------------
# ساخت جدول کاربران
# -----------------------------
def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        cur.close()
        conn.close()

        print("Database connected successfully.")
        print("Users table is ready.")

    except Exception as e:
        print("Database Error:", e)


# -----------------------------
# صفحه اصلی
# -----------------------------
@app.route("/")
def index():
    return render_template("index.html")


# -----------------------------
# تست چت
# -----------------------------
@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        user_message = data.get("message", "").strip()

        if not user_message:
            return jsonify({"reply": "لطفاً یک پیام بنویس."}), 400

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "تو دستیار هوش مصنوعی EpicAI.ir هستی. فارسی، دوستانه و مفید پاسخ بده."
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ]
        )

        answer = response.choices[0].message.content

        return jsonify({"reply": answer})

    except Exception as e:
        print("GapGPT API Error:", e)
        return jsonify({
            "reply": f"❌ خطا در ارتباط با هوش مصنوعی: {str(e)}"
        }), 500


# -----------------------------
# اجرای برنامه
# -----------------------------
if name == "main":
    init_db()

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
