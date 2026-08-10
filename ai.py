from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI
import os

# بارگذاری متغیرهای محیطی از فایل .env
load_dotenv()

app = Flask(__name__)
CORS(app)

# --- اتصال به GapGPT (جایگزین DeepSeek) ---
# دقت کن که در فایل .env حتماً باید GAPGPT_API_KEY رو تعریف کرده باشی
client = OpenAI(
    api_key=os.getenv("GAPGPT_API_KEY"),
    base_url="https://api.gapgpt.app/v1" # اصلاح شد: اضافه شدن h
)

# مسیر برای نمایش صفحه اصلی وب‌سایت
@app.route("/")
def index():
    return render_template("index.html")

# مسیر برای پردازش چت
@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        user_message = data.get("message", "").strip()

        if not user_message:
            return jsonify({"reply": "لطفاً یک پیام بنویس."}), 400

        # ارسال درخواست به GapGPT
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # مدل پیشنهادی: سریع، ارزان و با کیفیت بالا
            messages=[
                {"role": "system", "content": "تو دستیار هوش مصنوعی EpicAI.ir هستی. فارسی، دوستانه و مفید پاسخ بده."},
                {"role": "user", "content": user_message}
            ]
        )

        answer = response.choices[0].message.content
        return jsonify({"reply": answer})

    except Exception as e:
        # چاپ خطا در ترمینال برای اینکه بتونی بفهمی دقیقاً چه مشکلی پیش اومده
        print("GapGPT API Error:", e)
        return jsonify({"reply": f"❌ خطا در ارتباط با هوش مصنوعی: {str(e)}"}), 500

# اصلاح شد: اضافه شدن __ قبل و بعد از name
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000))), debug=True)
