from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
import os


# -----------------------------
# تنظیمات اولیه
# -----------------------------

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY")

CORS(app, supports_credentials=True)


# -----------------------------
# اتصال به EpicAI API
# -----------------------------

client = OpenAI(
    api_key=os.getenv("GAPGPT_API_KEY"),
    base_url="https://api.gapgpt.app/v1"
)


# -----------------------------
# اتصال دیتابیس
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

        print("Database connected.")
        print("Users table ready.")

    except Exception as e:
        print("Database Error:", e)


# -----------------------------
# صفحه اصلی
# -----------------------------

@app.route("/")
def index():
    return render_template("index.html")


# -----------------------------
# ثبت نام
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
                "message": "رمز عبور حداقل ۶ کاراکتر باشد."
            }), 400


        conn = get_db_connection()
        cur = conn.cursor()


        cur.execute(
            "SELECT id FROM users WHERE email=%s",
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
            INSERT INTO users(email, password_hash)
            VALUES(%s,%s)
            RETURNING id
            """,
            (email, password_hash)
        )


        user_id = cur.fetchone()[0]

        conn.commit()

        cur.close()
        conn.close()


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
# ورود
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
            WHERE email=%s
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
# خروج
# -----------------------------

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
# چت EpicAI
# -----------------------------

@app.route("/chat", methods=["POST"])
def chat():

    try:

        data = request.get_json() or {}

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
                    "content":
                    "تو دستیار هوش مصنوعی EpicAI.ir هستی. "
                    "فارسی، دوستانه، دقیق و مفید پاسخ بده."
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

        print("EpicAI API Error:", e)

        return jsonify({

            "reply": "❌ خطا در ارتباط با هوش مصنوعی."

        }), 500


# -----------------------------
# ساخت دیتابیس هنگام اجرا
# -----------------------------

init_db()



# -----------------------------
# اجرای برنامه
# -----------------------------

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
        
