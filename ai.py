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
        
