# -*- coding: utf-8 -*-
"""
تطبيق ورشة السيارات - نسخة الويب PWA مع دعم ngrok
"""

from flask import Flask, render_template, send_from_directory, request, jsonify, Response
import requests as req_lib
import os
import json
import uuid
import threading
import time
import re
from datetime import datetime, timedelta

app = Flask(__name__)

# ============================================================
# 🔥 الإعدادات الأساسية
# ============================================================
NGROK_URL = os.environ.get('NGROK_URL', 'https://curling-underwear-bubble.ngrok-free.dev')
API_BASE  = os.environ.get('API_BASE',  f'{NGROK_URL}/api')

# هيدرات لتجنب صفحة تحذير ngrok
NGROK_HEADERS = {
    'ngrok-skip-browser-warning': 'true',
    'User-Agent': 'WorkshopApp/1.0'
}

# ─── مخزن الحجوزات والإشعارات (في الذاكرة) ────────────────────────────────────
_bookings      = []
_notifications = {}
_lock          = threading.Lock()


# ─── إضافة إشعار ──────────────────────────────────────────────────────────────
def _add_notification(phone, notif_type, message, booking_id=None):
    with _lock:
        if phone not in _notifications:
            _notifications[phone] = []
        _notifications[phone].insert(0, {
            'id':         str(uuid.uuid4())[:8],
            'type':       notif_type,
            'message':    message,
            'booking_id': booking_id,
            'timestamp':  datetime.now().strftime('%Y-%m-%d %H:%M'),
            'read':       False
        })


# ─── خيط الخلفية: يفحص الحجوزات المقتربة كل دقيقة ───────────────────────────
def _background_checker():
    while True:
        time.sleep(60)
        now = datetime.now()
        with _lock:
            for b in _bookings:
                if b.get('notified_approaching') or b.get('status') == 'completed':
                    continue
                try:
                    booking_dt = datetime.strptime(
                        f"{b['date']} {b['time']}", '%Y-%m-%d %H:%M')
                    diff_min = (booking_dt - now).total_seconds() / 60
                    if 0 <= diff_min <= 35:
                        b['notified_approaching'] = True
                        phone = b.get('customerPhone', '')
                        if phone:
                            num = b.get('waiting_number', '؟')
                            _add_notification(
                                phone, 'approaching',
                                f"⏰ اقترب موعدك! دورك رقم {num} بعد حوالي 30 دقيقة. "
                                f"يرجى التوجه إلى الورشة.",
                                b.get('id')
                            )
                except Exception:
                    pass


_bg_thread = threading.Thread(target=_background_checker, daemon=True)
_bg_thread.start()


# ─── بيانات تجريبية ───────────────────────────────────────────────────────────
DEMO_GARAGES = [
    {"Id":1,"Name":"المرآب 1","Description":"متخصص في تغيير الزيت وفلتر الهواء","Status":"Available","EstimatedMinutes":0},
    {"Id":2,"Name":"المرآب 2","Description":"إصلاح المحركات والناقل",            "Status":"Partial",  "EstimatedMinutes":30},
    {"Id":3,"Name":"المرآب 3","Description":"فحص وإصلاح الأجهزة الكهربائية",    "Status":"Busy",     "EstimatedMinutes":60},
    {"Id":4,"Name":"المرآب 4","Description":"إصلاح وتغيير الفرامل",              "Status":"Available","EstimatedMinutes":0},
]
DEMO_POSTS = [
    {"Id":1,"Title":"عروض الصيف","Type":"Text","Text":"خصم 20% على جميع خدمات تغيير الزيت!","ImagePath":None,"VideoUrl":None,"CreatedAt":"2025-07-01T10:00:00"},
    {"Id":2,"Title":"نصيحة الأسبوع","Type":"Text","Text":"تذكر فحص ضغط الإطارات كل شهر.","ImagePath":None,"VideoUrl":None,"CreatedAt":"2025-07-01T09:00:00"},
]
DEMO_PRODUCTS = [
    {"Id":1,"Name":"زيت موتور توتال 5W-40","Price":2500,"IsAvailable":True, "ImagePath":None,"CreatedAt":"2025-07-01T00:00:00"},
    {"Id":2,"Name":"فلتر زيت أصلي",         "Price":800, "IsAvailable":True, "ImagePath":None,"CreatedAt":"2025-07-01T00:00:00"},
]

DEMO_ROUTES = {
    'garage/status': lambda: DEMO_GARAGES,
    'post':          lambda: DEMO_POSTS,
    'product':       lambda: DEMO_PRODUCTS,
}


# ─── مساعد: جلب بيانات من API الحقيقي مع تجاوز ngrok warning ─────────────────
def _api_get(path):
    try:
        r = req_lib.get(
            f"{API_BASE}/{path}",
            headers=NGROK_HEADERS,
            timeout=5
        )
        ct = r.headers.get('Content-Type', '')
        if 'text/html' in ct:
            return None
        return r.json()
    except Exception:
        return None


def _api_post(path, data):
    try:
        r = req_lib.post(
            f"{API_BASE}/{path}",
            json=data,
            headers=NGROK_HEADERS,
            timeout=8
        )
        ct = r.headers.get('Content-Type', '')
        if 'text/html' in ct:
            return None
        return r.json(), r.status_code
    except Exception:
        return None, 500


# ─── حساب أقل وقت انتظار من المرايب ──────────────────────────────────────────
def _get_min_wait():
    garages = _api_get('Garage/status') or DEMO_GARAGES
    wait_times = [g.get('EstimatedMinutes', 0) for g in garages
                  if g.get('Status') in ('Available', 'Partial')]
    if not wait_times:
        wait_times = [g.get('EstimatedMinutes', 60) for g in garages]
    min_wait = min(wait_times, default=0)
    return min_wait


# ─── تأكيد الحجز (تجريبي داخلي) ──────────────────────────────────────────────
def _demo_booking(data, local_id, waiting_number, people_ahead, min_wait):
    if not all([data.get('customerName'), data.get('customerPhone'),
                data.get('service'), data.get('date'), data.get('time')]):
        return jsonify({"error": "جميع الحقول مطلوبة"}), 400

    est = f"{min_wait} دقيقة" if min_wait > 0 else "متاح الآن"
    return jsonify({
        "Message":       "تم تأكيد حجزك بنجاح!",
        "WaitingNumber": waiting_number,
        "PeopleAhead":   people_ahead,
        "EstimatedTime": est,
        "BookingId":     local_id
    })


# ─── Proxy عام مع دعم ngrok ─────────────────────────────────────────────────
@app.route('/api/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE'])
@app.route('/api/<path:path>',            methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy(path):
    full_path = path.lower()
    
    # ─── معالجة خاصة لإنشاء الحجز ──────────────────────────────────────────
    if full_path == 'booking/create' and request.method == 'POST':
        data = request.get_json(silent=True) or {}
        min_wait     = _get_min_wait()
        local_id     = str(uuid.uuid4())[:8]
        with _lock:
            people_ahead = len([b for b in _bookings
                                 if b.get('date') == data.get('date')
                                 and b.get('status') != 'completed'])
            waiting_number = len(_bookings) + 1
            _bookings.append({
                'id':             local_id,
                'customerName':   data.get('customerName', ''),
                'customerPhone':  data.get('customerPhone', ''),
                'service':        data.get('service', ''),
                'date':           data.get('date', ''),
                'time':           data.get('time', ''),
                'status':         'pending',
                'waiting_number': waiting_number,
                'min_wait':       min_wait,
                'notified_approaching': False,
                'created_at':     datetime.now().strftime('%Y-%m-%d %H:%M'),
            })

        # محاولة إرسال إلى API الحقيقي
        api_result, status_code = _api_post('Booking/create', data)
        if api_result and status_code == 200:
            return jsonify(api_result), status_code
        
        # فشل الاتصال بـ API، استخدم البيانات المحلية
        return _demo_booking(data, local_id, waiting_number, people_ahead, min_wait)

    # ─── معالجة خاصة: إتمام الحجز ──────────────────────────────────────────
    cm1 = re.match(r'^booking/complete/(\w+)$', full_path)
    cm2 = re.match(r'^booking/(\w+)/complete$', full_path)
    complete_id = (cm1 or cm2) and ((cm1 or cm2).group(1))
    
    if complete_id and request.method in ('PUT', 'POST'):
        try:
            r = req_lib.request(
                method=request.method,
                url=f"{API_BASE}/{path}",
                json=request.get_json(silent=True),
                headers=NGROK_HEADERS,
                timeout=8
            )
            status_code = r.status_code
        except Exception:
            status_code = 500
        
        # تحديث الحالة محلياً وإرسال إشعار
        with _lock:
            for b in _bookings:
                if b['id'] == complete_id:
                    b['status'] = 'completed'
                    phone = b.get('customerPhone', '')
                    name = b.get('customerName', '')
                    if phone:
                        _add_notification(
                            phone, 'completed',
                            f"✅ تم اكتمال إصلاح سيارتك يا {name}. يمكنك القدوم لاستلامها.",
                            complete_id
                        )
                    break
        
        return jsonify({'ok': True}), 200

    # ─── Proxy العادي لبقية المسارات ────────────────────────────────────────
    target = f"{API_BASE}/{path}"
    try:
        params = dict(request.args)
        params['ngrok-skip-browser-warning'] = 'true'
        
        resp = req_lib.request(
            method=request.method,
            url=target,
            params=params,
            json=request.get_json(silent=True),
            data=request.form or None,
            headers=NGROK_HEADERS,
            timeout=8
        )
        
        ct = resp.headers.get('Content-Type', '')
        if 'text/html' in ct:
            # إذا كان الرد HTML (صفحة تحذير ngrok)، استخدم البيانات التجريبية
            key = full_path.rstrip('/')
            if request.method == 'GET':
                for route_key, data_fn in DEMO_ROUTES.items():
                    if key == route_key:
                        return jsonify(data_fn())
            return jsonify({"error": "الخادم غير متاح"}), 503

        body = resp.content
        return Response(body, status=resp.status_code, content_type=ct or 'application/json')

    except (req_lib.exceptions.ConnectionError, req_lib.exceptions.Timeout):
        key = full_path.rstrip('/')
        if request.method == 'GET':
            for route_key, data_fn in DEMO_ROUTES.items():
                if key == route_key:
                    return jsonify(data_fn())
        return jsonify({"error": "الخادم غير متاح"}), 503

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── صفحات التطبيق ────────────────────────────────────────────────────────────
@app.route('/')
def index():      return render_template('index.html')

@app.route('/garages')
def garages():    return render_template('garages.html')

@app.route('/posts')
def posts():      return render_template('posts.html')

@app.route('/products')
def products():   return render_template('products.html')

@app.route('/booking')
def booking():    return render_template('booking.html')

@app.route('/my-notifications')
def my_notifications(): return render_template('notifications.html')

@app.route('/sw.js')
def service_worker():
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')

@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json', mimetype='application/manifest+json')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
