from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta
import psycopg2
import base64
import os
import psycopg2
import uuid
from pathlib import Path

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


# -----------------------------
# Temporary image storage
# -----------------------------
TEMP_IMAGE_DIR = Path(os.getenv("TEMP_IMAGE_DIR", "static/generated"))
TEMP_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

# Images are intentionally NOT stored in PostgreSQL.
# Old temporary files are removed automatically.
IMAGE_MAX_AGE_SECONDS = int(os.getenv("IMAGE_MAX_AGE_SECONDS", "3600"))


def cleanup_old_images():
    """Remove generated images older than IMAGE_MAX_AGE_SECONDS."""
    import time

    now = time.time()
    for file_path in TEMP_IMAGE_DIR.iterdir():
        try:
            if file_path.is_file() and now - file_path.stat().st_mtime > IMAGE_MAX_AGE_SECONDS:
                file_path.unlink(missing_ok=True)
        except Exception as e:
            print("Image cleanup error:", e)

# EpicAI / GapGPT API
client = OpenAI(
    api_key=os.getenv("GAPGPT_API_KEY"),
    base_url="https://api.gapgpt.app/v1"
)
# AvalAI Image API
image_client = OpenAI(
    api_key=os.getenv("AVALAI_API_KEY"),
    base_url="https://api.avalai.ir/v1"
)

IMAGE_MODEL = "gpt-image-1"

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

        # -----------------------------
        # Users
        # -----------------------------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # -----------------------------
        # Chats
        # -----------------------------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL
                    REFERENCES users(id) ON DELETE CASCADE,
                title VARCHAR(255) NOT NULL DEFAULT 'چت جدید',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # -----------------------------
        # Messages
        # -----------------------------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL
                    REFERENCES users(id) ON DELETE CASCADE,
                role VARCHAR(20) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # برای دیتابیس‌های قدیمی
        cur.execute("""
            ALTER TABLE messages
            ADD COLUMN IF NOT EXISTS chat_id INTEGER
        """)

        # Foreign key فقط اگر قبلاً وجود نداشته باشد
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'messages_chat_id_fkey'
                ) THEN
                    ALTER TABLE messages
                    ADD CONSTRAINT messages_chat_id_fkey
                    FOREIGN KEY (chat_id)
                    REFERENCES chats(id)
                    ON DELETE CASCADE;
                END IF;
            END
            $$;
        """)

        # -----------------------------
        # Indexes
        # -----------------------------
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_user_id
            ON messages(user_id)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_chat_id
            ON messages(chat_id)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_chats_user_id
            ON chats(user_id)
        """)

        # -----------------------------
        # انتقال پیام‌های قدیمی
        # -----------------------------
        cur.execute("""
            SELECT DISTINCT user_id
            FROM messages
            WHERE chat_id IS NULL
        """)

        old_users = cur.fetchall()

        for (user_id,) in old_users:

            cur.execute("""
                SELECT id
                FROM chats
                WHERE user_id = %s
                ORDER BY created_at ASC
                LIMIT 1
            """, (user_id,))

            existing_chat = cur.fetchone()

            if existing_chat:
                chat_id = existing_chat[0]
            else:
                cur.execute("""
                    INSERT INTO chats (user_id, title)
                    VALUES (%s, %s)
                    RETURNING id
                """, (user_id, "گفتگوی قبلی"))

                chat_id = cur.fetchone()[0]

            cur.execute("""
                UPDATE messages
                SET chat_id = %s
                WHERE user_id = %s
                  AND chat_id IS NULL
            """, (chat_id, user_id))

        conn.commit()

        cur.close()
        conn.close()

        print("Database connected.")
        print("Users table ready.")
        print("Chats table ready.")
        print("Messages table ready.")

    except Exception as e:
        print("Database Error:", e)


# -----------------------------
# Main page
# -----------------------------

def get_db_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

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
# Chat system
# -----------------------------

@app.route("/chats", methods=["GET"])
def get_chats():

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "message": "ابتدا وارد حساب شوید."
        }), 401

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT id, title, created_at, updated_at
            FROM chats
            WHERE user_id = %s
            ORDER BY updated_at DESC, id DESC
        """, (session["user_id"],))

        rows = cur.fetchall()

        cur.close()
        conn.close()

        return jsonify({
            "success": True,
            "chats": [
                {
                    "id": chat_id,
                    "title": title,
                    "created_at": created_at.isoformat() if created_at else None,
                    "updated_at": updated_at.isoformat() if updated_at else None
                }
                for chat_id, title, created_at, updated_at in rows
            ]
        })

    except Exception as e:
        print("Chats Error:", e)

        return jsonify({
            "success": False,
            "message": "خطا در دریافت چت‌ها."
        }), 500


@app.route("/chats", methods=["POST"])
def create_chat():

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "message": "ابتدا وارد حساب شوید."
        }), 401

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO chats (user_id, title)
            VALUES (%s, %s)
            RETURNING id, title
        """, (
            session["user_id"],
            "چت جدید"
        ))

        chat_id, title = cur.fetchone()

        conn.commit()

        cur.close()
        conn.close()

        return jsonify({
            "success": True,
            "chat": {
                "id": chat_id,
                "title": title
            }
        })

    except Exception as e:
        print("Create Chat Error:", e)

        return jsonify({
            "success": False,
            "message": "خطا در ساخت چت جدید."
        }), 500


@app.route("/chats/<int:chat_id>", methods=["GET"])
def get_chat(chat_id):

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "message": "ابتدا وارد حساب شوید."
        }), 401

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # مطمئن می‌شویم چت متعلق به همین کاربر است
        cur.execute("""
            SELECT id, title
            FROM chats
            WHERE id = %s
              AND user_id = %s
        """, (
            chat_id,
            session["user_id"]
        ))

        chat_row = cur.fetchone()

        if not chat_row:
            cur.close()
            conn.close()

            return jsonify({
                "success": False,
                "message": "چت پیدا نشد."
            }), 404

        cur.execute("""
            SELECT id, role, content, created_at
            FROM messages
            WHERE chat_id = %s
              AND user_id = %s
            ORDER BY created_at ASC, id ASC
        """, (
            chat_id,
            session["user_id"]
        ))

        rows = cur.fetchall()

        cur.close()
        conn.close()

        return jsonify({
            "success": True,
            "chat": {
                "id": chat_row[0],
                "title": chat_row[1]
            },
            "messages": [
                {
                    "id": message_id,
                    "role": role,
                    "content": content,
                    "created_at": created_at.isoformat()
                    if created_at else None
                }
                for message_id, role, content, created_at in rows
            ]
        })

    except Exception as e:
        print("Get Chat Error:", e)

        return jsonify({
            "success": False,
            "message": "خطا در دریافت گفتگو."
        }), 500


@app.route("/chats/<int:chat_id>", methods=["DELETE"])
def delete_chat(chat_id):

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "message": "ابتدا وارد حساب شوید."
        }), 401

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            DELETE FROM chats
            WHERE id = %s
              AND user_id = %s
        """, (
            chat_id,
            session["user_id"]
        ))

        deleted = cur.rowcount

        conn.commit()

        cur.close()
        conn.close()

        if deleted == 0:
            return jsonify({
                "success": False,
                "message": "چت پیدا نشد."
            }), 404

        return jsonify({
            "success": True
        })

    except Exception as e:
        print("Delete Chat Error:", e)

        return jsonify({
            "success": False,
            "message": "خطا در حذف چت."
        }), 500


# سازگاری با /history قدیمی
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

        cur.execute("""
            SELECT role, content
            FROM messages
            WHERE user_id = %s
            ORDER BY created_at ASC, id ASC
        """, (session["user_id"],))

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




# -----------------------------
# GapGPT Image API test
# -----------------------------

def test_gapgpt_image_api():
    """
    Safe startup test:
    - Uses the existing GAPGPT_API_KEY and base URL.
    - Does NOT expose the API key.
    - Does NOT save anything to PostgreSQL.
    - Does NOT generate/save a real image yet.
    """
    try:
        if not os.getenv("GAPGPT_API_KEY"):
            print("IMAGE TEST: GAPGPT_API_KEY is not configured.")
            return

        test_client = OpenAI(
            api_key=os.getenv("GAPGPT_API_KEY"),
            base_url="https://api.gapgpt.app/v1"
        )

        print("IMAGE TEST: checking GapGPT API/model access...")

        models = test_client.models.list()

        model_ids = []
        for model in getattr(models, "data", []) or []:
            model_id = getattr(model, "id", None)
            if model_id:
                model_ids.append(model_id)

        print("IMAGE TEST: API connection OK.")
        print("IMAGE TEST: available model IDs:")
        print(model_ids)

        image_models = [
            m for m in model_ids
            if any(word in m.lower() for word in ["image", "img", "dall", "flux", "sd", "gemini"])
        ]

        if image_models:
            print("IMAGE TEST: possible image-capable models found:")
            print(image_models)
        else:
            print("IMAGE TEST: no obvious image model found in models.list().")

    except Exception as e:
        print("IMAGE TEST ERROR:", type(e).__name__, str(e))


# -----------------------------
# Image generation
# -----------------------------

@app.route("/generate-image", methods=["POST"])
def generate_image():
    # فقط کاربران واردشده
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "message": "🔐 برای ساخت تصویر ابتدا وارد حساب شوید."
        }), 401

    user_id = session["user_id"]

    try:
        data = request.get_json() or {}
        prompt = data.get("prompt", "").strip()

        if not prompt:
            return jsonify({
                "success": False,
                "message": "لطفاً توضیح تصویر را وارد کنید."
            }), 400

        if not os.getenv("AVALAI_API_KEY"):
            return jsonify({
                "success": False,
                "message": "کلید AvalAI تنظیم نشده است."
            }), 500

        # -----------------------------
        # Check daily image limit
        # Maximum: 2 images per user per day
        # -----------------------------

        conn = None

        try:
            conn = get_db_connection()
            conn.autocommit = False

            with conn.cursor() as cur:

                # جلوگیری از درخواست همزمان برای یک کاربر
                cur.execute(
                    "SELECT pg_advisory_xact_lock(%s)",
                    (int(user_id),)
                )

                cur.execute(
                    """
                    SELECT image_count
                    FROM public.image_usage
                    WHERE user_id = %s
                      AND usage_date = CURRENT_DATE
                    FOR UPDATE
                    """,
                    (user_id,)
                )

                row = cur.fetchone()

                current_count = row[0] if row else 0

                # حداکثر 2 تصویر در روز
                if current_count >= 2:
                    conn.rollback()

                    return jsonify({
                        "success": False,
                        "message": "🚫 سهمیه امروز شما تمام شده است. فردا دوباره ۲ تصویر دریافت می‌کنید.",
                        "remaining": 0
                    }), 429

            # هنوز سهمیه مصرف نشده؛ API را صدا می‌زنیم
            cleanup_old_images()

            response = image_client.with_options(
                timeout=180
            ).images.generate(
                model=IMAGE_MODEL,
                prompt=prompt,
                size="1024x1024",
                n=1,
                response_format="b64_json"
            )

            image_data = response.data[0].b64_json

            if not image_data:
                conn.rollback()

                return jsonify({
                    "success": False,
                    "message": "تصویری از موتور دریافت نشد."
                }), 502

            image_bytes = base64.b64decode(image_data)

            filename = f"{uuid.uuid4().hex}.png"
            file_path = TEMP_IMAGE_DIR / filename

            with open(file_path, "wb") as f:
                f.write(image_bytes)

            # -----------------------------
            # Count successful generation
            # -----------------------------

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.image_usage
                        (user_id, usage_date, image_count)
                    VALUES
                        (%s, CURRENT_DATE, 1)
                    ON CONFLICT (user_id, usage_date)
                    DO UPDATE SET
                        image_count = public.image_usage.image_count + 1
                    RETURNING image_count
                    """,
                    (user_id,)
                )

                new_count = cur.fetchone()[0]

            conn.commit()

            image_url = f"/static/generated/{filename}"

            return jsonify({
                "success": True,
                "message": "تصویر با موفقیت ساخته شد.",
                "image_url": image_url,
                "remaining": max(0, 2 - new_count)
            })

        except Exception:
            if conn:
                conn.rollback()
            raise

        finally:
            if conn:
                conn.close()

    except Exception as e:
        print("Image Generation Error:", repr(e))

        return jsonify({
            "success": False,
            "message": "❌ ساخت تصویر با خطا مواجه شد."
        }), 500
