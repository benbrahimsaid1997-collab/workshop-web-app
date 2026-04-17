# -*- coding: utf-8 -*-
"""
تطبيق ورشة السيارات - نسخة الويب PWA
"""

from flask import Flask, render_template, send_from_directory, request, jsonify, Response
import requests as req_lib
import os
import json
from datetime import datetime

app = Flask(__name__)

NGROK_URL = os.environ.get('NGROK_URL', 'https://curling-underwear-bubble.ngrok-free.dev')
API_BASE  = os.environ.get('API_BASE',  f'{NGROK_URL}/api')

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
    waiting_number = len(_bookings) + 1
    people_ahead   = len([b for b in _bookings if b.get('date') == date])
    _bookings.append({"customerName": name, "customerPhone": phone,
                      "service": service, "date": date, "time": time})
    return jsonify({
        "Message":       "تم تأكيد حجزك بنجاح! (بيانات تجريبية)",
        "WaitingNumber": waiting_number,
        "PeopleAhead":   people_ahead,
        "EstimatedTime": f"{people_ahead * 30} دقيقة"
    })


# ─── Proxy ────────────────────────────────────────────────────────────────────
@app.route('/api/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE'])
@app.route('/api/<path:path>',            methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy(path):
    target = f"{API_BASE}/{path}"
    try:
        fwd_headers = {k: v for k, v in request.headers if k.lower() != 'host'}
        fwd_headers['ngrok-skip-browser-warning'] = 'true'
        fwd_headers['User-Agent'] = 'WorkshopApp/1.0'
        # merge any existing query params plus the ngrok bypass param
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
        # if the response is HTML (ngrok warning page or error page), fall back to demo
        content_type = resp.headers.get('Content-Type', '')
        if 'text/html' in content_type:
            raise req_lib.exceptions.ConnectionError('API returned HTML — falling back to demo data')

        # rewrite localhost URLs in JSON responses to go through our /media proxy
        # so images/videos load correctly (browser can't add headers to <img> tags)
        body = resp.content
        if 'application/json' in content_type:
            body = body.replace(b'http://localhost:5001', b'/media')

        return Response(
            body,
            status=resp.status_code,
            content_type=content_type or 'application/json'
        )

    except (req_lib.exceptions.ConnectionError, req_lib.exceptions.Timeout):
        # الـ API غير متاح — استخدم البيانات التجريبية
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


# ─── Media proxy (images / videos from the API server) ───────────────────────
@app.route('/media/<path:path>')
def media_proxy(path):
    url = f"{NGROK_URL}/{path}"
    try:
        r = req_lib.get(
            url,
            headers={'ngrok-skip-browser-warning': 'true', 'User-Agent': 'WorkshopApp/1.0'},
            timeout=10,
            stream=True
        )
        ct = r.headers.get('Content-Type', 'application/octet-stream')
        return Response(r.content, status=r.status_code, content_type=ct)
    except Exception:
        return '', 404


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
