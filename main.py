# -*- coding: utf-8 -*-
"""
تطبيق ورشة السيارات - نسخة الويب PWA
"""

from flask import (
    Flask,
    render_template,
    send_from_directory,
    request,
    jsonify,
    Response,
)
import requests as req_lib
import os
import json
import uuid
import threading
import time
import re
from datetime import datetime, timedelta

app = Flask(__name__)

NGROK_URL = os.environ.get(
    "NGROK_URL", "https://curling-underwear-bubble.ngrok-free.dev"
)
API_BASE = os.environ.get("API_BASE", f"{NGROK_URL}/api")

# ─── مخزن الحجوزات والإشعارات (في الذاكرة) ────────────────────────────────────
_bookings = []  # قائمة الحجوزات المحلية
_notifications = {}  # {phone: [{id, type, message, booking_id, timestamp, read}]}
_lock = threading.Lock()


# ─── إضافة إشعار ──────────────────────────────────────────────────────────────
def _add_notification(phone, notif_type, message, booking_id=None):
    with _lock:
        if phone not in _notifications:
            _notifications[phone] = []
        _notifications[phone].insert(
            0,
            {
                "id": str(uuid.uuid4())[:8],
                "type": notif_type,
                "message": message,
                "booking_id": booking_id,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "read": False,
            },
        )


# ─── خيط الخلفية: يفحص الحجوزات المقتربة كل دقيقة ───────────────────────────
def _background_checker():
    while True:
        time.sleep(60)
        now = datetime.now()
        with _lock:
            for b in _bookings:
                if b.get("notified_approaching") or b.get("status") == "completed":
                    continue
                try:
                    booking_dt = datetime.strptime(
                        f"{b['date']} {b['time']}", "%Y-%m-%d %H:%M"
                    )
                    diff_min = (booking_dt - now).total_seconds() / 60
                    if 0 <= diff_min <= 35:
                        b["notified_approaching"] = True
                        phone = b.get("customerPhone", "")
                        if phone:
                            num = b.get("waiting_number", "؟")
                            _add_notification(
                                phone,
                                "approaching",
                                f"⏰ اقترب موعدك! دورك رقم {num} بعد حوالي 30 دقيقة. "
                                f"يرجى التوجه إلى الورشة.",
                                b.get("id"),
                            )
                except Exception:
                    pass


_bg_thread = threading.Thread(target=_background_checker, daemon=True)
_bg_thread.start()


# ─── بيانات تجريبية ───────────────────────────────────────────────────────────
DEMO_GARAGES = [
    {
        "Id": 1,
        "Name": "المرآب 1",
        "Description": "متخصص في تغيير الزيت وفلتر الهواء",
        "Status": "Available",
        "EstimatedMinutes": 0,
    },
    {
        "Id": 2,
        "Name": "المرآب 2",
        "Description": "إصلاح المحركات والناقل",
        "Status": "Partial",
        "EstimatedMinutes": 30,
    },
    {
        "Id": 3,
        "Name": "المرآب 3",
        "Description": "فحص وإصلاح الأجهزة الكهربائية",
        "Status": "Busy",
        "EstimatedMinutes": 60,
    },
    {
        "Id": 4,
        "Name": "المرآب 4",
        "Description": "إصلاح وتغيير الفرامل",
        "Status": "Available",
        "EstimatedMinutes": 0,
    },
]
DEMO_POSTS = [
    {
        "Id": 1,
        "Title": "عروض الصيف",
        "Type": "Text",
        "Text": "خصم 20% على جميع خدمات تغيير الزيت!",
        "ImagePath": None,
        "VideoUrl": None,
        "CreatedAt": "2025-07-01T10:00:00",
    },
    {
        "Id": 2,
        "Title": "نصيحة الأسبوع",
        "Type": "Text",
        "Text": "تذكر فحص ضغط الإطارات كل شهر.",
        "ImagePath": None,
        "VideoUrl": None,
        "CreatedAt": "2025-07-01T09:00:00",
    },
]
DEMO_PRODUCTS = [
    {
        "Id": 1,
        "Name": "زيت موتور توتال 5W-40",
        "Price": 2500,
        "IsAvailable": True,
        "ImagePath": None,
        "CreatedAt": "2025-07-01T00:00:00",
    },
    {
        "Id": 2,
        "Name": "فلتر زيت أصلي",
        "Price": 800,
        "IsAvailable": True,
        "ImagePath": None,
        "CreatedAt": "2025-07-01T00:00:00",
    },
]

DEMO_ROUTES = {
    "garage/status": lambda: DEMO_GARAGES,
    "post": lambda: DEMO_POSTS,
    "product": lambda: DEMO_PRODUCTS,
}


# ─── مساعد: جلب بيانات من API الحقيقي بدون proxy ─────────────────────────────
def _api_get(path):
    try:
        r = req_lib.get(
            f"{API_BASE}/{path}",
            headers={
                "ngrok-skip-browser-warning": "true",
                "User-Agent": "WorkshopApp/1.0",
            },
            timeout=5,
        )
        ct = r.headers.get("Content-Type", "")
        if "text/html" in ct:
            return None
        return r.json()
    except Exception:
        return None


# ─── حساب أقل وقت انتظار من المرايب ──────────────────────────────────────────
def _get_min_wait():
    garages = _api_get("Garage/status") or DEMO_GARAGES
    wait_times = [
        g.get("EstimatedMinutes", 0)
        for g in garages
        if g.get("Status") in ("Available", "Partial")
    ]
    if not wait_times:
        wait_times = [g.get("EstimatedMinutes", 60) for g in garages]
    min_wait = min(wait_times, default=0)
    return min_wait


# ─── تأكيد الحجز (تجريبي داخلي) ──────────────────────────────────────────────
def _demo_booking(data, local_id, waiting_number, people_ahead, min_wait):
    if not all(
        [
            data.get("customerName"),
            data.get("customerPhone"),
            data.get("service"),
            data.get("date"),
            data.get("time"),
        ]
    ):
        return jsonify({"error": "جميع الحقول مطلوبة"}), 400

    est = f"{min_wait} دقيقة" if min_wait > 0 else "متاح الآن"
    return jsonify(
        {
            "Message": "تم تأكيد حجزك بنجاح!",
            "WaitingNumber": waiting_number,
            "PeopleAhead": people_ahead,
            "EstimatedTime": est,
            "BookingId": local_id,
        }
    )


# ─── Proxy عام ────────────────────────────────────────────────────────────────
@app.route("/api/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "DELETE"])
@app.route("/api/<path:path>", methods=["GET", "POST", "PUT", "DELETE"])
def proxy(path):
    # ─── معالجة خاصة لإنشاء الحجز ──────────────────────────────────────────
    if path.lower() == "booking/create" and request.method == "POST":
        data = request.get_json(silent=True) or {}
        min_wait = _get_min_wait()
        local_id = str(uuid.uuid4())[:8]
        with _lock:
            people_ahead = len(
                [
                    b
                    for b in _bookings
                    if b.get("date") == data.get("date")
                    and b.get("status") != "completed"
                ]
            )
            waiting_number = len(_bookings) + 1
            _bookings.append(
                {
                    "id": local_id,
                    "customerName": data.get("customerName", ""),
                    "customerPhone": data.get("customerPhone", ""),
                    "service": data.get("service", ""),
                    "date": data.get("date", ""),
                    "time": data.get("time", ""),
                    "status": "pending",
                    "waiting_number": waiting_number,
                    "min_wait": min_wait,
                    "notified_approaching": False,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                }
            )

        est_label = f"{min_wait} دقيقة" if min_wait > 0 else "متاح الآن"

        try:
            headers = {k: v for k, v in request.headers if k.lower() != "host"}
            headers["ngrok-skip-browser-warning"] = "true"
            headers["User-Agent"] = "WorkshopApp/1.0"
            resp = req_lib.post(
                f"{API_BASE}/Booking/create", json=data, headers=headers, timeout=8
            )
            ct = resp.headers.get("Content-Type", "")
            if "text/html" in ct:
                raise req_lib.exceptions.ConnectionError("html response")
            result = resp.json()
            result.setdefault("EstimatedTime", est_label)
            result["BookingId"] = local_id
            return jsonify(result), resp.status_code

        except Exception:
            return _demo_booking(data, local_id, waiting_number, people_ahead, min_wait)

    # ─── معالجة خاصة: إتمام الحجز من موقع الموظف Blazor ────────────────────
    # PUT /api/Booking/complete/{id}  أو  PUT /api/Booking/{id}/complete
    _cm1 = re.match(r"^booking/complete/(\w+)$", path.lower())
    _cm2 = re.match(r"^booking/(\w+)/complete$", path.lower())
    _complete_id = (_cm1 or _cm2) and ((_cm1 or _cm2).group(1))
    if _complete_id and request.method in ("PUT", "POST"):
        target = f"{API_BASE}/{path}"
        try:
            fwd = {k: v for k, v in request.headers if k.lower() != "host"}
            fwd["ngrok-skip-browser-warning"] = "true"
            fwd["User-Agent"] = "WorkshopApp/1.0"
            resp = req_lib.request(
                method=request.method,
                url=target,
                json=request.get_json(silent=True),
                headers=fwd,
                timeout=8,
            )
        except Exception:
            pass
        # أرسل إشعاراً للزبون في نظام الإشعارات المحلي
        booking = None
        phone = ""
        name = ""
        with _lock:
            booking = next(
                (
                    b
                    for b in _bookings
                    if b["id"] == _complete_id
                    or str(b.get("api_id", "")) == _complete_id
                ),
                None,
            )
            if booking:
                booking["status"] = "completed"
                phone = booking.get("customerPhone", "")
                name = booking.get("customerName", "")
        if phone:
            _add_notification(
                phone,
                "completed",
                f"✅ تم اكتمال إصلاح سيارتك يا {name}. يمكنك القدوم لاستلامها.",
                _complete_id,
            )
        try:
            return Response(
                resp.content,
                status=resp.status_code,
                content_type=resp.headers.get("Content-Type", "application/json"),
            )
        except Exception:
            return jsonify({"ok": True})

    # ─── Proxy العادي لبقية المسارات ────────────────────────────────────────
    target = f"{API_BASE}/{path}"
    try:
        fwd_headers = {k: v for k, v in request.headers if k.lower() != "host"}
        fwd_headers["ngrok-skip-browser-warning"] = "true"
        fwd_headers["User-Agent"] = "WorkshopApp/1.0"
        params = dict(request.args)
        params["ngrok-skip-browser-warning"] = "true"
        resp = req_lib.request(
            method=request.method,
            url=target,
            params=params,
            json=request.get_json(silent=True),
            data=request.form or None,
            headers=fwd_headers,
            timeout=8,
        )
        ct = resp.headers.get("Content-Type", "")
        if "text/html" in ct:
            raise req_lib.exceptions.ConnectionError("html response")

        body = resp.content
        if "application/json" in ct:
            body = body.replace(b"http://localhost:5001", b"/media")

        return Response(
            body, status=resp.status_code, content_type=ct or "application/json"
        )

    except (req_lib.exceptions.ConnectionError, req_lib.exceptions.Timeout):
        key = path.lower().rstrip("/")
        if request.method == "GET":
            for route_key, data_fn in DEMO_ROUTES.items():
                if key == route_key:
                    return jsonify(data_fn())
        return jsonify({"error": "الخادم غير متاح"}), 503

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Media proxy (صور وفيديوهات من الخادم) ───────────────────────────────────
@app.route("/media/<path:path>")
def media_proxy(path):
    url = f"{NGROK_URL}/{path}"
    try:
        r = req_lib.get(
            url,
            headers={
                "ngrok-skip-browser-warning": "true",
                "User-Agent": "WorkshopApp/1.0",
            },
            timeout=10,
            stream=True,
        )
        ct = r.headers.get("Content-Type", "application/octet-stream")
        return Response(r.content, status=r.status_code, content_type=ct)
    except Exception:
        return "", 404


# ─── إشعارات ──────────────────────────────────────────────────────────────────
@app.route("/notifications/<phone>")
def get_notifications(phone):
    with _lock:
        notifs = list(_notifications.get(phone, []))
    return jsonify(notifs)


@app.route("/notifications/read/<nid>", methods=["POST"])
def mark_read(nid):
    data = request.get_json(silent=True) or {}
    phone = data.get("phone", "")
    with _lock:
        for n in _notifications.get(phone, []):
            if n["id"] == nid:
                n["read"] = True
                break
    return jsonify({"ok": True})


@app.route("/notifications/read-all", methods=["POST"])
def mark_all_read():
    phone = (request.get_json(silent=True) or {}).get("phone", "")
    with _lock:
        for n in _notifications.get(phone, []):
            n["read"] = True
    return jsonify({"ok": True})


@app.route("/notifications/count/<phone>")
def notif_count(phone):
    with _lock:
        count = sum(1 for n in _notifications.get(phone, []) if not n["read"])
    return jsonify({"unread": count})


# ─── استقبال إشعار من API (C#) ───────────────────────────────────────────────
@app.route("/api/notify", methods=["POST"])
def notify_from_api():
    """استقبال إشعار من API وإضافته للإشعارات المحلية"""
    data = request.get_json(silent=True) or {}
    phone = data.get("phone", "")
    message = data.get("message", "")
    booking_id = data.get("bookingId", "")

    if phone and message:
        _add_notification(phone, "completed", message, booking_id)
        print(f"[INFO] تم إضافة إشعار للرقم {phone}: {message[:50]}...")
        return jsonify({"status": "ok"}), 200
    return jsonify({"status": "error", "message": "بيانات غير كاملة"}), 400


# ─── صفحات التطبيق ────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/garages")
def garages():
    return render_template("garages.html")


@app.route("/posts")
def posts():
    return render_template("posts.html")


@app.route("/products")
def products():
    return render_template("products.html")


@app.route("/booking")
def booking():
    return render_template("booking.html")


@app.route("/my-notifications")
def my_notifications():
    return render_template("notifications.html")


@app.route("/sw.js")
def service_worker():
    return send_from_directory("static", "sw.js", mimetype="application/javascript")


@app.route("/manifest.json")
def manifest():
    return send_from_directory(
        "static", "manifest.json", mimetype="application/manifest+json"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
