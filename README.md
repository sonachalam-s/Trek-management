# Trek Management System (TrekMS)

A full-featured **Trekking Management System** with an intelligent **AI Recommendation Engine**.

## Features

### Core
- **User registration & login** (Flask-Login + hashed passwords)
- **Trek catalog** – search, filter by difficulty / country / duration
- **Detailed trek pages** – elevation, distance, best season, highlights, images
- **Booking system** – add treks to “My Treks”, update status (planned → confirmed → completed)
- **Smart packing lists** – auto-generated based on trek difficulty
- **User profile** – fitness level used by the AI engine
- **Admin dashboard** – manage treks, view users & bookings

### AI Best Suggestion Engine
- Multi-factor scoring (difficulty vs fitness, duration, country, season, budget, altitude safety)
- Natural-language recommendation summary
- Ranked results with transparent reasons
- JSON API endpoint (`POST /api/ai-suggest`) for integration

## Quick Start

```bash
cd trek_management_system
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000**

### Demo Accounts
| Role  | Username | Password    |
|-------|----------|-------------|
| Admin | admin    | admin123    |
| User  | trekker  | trekker123  |

## Seed Data
12 famous treks are pre-loaded:
- Everest Base Camp, Annapurna Circuit, Langtang Valley (Nepal)
- Inca Trail, Salkantay (Peru)
- Torres del Paine W (Chile)
- Kilimanjaro Machame (Tanzania)
- Tour du Mont Blanc, GR20 Corsica (Europe)
- Jordan Trail – Petra, Dolomites Alta Via 1, Poon Hill

## Project Structure
```
trek_management_system/
├── app.py                 # Main application + AI engine
├── requirements.txt
├── trek.db                # SQLite (created on first run)
├── static/css/style.css
└── templates/             # Jinja2 + Bootstrap 5 UI
```

## API Example
```bash
curl -X POST http://127.0.0.1:5000/api/ai-suggest \
  -H "Content-Type: application/json" \
  -d '{
    "fitness_level": "intermediate",
    "difficulty": "moderate",
    "min_days": 4,
    "max_days": 10,
    "country": "Nepal",
    "max_budget": 1500
  }'
```

## Tech Stack
- Python 3 + Flask
- SQLite
- Bootstrap 5 + Bootstrap Icons
- Rule-based AI scoring engine (extendable to real LLM later)

---
Built for trekkers, by trekkers. Plan. Trek. Conquer.
