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

        # بررسی رمز عبور
        if not check_password_hash(password_hash, password):
            return jsonify({
                "success": False,
                "message": "ایمیل یا رمز عبور اشتباه است."
            }), 401

        # ذخیره اطلاعات در Session
        session["user_id"] = user_id
        session["email"] = user_email

        return jsonify({
            "success": True,
            "message": "با موفقیت وارد شدید.",
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


if name == "main":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
