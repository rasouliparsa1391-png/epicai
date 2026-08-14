from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta
import psycopg2
import os

load_dotenv()

app = Flask(__name__)

# Session settings
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret-key")
app.permanent_session_lifetime = timedelta(days=30)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax"
)

CORS(app, supports_credentials=True)

# EpicAI / GapGPT API
client = OpenAI(
    api_key=os.getenv("GAPGPT_API_KEY"),
    base_url="https://api.gapgpt.app/v1"
)


# -----------------------------
# Database
# -----------------------------

def get_db_connection():
    return psycopg2.connect(
        os.getenv("DATABASE_URL"),
        sslmode="require"
    )


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

        cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role VARCHAR(20) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_user_id
            ON messages(user_id)
        """)

        conn.commit()
        cur.close()
        conn.close()

        print("Database connected.")
        print("Users table ready.")
        print("Messages table ready.")

    except Exception as e:
        print("Database Error:", e)


# -----------------------------
# Main page
# -----------------------------

@app.route("/")
def index():
    return render_template("index.html")


# -----------------------------
# Register
# -----------------------------

@app.route("/register", methods=["POST"])
def register():
    try:
        data = request.get_json() or {}

        email = data.get("email", "").strip().lower()
        password = data.get("password", "")

        if not email or not password:
            return jsonify({
                "success": False,
                "message": "ایمیل و رمز عبور را وارد کنید."
            }), 400

        if len(password) < 6:
            return jsonify({
                "success": False,
                "message": "رمز عبور باید حداقل ۶ کاراکتر باشد."
            }), 400

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            "SELECT id FROM users WHERE email = %s",
            (email,)
        )

        if cur.fetchone():
            cur.close()
            conn.close()

            return jsonify({
                "success": False,
                "message": "این ایمیل قبلاً ثبت شده است."
            }), 409

        password_hash = generate_password_hash(password)

        cur.execute(
            """
            INSERT INTO users (email, password_hash)
            VALUES (%s, %s)
            RETURNING id
            """,
            (email, password_hash)
        )

        user_id = cur.fetchone()[0]

        conn.commit()
        cur.close()
        conn.close()

        session.permanent = True
        session["user_id"] = user_id
        session["email"] = email

        return jsonify({
            "success": True,
            "message": "ثبت نام موفق بود.",
            "user": {
                "id": user_id,
                "email": email
            }
        })

    except Exception as e:
        print("Register Error:", e)

        return jsonify({
            "success": False,
            "message": "خطا در ثبت نام."
        }), 500


# -----------------------------
# Login
# -----------------------------

@app.route("/login", methods=["POST"])
def login():
    try:
        data = request.get_json() or {}

        email = data.get("email", "").strip().lower()
        password = data.get("password", "")

        if not email or not password:
            return jsonify({
                "success": False,
                "message": "ایمیل و رمز عبور را وارد کنید."
            }), 400

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, email, password_hash
            FROM users
            WHERE email = %s
            """,
            (email,)
        )

        user = cur.fetchone()

        cur.close()
        conn.close()

        if not user:
            return jsonify({
                "success": False,
                "message": "ایمیل یا رمز عبور اشتباه است."
            }), 401

        user_id, user_email, password_hash = user

        if not check_password_hash(password_hash, password):
            return jsonify({
                "success": False,
                "message": "ایمیل یا رمز عبور اشتباه است."
            }), 401

        session.permanent = True
        session["user_id"] = user_id
        session["email"] = user_email

        return jsonify({
            "success": True,
            "message": "ورود موفق بود.",
            "user": {
                "id": user_id,
                "email": user_email
            }
        })

    except Exception as e:
        print("Login Error:", e)

        return jsonify({
            "success": False,
            "message": "خطا در ورود."
        }), 500


# -----------------------------
# Logout
# -----------------------------

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()

    return jsonify({
        "success": True,
        "message": "با موفقیت خارج شدید."
    })


# -----------------------------
# Check login
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
# Chat history
# -----------------------------

@app.route("/history", methods=["GET"])
def history():
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "message": "ابتدا وارد حساب شوید."
        }), 401

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT role, content
            FROM messages
            WHERE user_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            (session["user_id"],)
        )

        rows = cur.fetchall()

        cur.close()
        conn.close()

        return jsonify({
            "success": True,
            "messages": [
                {
                    "role": role,
                    "content": content
                }
                for role, content in rows
            ]
        })

    except Exception as e:
        print("History Error:", e)

        return jsonify({
            "success": False,
            "message": "خطا در دریافت تاریخچه چت."
        }), 500


# -----------------------------
# EpicAI Chat
# -----------------------------

@app.route("/chat", methods=["POST"])
def chat():
    if "user_id" not in session:
        return jsonify({
            "reply": "🔐 برای استفاده از EpicAI ابتدا وارد حساب شوید."
        }), 401

    try:
        data = request.get_json() or {}
        user_message = data.get("message", "").strip()

        if not user_message:
            return jsonify({
                "reply": "لطفاً یک پیام بنویس."
            }), 400

        conn = get_db_connection()
        cur = conn.cursor()

        # Save user message
        cur.execute(
            """
            INSERT INTO messages (user_id, role, content)
            VALUES (%s, %s, %s)
            """,
            (session["user_id"], "user", user_message)
        )
        conn.commit()

        # Load recent conversation
        cur.execute(
            """
            SELECT role, content
            FROM messages
            WHERE user_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 30
            """,
            (session["user_id"],)
        )

        rows = cur.fetchall()
        cur.close()
        conn.close()

        rows.reverse()

        messages = [
            {
                "role": "system",
                "content": (
                    "تو دستیار هوش مصنوعی EpicAI.ir هستی. "
                    "فارسی، دوستانه، دقیق و مفید پاسخ بده."
                )
            }
        ]

        messages.extend([
            {
                "role": role,
                "content": content
            }
            for role, content in rows
        ])

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )

        answer = response.choices[0].message.content

        # Save AI response
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO messages (user_id, role, content)
            VALUES (%s, %s, %s)
            """,
            (session["user_id"], "assistant", answer)
        )

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            "reply": answer
        })

    except Exception as e:
        print("EpicAI API Error:", e)

        return jsonify({
            "reply": "❌ خطا در ارتباط با هوش مصنوعی."
        }), 500


# Create database tables on startup
init_db()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
