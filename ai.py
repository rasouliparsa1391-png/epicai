from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
import os

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY", "change-this-secret-key")

CORS(app, supports_credentials=True)
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
# خروج
# -----------------------------
app = Flask(__name__)
@app.route("/logout", methods=["POST"])
def logout():
    session.clear()

    return jsonify({
        "success": True,
        "message": "با موفقیت خارج شدید."
    })


# -----------------------------
# بررسی وضعیت ورود
# -----------------------------
@app.route("/me", methods=["GET"])
def me():
    if "user_id" not in session:
        return jsonify({
            "logged_in": False
        })

    return jsonify({
        "logged_in": True,
        "user": {
            "id": session["user_id"],
            "email": session["email"]
        }
    })


# -----------------------------
# چت هوش مصنوعی
# -----------------------------
@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        user_message = data.get("message", "").strip()

        if not user_message:
            return jsonify({
                "reply": "لطفاً یک پیام بنویس."
            }), 400

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "تو دستیار هوش مصنوعی EpicAI.ir هستی. "
                        "فارسی، دوستانه و مفید پاسخ بده."
                    )
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ]
        )

        answer = response.choices[0].message.content

        return jsonify({
            "reply": answer
        })

    except Exception as e:
        print("GapGPT API Error:", e)

        return jsonify({
            "reply": "❌ خطا در ارتباط با هوش مصنوعی."
        }), 500


# -----------------------------
# اجرای برنامه
# -----------------------------

# برای Gunicorn هم جدول را ایجاد می‌کنیم
init_db()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
