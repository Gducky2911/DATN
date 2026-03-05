

from flask import Blueprint, render_template, request, jsonify, current_app
from models import db, Menu, Table, Reservation
from datetime import datetime, timedelta
from sqlalchemy import func, desc
import re

bp = Blueprint("chatbot", __name__, url_prefix="/chatbot")

def normalize_text(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


def find_menu_by_name(text):
 
    words = normalize_text(text).split()

    for word in words:
        item = Menu.query.filter(
            Menu.available == True,
            Menu.name.ilike(f"%{word}%")
        ).first()
        if item:
            return item
    return None


def build_menu_response(item: Menu, note: str = None):
    """
    Chuẩn response có ảnh + calories
    """
    message = f"🍽️ **{item.name}**\n"

    if item.price:
        message += f"💰 Giá: **{item.price:,.0f}đ**\n"

    if item.calories:
        message += f"🔥 Calories: **{item.calories} kcal**\n"

        if item.calories <= 500:
            message += "✅ Phù hợp cho người ăn kiêng\n"
        else:
            message += "⚠️ Nên dùng vừa phải nếu đang giảm cân\n"

    if note:
        message += f"\n{note}"

    return {
        "success": True,
        "message": message.strip(),
        "image": (
            f"/static/images/menu/{item.image_url}"
            if item.image_url else None
        ),
        "timestamp": datetime.now().strftime("%H:%M"),
    }



def get_best_sellers(limit=5):
    from models import OrderItem

    return (
        db.session.query(
            Menu.name,
            Menu.price,
            Menu.calories,
            Menu.image_url,
            func.sum(OrderItem.quantity).label("total_sold"),
        )
        .join(OrderItem, Menu.menu_id == OrderItem.menu_id)
        .filter(Menu.available == True)
        .group_by(Menu.menu_id)
        .order_by(desc("total_sold"))
        .limit(limit)
        .all()
    )


def check_table_availability():
    now = datetime.now()

    reserved_ids = (
        db.session.query(Reservation.table_id)
        .filter(
            Reservation.status.in_(["pending", "confirmed"]),
            Reservation.reservation_time.between(
                now - timedelta(hours=2),
                now + timedelta(hours=2),
            ),
        )
        .all()
    )

    reserved_ids = [r[0] for r in reserved_ids]

    count = Table.query.filter(
        Table.status == "available",
        ~Table.table_id.in_(reserved_ids),
    ).count()

    return count > 0, count



def get_system_prompt():
    return f"""
Bạn là trợ lý AI của {current_app.config.get('RESTAURANT_NAME', 'nhà hàng')}.

QUY TẮC:
- Không bịa giá tiền
- Không nói món không bán nếu chưa chắc
- Nếu thiếu dữ liệu → nói lịch sự
- Trả lời ngắn gọn, tiếng Việt
"""


# ======================================================
# 4. UI
# ======================================================

@bp.route("/")
def index():
    return render_template("chatbot/chat.html")


# ======================================================
# 5. QUICK QUESTIONS (BUTTON GỢI Ý)
# ======================================================

@bp.route("/api/quick-questions", methods=["GET"])
def quick_questions():
    return jsonify({
        "suggestions": [
            "Món nào bán chạy nhất?",
            "Giá phở bò bao nhiêu?",
            "Phở bò bao nhiêu calories?",
            "Ăn kiêng nên ăn món gì?",
            "Nhà hàng còn bàn trống không?"
        ]
    })


# ======================================================
# 6. CHAT API
# ======================================================

@bp.route("/api/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        user_message = data.get("message", "").strip()
        history = data.get("history", [])

        if not user_message:
            return jsonify({"success": False, "message": "Tin nhắn trống"})

        msg = user_message.lower()

        # --------------------------------------------------
        # (A) HỎI GIÁ / CALORIES MÓN
        # --------------------------------------------------
        if any(k in msg for k in ["giá", "calo", "calories", "ăn kiêng", "béo"]):
            item = find_menu_by_name(user_message)
            if item:
                return jsonify(build_menu_response(item))

        # --------------------------------------------------
        # (B) GỢI Ý ĂN KIÊNG
        # --------------------------------------------------
        if "ăn kiêng" in msg or "ít calo" in msg:
            items = (
                Menu.query.filter(
                    Menu.available == True,
                    Menu.calories.isnot(None),
                    Menu.calories <= 500
                )
                .order_by(Menu.calories)
                .limit(5)
                .all()
            )

            if items:
                text = "🥗 **Món phù hợp cho ăn kiêng:**\n"
                for m in items:
                    text += f"- {m.name}: {m.calories} kcal\n"

                return jsonify({
                    "success": True,
                    "message": text,
                    "image": (
                        f"/static/images/menu/{items[0].image_url}"
                        if items[0].image_url else None
                    ),
                    "timestamp": datetime.now().strftime("%H:%M"),
                })

        # --------------------------------------------------
        # (C) BEST SELLER
        # --------------------------------------------------
        if "bán chạy" in msg:
            best = get_best_sellers()
            if best:
                text = "🔥 **Món bán chạy nhất:**\n"
                for name, price, cal, img, sold in best:
                    text += f"- {name}: {price:,.0f}đ ({sold} phần)\n"

                return jsonify({
                    "success": True,
                    "message": text,
                    "image": (
                        f"/static/images/menu/{best[0].image_url}"
                        if best[0].image_url else None
                    ),
                    "timestamp": datetime.now().strftime("%H:%M"),
                })

        # --------------------------------------------------
        # (D) BÀN TRỐNG
        # --------------------------------------------------
        if any(k in msg for k in ["bàn", "đặt bàn"]):
            has_table, count = check_table_availability()
            return jsonify({
                "success": True,
                "message": (
                    f"✅ Hiện còn **{count} bàn trống**."
                    if has_table else
                    "❌ Hiện tại không còn bàn trống."
                ),
                "timestamp": datetime.now().strftime("%H:%M"),
            })

        # --------------------------------------------------
        # (E) FALLBACK GPT
        # --------------------------------------------------
        from openai import OpenAI
        client = OpenAI(api_key=current_app.config["OPENAI_API_KEY"])

        messages = [{"role": "system", "content": get_system_prompt()}]
        for h in history[-6:]:
            messages.append(h)

        messages.append({"role": "user", "content": user_message})

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.6,
            max_tokens=300,
        )

        return jsonify({
            "success": True,
            "message": res.choices[0].message.content,
            "timestamp": datetime.now().strftime("%H:%M"),
        })

    except Exception as e:
        current_app.logger.error(e)
        return jsonify({
            "success": False,
            "message": "Chatbot đang bận, vui lòng thử lại sau."
        })


