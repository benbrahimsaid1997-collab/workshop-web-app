# ورشة السيارات - Car Workshop PWA

## Overview
A Flask-based Arabic Progressive Web App (PWA) for a car workshop. Connects to an external API
(the user's Windows machine running at port 5001) and is installable on Android and iOS.

## Features
- **المرايب:** Live garage bay status fetched from API
- **المنشورات:** Posts with text, images, and video links
- **المنتجات:** Product catalog with prices and availability
- **حجز موعد:** Appointment booking form submitted to API
- **إعدادات الاتصال:** Configure API base URL (stored in localStorage)
- **PWA:** Installable on Android (Add to Home Screen) and iOS (Safari > Share > Add to Home Screen)
- **Offline support:** Service worker caches pages, API calls degrade gracefully

## Architecture
- **Framework:** Flask (Python 3.11)
- **Frontend:** Server-rendered HTML + vanilla JS; all API calls made client-side (browser → API)
- **API URL:** Configurable via the Settings page, stored in `localStorage` as `workshop_api_url`
- **Default API URL:** `http://localhost:5001/api`
- **PWA Assets:** `static/manifest.json`, `static/sw.js`, `static/icon-192.png`, `static/icon-512.png`

## File Structure
```
main.py                   # Flask app — page routes only
templates/
  base.html               # RTL Arabic base layout, service worker registration, apiFetch() helper
  index.html              # Main menu + API connectivity indicator
  garages.html            # Garage status (client-side fetch)
  posts.html              # Posts/announcements (client-side fetch)
  products.html           # Products catalog (client-side fetch)
  booking.html            # Booking form (submits to API)
  settings.html           # API URL configuration + connection test
static/
  manifest.json           # PWA manifest
  sw.js                   # Service worker
  icon-192.png            # PWA icon
  icon-512.png            # PWA icon
```

## Running
```bash
python main.py
```
Starts on port 5000.

## Connecting to Real API (Same WiFi)
1. Find Windows IP: run `ipconfig` in CMD (e.g. `192.168.1.15`)
2. Open the app → Settings → enter `http://192.168.1.15:5001/api`
3. Allow port 5001 through Windows Firewall
4. Test connection from the Settings page

## Installing as PWA
- **Android:** Chrome → ⋮ menu → "Add to Home Screen"
- **iOS:** Safari → Share icon → "Add to Home Screen"
