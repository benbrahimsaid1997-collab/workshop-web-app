# -*- coding: utf-8 -*-
"""
تطبيق ورشة السيارات - نسخة الويب PWA
"""

from flask import Flask, render_template, send_from_directory, request, jsonify, Response
import requests as req_lib
import os
import json
from datetime import datetime
import threading
import time

app = Flask(__name__)

# عنوان الـ API — سيُحدَّث عند الحصول على رابط ngrok الجديد (port 5001)
API_BASE = os.environ.get('API_BASE', 'http://localhost:5001/api')

# قاموس لتخزين الإشعارات المؤقتة (في الإنتاج، استخدم قاعدة بيانات)
notifications = []

# ─── بيانات تجريبية (تُستخدم إذا كان الـ API غير متاح) ───────────────────────
DEMO_GARAGES = [
    {"Name": "مرقد 1 - تغيير الزيت",      "Description": "متخصص في تغيير الزيت وفلتر الهواء", "Status": "Available", "EstimatedMinutes": 0},
    {"Name": "مرقد 2 - الميكانيك العام",   "Description": "إصلاح المحركات والناقل",            "Status": "Partial",   "EstimatedMinutes": 30},
    {"Name": "مرقد 3 - الكهرباء",          "Description": "فحص وإصلاح الأجهزة الكهربائية",    "Status": "Busy",      "EstimatedMinutes": 60},
    {"Name": "مرقد 4 - الفرامل",           "Description": "إصلاح وتغيير الفرامل",              "Status": "Available", "EstimatedMinutes": 0},
]

DEMO_POSTS = [
    {"Title": "عروض الصيف 2025",          "Type": "Text",  "Text": "خصم 20% على جميع خدمات تغيير الزيت طوال شهر يوليو! لا تفوت الفرصة.", "ImagePath": None, "VideoUrl": None},
    {"Title": "نصيحة الأسبوع",            "Type": "Text",  "Text": "تذكر فحص ضغط الإطارات كل شهر — يحافظ على سلامتك ويوفر الوقود.",    "ImagePath": None, "VideoUrl": None},
    {"Title": "فيديو: مؤشرات لوحة القيادة","Type": "Video", "Text": "شاهد هذا الفيديو لفهم جميع مؤشرات سيارتك.", "ImagePath": None, "VideoUrl": "https://www.youtube.com/watch?v=KIMgS4-RAVE"},
]

DEMO_PRODUCTS = [
    {"Name": "زيت موتور 5W-40 توتال",          "Price": 2500, "IsAvailable": True,  "ImagePath": None},
    {"Name": "زيت موتور 10W-40 كاسترول",        "Price": 2200, "IsAvailable": True,  "ImagePath": None},
    {"Name": "فلتر زيت أصلي",                   "Price": 800,  "IsAvailable": True,  "ImagePath": None},
    {"Name": "فلتر هواء",                       "Price": 650,  "IsAvailable": False, "ImagePath": None},
    {"Name": "سائل تبريد",                      "Price": 1200, "IsAvailable": True,  "ImagePath": None},
    {"Name": "وسادات الفرامل الأمامية",          "Price": 3500, "IsAvailable": True,  "ImagePath": None},
]

_bookings = []

DEMO_ROUTES = {
    'GET':  {
        'garage/status': lambda: DEMO_GARAGES,
        'post':          lambda: DEMO_POSTS,
        'product':       lambda: DEMO_PRODUCTS,
    },
    'POST': {
        'booking/create': '_handle_booking',
    }
}

def _demo_booking():
    data = request.get_json(silent=True) or {}
    name    = data.get('customerName', '').strip()
    phone   = data.get('customerPhone', '').strip()
    service = data.get('service', '')
    date    = data.get('date', '')
    time    = data.get('time', '')
    if not all([name, phone, service, date, time]):
        return jsonify({"error": "جميع الحقول مطلوبة"}), 400
    
    # حساب الوقت المتوقع بناءً على عدد الحجوزات
    waiting_number = len(_bookings) + 1
    people_ahead   = len([b for b in _bookings if b.get('date') == date])
    estimated_minutes = people_ahead * 30
    estimated_time = f"{estimated_minutes} دقيقة" if estimated_minutes < 60 else f"{(estimated_minutes // 60)} ساعة و {estimated_minutes % 60} دقيقة"
    
    _bookings.append({"customerName": name, "customerPhone": phone,
                      "service": service, "date": date, "time": time})
    
    # إضافة إشعار تأكيد
    notifications.append({
        "phone": phone,
        "message": f"✅ تم تأكيد حجزك! رقم انتظارك: {waiting_number}",
        "timestamp": datetime.now().isoformat(),
        "read": False
    })
    
    return jsonify({
        "Message":       "تم تأكيد حجزك بنجاح! (بيانات تجريبية)",
        "WaitingNumber": waiting_number,
        "PeopleAhead":   people_ahead,
        "EstimatedTime": estimated_time
    })


# ─── دالة لحساب الوقت المتوقع من المرآب ─────────────────────────────────────
def get_estimated_time_from_garage():
    """جلب أقل وقت متوقع من المرائب"""
    try:
        response = req_lib.get(f"{API_BASE}/Garage/status", timeout=5)
        if response.status_code == 200:
            garages = response.json()
            # البحث عن أقل وقت متوقع
            min_time = min([g.get('estimatedMinutes', 30) for g in garages])
            return min_time
    except:
        pass
    return 30  # القيمة الافتراضية


# ─── خدمة خلفية لإرسال الإشعارات التلقائية ─────────────────────────────────
def notification_worker():
    """تعمل في الخلفية وترسل إشعارات للمواعيد القريبة"""
    while True:
        try:
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            current_time = now.strftime("%H:%M")
            
            # جلب الحجوزات القادمة (خلال 30 دقيقة)
            upcoming = []
            for booking in _bookings:
                if booking.get('date') == today and booking.get('time') > current_time:
                    time_diff = (datetime.strptime(booking['time'], "%H:%M") - datetime.strptime(current_time, "%H:%M")).total_seconds() / 60
                    if 0 <= time_diff <= 30:
                        upcoming.append(booking)
            
            # إرسال إشعارات للمواعيد القريبة
            for booking in upcoming:
                phone = booking.get('customerPhone')
                waiting_num = booking.get('waitingNumber', '?')
                notifications.append({
                    "phone": phone,
                    "message": f"⏰ اقترب موعدك! دورك رقم {waiting_num} بعد حوالي 30 دقيقة. يرجى التوجه إلى الورشة.",
                    "timestamp": datetime.now().isoformat(),
                    "read": False
                })
            
            # التحقق من الحجوزات التي اكتملت (يمكن ربطها بـ API لاحقاً)
        except Exception as e:
            print(f"خطأ في خدمة الإشعارات: {e}")
        
        time.sleep(60)  # التحقق كل دقيقة


# تشغيل خدمة الإشعارات في الخلفية
threading.Thread(target=notification_worker, daemon=True).start()


# ─── Proxy ────────────────────────────────────────────────────────────────────
@app.route('/api/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE'])
@app.route('/api/<path:path>',            methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy(path):
    target = f"{API_BASE}/{path}"
    try:
        fwd_headers = {k: v for k, v in request.headers if k.lower() != 'host'}
        fwd_headers['ngrok-skip-browser-warning'] = 'true'
        fwd_headers['User-Agent'] = 'WorkshopApp/1.0'
        params = dict(request.args)
        params['ngrok-skip-browser-warning'] = 'true'
        resp = req_lib.request(
            method=request.method,
            url=target,
            params=params,
            json=request.get_json(silent=True),
            data=request.form or None,
            headers=fwd_headers,
            timeout=8
        )
        content_type = resp.headers.get('Content-Type', '')
        if 'text/html' in content_type:
            raise req_lib.exceptions.ConnectionError('API returned HTML — falling back to demo data')
        return Response(
            resp.content,
            status=resp.status_code,
            content_type=resp.headers.get('Content-Type', 'application/json')
        )

    except (req_lib.exceptions.ConnectionError, req_lib.exceptions.Timeout):
        key = path.lower().rstrip('/')
        method = request.method.upper()

        if method == 'POST' and key == 'booking/create':
            return _demo_booking()

        if method == 'GET':
            for route_key, data_fn in DEMO_ROUTES['GET'].items():
                if key == route_key:
                    return jsonify(data_fn())

        return jsonify({"error": "الخادم غير متاح والمسار غير معروف"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── واجهة الإشعارات ────────────────────────────────────────────────────────
@app.route('/api/notifications/<phone>', methods=['GET'])
def get_notifications(phone):
    """جلب إشعارات زبون معين"""
    user_notifications = [n for n in notifications if n['phone'] == phone]
    return jsonify(user_notifications)


@app.route('/api/notifications/<phone>/read', methods=['PUT'])
def mark_notifications_read(phone):
    """تحديد جميع إشعارات الزبون كمقروءة"""
    global notifications
    for n in notifications:
        if n['phone'] == phone:
            n['read'] = True
    return jsonify({"message": "تم تحديث حالة الإشعارات"})


@app.route('/api/estimated-time', methods=['GET'])
def get_estimated_time():
    """جلب الوقت المتوقع من المرآب"""
    estimated_time = get_estimated_time_from_garage()
    return jsonify({"estimatedMinutes": estimated_time})


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

@app.route('/sw.js')
def service_worker():
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')

@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json', mimetype='application/manifest+json')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
