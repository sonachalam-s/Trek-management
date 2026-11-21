"""
Trek Management System v2
Full-featured trekking platform with AI suggestions, interactive maps,
image galleries, rest stops & stations, and modern UI.
"""

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, session
)
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = "trek-management-secret-key-change-in-prod-2026"

DATABASE = os.path.join(os.path.dirname(__file__), "trek.db")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            fitness_level TEXT DEFAULT 'intermediate',
            is_admin INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS treks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            location TEXT NOT NULL,
            country TEXT,
            difficulty TEXT NOT NULL,
            duration_days INTEGER NOT NULL,
            distance_km REAL,
            max_elevation_m INTEGER,
            best_season TEXT,
            description TEXT,
            highlights TEXT,
            price_usd REAL DEFAULT 0,
            image_url TEXT,
            lat REAL,
            lng REAL,
            end_lat REAL,
            end_lng REAL,
            is_active INTEGER DEFAULT 1,
            created_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS trek_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trek_id INTEGER NOT NULL,
            image_url TEXT NOT NULL,
            caption TEXT,
            sort_order INTEGER DEFAULT 0,
            FOREIGN KEY (trek_id) REFERENCES treks(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS trek_pois (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trek_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            poi_type TEXT NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            description TEXT,
            FOREIGN KEY (trek_id) REFERENCES treks(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            trek_id INTEGER NOT NULL,
            start_date TEXT,
            status TEXT DEFAULT 'planned',
            notes TEXT,
            created_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (trek_id) REFERENCES treks(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS packing_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            item_name TEXT NOT NULL,
            difficulty_min TEXT DEFAULT 'easy'
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            details TEXT,
            created_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()

    # Seed users
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        pw = generate_password_hash("admin123")
        c.execute(
            "INSERT INTO users (username, email, password_hash, full_name, is_admin, created_at) "
            "VALUES (?, ?, ?, ?, 1, ?)",
            ("admin", "admin@trek.com", pw, "System Admin", datetime.utcnow().isoformat())
        )
        pw2 = generate_password_hash("trekker123")
        c.execute(
            "INSERT INTO users (username, email, password_hash, full_name, fitness_level, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("trekker", "trekker@example.com", pw2, "Alex Trekker", "intermediate",
             datetime.utcnow().isoformat())
        )

    # Seed treks with coordinates + images + POIs
    c.execute("SELECT COUNT(*) FROM treks")
    if c.fetchone()[0] == 0:
        seed = [
            # name, location, country, difficulty, days, distance, elev, season, desc, highlights, price, img, lat, lng, end_lat, end_lng
            ("Everest Base Camp", "Khumbu, Nepal", "Nepal", "hard", 14, 130, 5364,
             "March-May, Sep-Nov",
             "The classic trek to the base of the world's highest mountain. Spectacular views of Everest, Lhotse and Ama Dablam along the Khumbu Valley.",
             "Namche Bazaar, Tengboche Monastery, Kala Patthar sunrise, Everest viewpoint",
             1800, "https://images.unsplash.com/photo-1544735716-392fe2489ffa?w=900",
             27.7172, 86.7278, 28.0026, 86.8528),
            ("Annapurna Circuit", "Annapurna Region, Nepal", "Nepal", "hard", 18, 160, 5416,
             "March-May, Oct-Nov",
             "One of the world's most famous long-distance treks. Cross the Thorong La pass at 5,416 m with dramatic landscape changes.",
             "Thorong La Pass, Manang, Muktinath, diverse landscapes from subtropical to alpine",
             1600, "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=900",
             28.3949, 84.1240, 28.8167, 83.8667),
            ("Langtang Valley", "Langtang National Park, Nepal", "Nepal", "moderate", 8, 60, 4600,
             "March-May, Sep-Nov",
             "Beautiful valley trek with views of Langtang Lirung and rich Tibetan culture in the villages.",
             "Kyanjin Gompa, cheese factory, glacier views, Langtang village",
             900, "https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?w=900",
             28.2100, 85.5200, 28.2135, 85.5667),
            ("Inca Trail to Machu Picchu", "Cusco Region, Peru", "Peru", "moderate", 4, 42, 4215,
             "May-September",
             "The legendary trail ending at the Sun Gate of Machu Picchu. Permits required months in advance.",
             "Dead Woman's Pass, Wiñay Wayna, Sun Gate, Machu Picchu",
             750, "https://images.unsplash.com/photo-1526392060635-9d6019884377?w=900",
             -13.1631, -72.5450, -13.1631, -72.5456),
            ("Torres del Paine W Trek", "Patagonia, Chile", "Chile", "moderate", 5, 71, 1200,
             "November-March",
             "Iconic Patagonian trek featuring granite towers, glaciers and turquoise lakes.",
             "Base of the Towers, Grey Glacier, French Valley, Lake Pehoe",
             600, "https://images.unsplash.com/photo-1516483638261-f4dbaf036963?w=900",
             -51.0000, -73.0000, -50.9423, -73.2468),
            ("Kilimanjaro - Machame Route", "Kilimanjaro National Park, Tanzania", "Tanzania", "hard", 7, 62, 5895,
             "January-March, June-October",
             "Africa's highest peak via the scenic Machame (Whiskey) route through rainforest and alpine desert.",
             "Shira Plateau, Barranco Wall, Uhuru Peak summit, Stella Point",
             2200, "https://images.unsplash.com/photo-1609198092458-38a293c7ac4b?w=900",
             -3.0674, 37.3556, -3.0758, 37.3533),
            ("Tour du Mont Blanc", "Alps (France/Italy/Switzerland)", "France", "moderate", 11, 170, 2665,
             "June-September",
             "Circumnavigate Western Europe's highest mountain through three countries with stunning alpine scenery.",
             "Chamonix, Courmayeur, alpine meadows, mountain huts, Mont Blanc views",
             1400, "https://images.unsplash.com/photo-1486870591958-79fc861a9ba4?w=900",
             45.9237, 6.8694, 45.8326, 6.8652),
            ("GR20 Corsica", "Corsica, France", "France", "hard", 15, 180, 2157,
             "June-September",
             "Often called Europe's toughest long-distance trail. Rugged granite terrain and wild alpine landscapes.",
             "Cirque de la Solitude, alpine lakes, wild camping, granite peaks",
             1100, "https://images.unsplash.com/photo-1551632811-561732d1e306?w=900",
             42.2781, 8.9833, 41.7000, 9.1500),
            ("Jordan Trail - Petra Section", "Southern Jordan", "Jordan", "easy", 5, 75, 1300,
             "March-May, Sep-Nov",
             "Desert trek finishing at the iconic Treasury of Petra through dramatic sandstone canyons.",
             "Little Petra, Siq, Monastery, Bedouin culture, desert landscapes",
             450, "https://images.unsplash.com/photo-1578662996442-48f60103fc96?w=900",
             30.3285, 35.4444, 30.3225, 35.4510),
            ("Himalayan Day Hike - Poon Hill", "Annapurna Region, Nepal", "Nepal", "easy", 3, 25, 3210,
             "Year-round (best Oct-May)",
             "Short and rewarding trek with famous sunrise views of Annapurna and Dhaulagiri ranges.",
             "Ghorepani, Poon Hill sunrise, Gurung villages, mountain panorama",
             250, "https://images.unsplash.com/photo-1486870591958-79fc861a9ba4?w=900",
             28.4000, 83.7000, 28.4005, 83.7010),
            ("Dolomites Alta Via 1", "Dolomites, Italy", "Italy", "moderate", 10, 120, 2750,
             "June-September",
             "Classic high-level route through the dramatic limestone peaks of the Dolomites with excellent rifugios.",
             "Rifugios, via ferrata sections optional, lake views, Cinque Torri",
             1300, "https://images.unsplash.com/photo-1516483638261-f4dbaf036963?w=900",
             46.5000, 12.0000, 46.4100, 11.8500),
            ("Salkantay Trek", "Cusco Region, Peru", "Peru", "moderate", 5, 74, 4600,
             "April-October",
             "Alternative to the Inca Trail with fewer crowds and stunning mountain scenery ending near Machu Picchu.",
             "Salkantay Pass, Humantay Lake, Machu Picchu, cloud forest",
             650, "https://images.unsplash.com/photo-1526392060635-9d6019884377?w=900",
             -13.3333, -72.5500, -13.1631, -72.5456),
        ]
        now = datetime.utcnow().isoformat()
        for t in seed:
            c.execute(
                """INSERT INTO treks
                   (name, location, country, difficulty, duration_days, distance_km,
                    max_elevation_m, best_season, description, highlights, price_usd,
                    image_url, lat, lng, end_lat, end_lng, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (*t, now)
            )

        # Extra gallery images per trek
        gallery = {
            1: [  # EBC
                ("https://images.unsplash.com/photo-1589308078059-be1415eab4c3?w=900", "Khumbu Icefall"),
                ("https://images.unsplash.com/photo-1519904981063-b0cf448d479e?w=900", "Namche Bazaar"),
                ("https://images.unsplash.com/photo-1486870591958-79fc861a9ba4?w=900", "Mountain panorama"),
                ("https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?w=900", "Alpine landscape"),
            ],
            2: [  # Annapurna
                ("https://images.unsplash.com/photo-1551632811-561732d1e306?w=900", "Thorong La area"),
                ("https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=900", "Annapurna range"),
                ("https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?w=900", "Valley views"),
            ],
            3: [  # Langtang
                ("https://images.unsplash.com/photo-1544735716-392fe2489ffa?w=900", "Langtang peaks"),
                ("https://images.unsplash.com/photo-1519904981063-b0cf448d479e?w=900", "Village trail"),
            ],
            4: [  # Inca
                ("https://images.unsplash.com/photo-1587595431973-160d0d94add1?w=900", "Machu Picchu"),
                ("https://images.unsplash.com/photo-1526392060635-9d6019884377?w=900", "Inca ruins"),
                ("https://images.unsplash.com/photo-1531366936337-7c912a4589a7?w=900", "Trail views"),
            ],
            5: [  # Torres
                ("https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=900", "Torres towers"),
                ("https://images.unsplash.com/photo-1516483638261-f4dbaf036963?w=900", "Patagonia lakes"),
            ],
            6: [  # Kili
                ("https://images.unsplash.com/photo-1609198092458-38a293c7ac4b?w=900", "Summit approach"),
                ("https://images.unsplash.com/photo-1544735716-392fe2489ffa?w=900", "Alpine desert"),
            ],
            7: [  # TMB
                ("https://images.unsplash.com/photo-1486870591958-79fc861a9ba4?w=900", "Mont Blanc"),
                ("https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?w=900", "Alpine meadows"),
            ],
            8: [  # GR20
                ("https://images.unsplash.com/photo-1551632811-561732d1e306?w=900", "Corsica granite"),
                ("https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=900", "Ridge walk"),
            ],
            9: [  # Jordan
                ("https://images.unsplash.com/photo-1578662996442-48f60103fc96?w=900", "Petra Treasury"),
                ("https://images.unsplash.com/photo-1548013146-72479768bada?w=900", "Desert canyon"),
            ],
            10: [  # Poon Hill
                ("https://images.unsplash.com/photo-1486870591958-79fc861a9ba4?w=900", "Sunrise viewpoint"),
                ("https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?w=900", "Village path"),
            ],
            11: [  # Dolomites
                ("https://images.unsplash.com/photo-1516483638261-f4dbaf036963?w=900", "Dolomite peaks"),
                ("https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=900", "Rifugio views"),
            ],
            12: [  # Salkantay
                ("https://images.unsplash.com/photo-1526392060635-9d6019884377?w=900", "Salkantay peak"),
                ("https://images.unsplash.com/photo-1587595431973-160d0d94add1?w=900", "Cloud forest"),
            ],
        }
        for trek_id, imgs in gallery.items():
            for i, (url, cap) in enumerate(imgs):
                c.execute(
                    "INSERT INTO trek_images (trek_id, image_url, caption, sort_order) VALUES (?,?,?,?)",
                    (trek_id, url, cap, i)
                )

        # POIs: rest stops, stations, viewpoints, water, lodges
        pois = [
            # EBC
            (1, "Lukla Airport", "station", 27.6870, 86.7314, "Start/end flight hub – Tenzing-Hillary Airport"),
            (1, "Namche Bazaar", "rest", 27.8069, 86.7140, "Main acclimatization stop – shops, cafes, lodges"),
            (1, "Tengboche Monastery", "rest", 27.8361, 86.7642, "Famous monastery & rest point with Everest views"),
            (1, "Dingboche", "rest", 27.8925, 86.8364, "Acclimatization village with teahouses"),
            (1, "Gorak Shep", "rest", 27.9808, 86.8286, "Last settlement before Base Camp"),
            (1, "Everest Base Camp", "viewpoint", 28.0026, 86.8528, "Main destination viewpoint"),
            (1, "Kala Patthar", "viewpoint", 27.9958, 86.8283, "Best sunrise viewpoint of Everest"),
            # Annapurna Circuit
            (2, "Besisahar Bus Station", "station", 28.2300, 84.3800, "Road access & bus terminal"),
            (2, "Chame", "rest", 28.5500, 84.2300, "District HQ – good lodges & rest day option"),
            (2, "Manang", "rest", 28.6667, 84.0167, "Major acclimatization stop"),
            (2, "Thorong Phedi", "rest", 28.7833, 83.9500, "Base before high pass"),
            (2, "Thorong La Pass", "viewpoint", 28.7936, 83.9381, "Highest point 5416 m"),
            (2, "Muktinath", "rest", 28.8167, 83.8667, "Sacred site & rest after pass"),
            # Langtang
            (3, "Syabrubesi", "station", 28.1640, 85.3460, "Road head / bus station"),
            (3, "Lama Hotel", "rest", 28.1750, 85.4500, "Forest rest stop with lodges"),
            (3, "Langtang Village", "rest", 28.2120, 85.5200, "Main village rest point"),
            (3, "Kyanjin Gompa", "rest", 28.2135, 85.5667, "End of valley – cheese factory & views"),
            (3, "Kyanjin Ri", "viewpoint", 28.2200, 85.5750, "Panoramic viewpoint above gompa"),
            # Inca Trail
            (4, "KM 82 Trailhead", "station", -13.2200, -72.5000, "Official Inca Trail start point"),
            (4, "Wayllabamba", "rest", -13.2000, -72.5200, "First campsite & rest"),
            (4, "Dead Woman's Pass", "viewpoint", -13.1800, -72.5300, "Highest point of the trail"),
            (4, "Wiñay Wayna", "rest", -13.1700, -72.5400, "Last campsite before Machu Picchu"),
            (4, "Sun Gate", "viewpoint", -13.1631, -72.5450, "First view of Machu Picchu"),
            # Torres del Paine
            (5, "Laguna Amarga Entrance", "station", -50.9800, -72.8000, "Main park entrance station"),
            (5, "Refugio Chileno", "rest", -50.9500, -72.9500, "Rest & overnight near Base Torres"),
            (5, "Base Torres Viewpoint", "viewpoint", -50.9423, -73.2468, "Iconic towers viewpoint"),
            (5, "Refugio Paine Grande", "rest", -51.0500, -73.1000, "Central rest hub on W trek"),
            (5, "Grey Glacier Viewpoint", "viewpoint", -51.1000, -73.2000, "Glacier viewing platform"),
            # Kilimanjaro
            (6, "Machame Gate", "station", -3.1700, 37.2400, "Trailhead registration station"),
            (6, "Machame Camp", "rest", -3.1200, 37.2800, "First overnight camp"),
            (6, "Shira Camp", "rest", -3.1000, 37.3000, "Plateau rest camp"),
            (6, "Barranco Camp", "rest", -3.0900, 37.3400, "Below the Barranco Wall"),
            (6, "Uhuru Peak", "viewpoint", -3.0758, 37.3533, "Summit of Africa 5895 m"),
            # TMB
            (7, "Chamonix Station", "station", 45.9237, 6.8694, "Main transport hub"),
            (7, "Refuge de la Flegere", "rest", 45.9600, 6.8800, "Mountain hut rest stop"),
            (7, "Courmayeur", "rest", 45.7900, 6.9700, "Italian valley town rest"),
            (7, "Col de la Seigne", "viewpoint", 45.7800, 6.9000, "Border pass viewpoint"),
            # GR20
            (8, "Calenzana", "station", 42.5080, 8.8550, "Northern trailhead"),
            (8, "Refuge de Carozzu", "rest", 42.4000, 8.9000, "Mountain refuge"),
            (8, "Cirque de la Solitude", "viewpoint", 42.2500, 9.0000, "Dramatic rocky amphitheatre"),
            (8, "Conca", "station", 41.7000, 9.1500, "Southern trail end"),
            # Jordan
            (9, "Little Petra", "rest", 30.3700, 35.4500, "Rest & exploration stop"),
            (9, "Siq Entrance", "station", 30.3285, 35.4444, "Main Petra entry corridor"),
            (9, "The Treasury", "viewpoint", 30.3225, 35.4510, "Iconic Al-Khazneh facade"),
            (9, "Monastery (Ad-Deir)", "viewpoint", 30.3300, 35.4400, "Hilltop monastery viewpoint"),
            # Poon Hill
            (10, "Nayapul", "station", 28.2800, 83.7500, "Road head / jeep station"),
            (10, "Tikhedhunga", "rest", 28.3200, 83.7200, "First night stop"),
            (10, "Ghorepani", "rest", 28.4000, 83.7000, "Main village before viewpoint"),
            (10, "Poon Hill Summit", "viewpoint", 28.4005, 83.7010, "Famous sunrise viewpoint 3210 m"),
            # Dolomites
            (11, "Dobbiaco Station", "station", 46.7300, 12.2200, "Train access point"),
            (11, "Rifugio Locatelli", "rest", 46.6200, 12.3000, "Classic mountain hut"),
            (11, "Tre Cime Viewpoint", "viewpoint", 46.6180, 12.3030, "Iconic three peaks view"),
            (11, "Cortina d'Ampezzo", "rest", 46.5400, 12.1400, "Town rest & supplies"),
            # Salkantay
            (12, "Mollepata", "station", -13.3500, -72.5800, "Trailhead access"),
            (12, "Soraypampa", "rest", -13.3400, -72.5600, "Camp near Humantay Lake"),
            (12, "Salkantay Pass", "viewpoint", -13.3333, -72.5500, "High pass 4600 m"),
            (12, "Aguas Calientes", "rest", -13.1547, -72.5254, "Town below Machu Picchu"),
        ]
        for p in pois:
            c.execute(
                "INSERT INTO trek_pois (trek_id, name, poi_type, lat, lng, description) VALUES (?,?,?,?,?,?)",
                p
            )

    # Packing items
    c.execute("SELECT COUNT(*) FROM packing_items")
    if c.fetchone()[0] == 0:
        packing = [
            ("Clothing", "Moisture-wicking base layers", "easy"),
            ("Clothing", "Insulating mid-layer (fleece)", "easy"),
            ("Clothing", "Waterproof hard-shell jacket", "easy"),
            ("Clothing", "Trekking pants (quick-dry)", "easy"),
            ("Clothing", "Warm hat & gloves", "moderate"),
            ("Clothing", "Down jacket", "hard"),
            ("Footwear", "Broken-in hiking boots", "easy"),
            ("Footwear", "Camp shoes / sandals", "easy"),
            ("Footwear", "Wool socks (3-4 pairs)", "easy"),
            ("Gear", "Backpack 40-60L", "easy"),
            ("Gear", "Trekking poles", "easy"),
            ("Gear", "Sleeping bag (rated for altitude)", "moderate"),
            ("Gear", "Headlamp + spare batteries", "easy"),
            ("Gear", "Water bottles / hydration bladder", "easy"),
            ("Gear", "Water purification tablets / filter", "moderate"),
            ("Health", "Personal first-aid kit", "easy"),
            ("Health", "Altitude sickness medication (Diamox)", "hard"),
            ("Health", "Sunscreen SPF 50+", "easy"),
            ("Health", "Blister treatment (Compeed)", "easy"),
            ("Documents", "Passport + permits", "easy"),
            ("Documents", "Travel insurance (helicopter rescue)", "moderate"),
            ("Electronics", "Power bank", "easy"),
            ("Electronics", "Camera / phone", "easy"),
            ("Misc", "Quick-dry towel", "easy"),
            ("Misc", "Snacks / energy bars", "easy"),
        ]
        for cat, name, diff in packing:
            c.execute(
                "INSERT INTO packing_items (category, item_name, difficulty_min) VALUES (?,?,?)",
                (cat, name, diff)
            )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class User(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.username = row["username"]
        self.email = row["email"]
        self.full_name = row["full_name"]
        self.fitness_level = row["fitness_level"]
        self.is_admin = bool(row["is_admin"])


@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return User(row) if row else None


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Admin access required.", "danger")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated


def log_activity(user_id, action, details=""):
    """Record user/admin activity for history."""
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO activity_log (user_id, action, details, created_at) VALUES (?,?,?,?)",
            (user_id, action, details, datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_trek_images(trek_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM trek_images WHERE trek_id = ? ORDER BY sort_order", (trek_id,)
    ).fetchall()
    conn.close()
    return rows


def get_trek_pois(trek_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM trek_pois WHERE trek_id = ? ORDER BY poi_type, name", (trek_id,)
    ).fetchall()
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# AI Recommendation Engine
# ---------------------------------------------------------------------------
DIFFICULTY_SCORE = {"easy": 1, "moderate": 2, "hard": 3}
FITNESS_MAP = {"beginner": 1, "intermediate": 2, "advanced": 3}


def ai_suggest_treks(prefs: dict) -> list:
    conn = get_db()
    treks = conn.execute("SELECT * FROM treks WHERE is_active = 1").fetchall()
    conn.close()

    preferred_diff = prefs.get("difficulty", "moderate")
    max_days = int(prefs.get("max_days", 15))
    min_days = int(prefs.get("min_days", 1))
    fitness = prefs.get("fitness_level", "intermediate")
    preferred_country = (prefs.get("country") or "").strip().lower()
    preferred_season = (prefs.get("season") or "").strip().lower()
    max_budget = float(prefs.get("max_budget", 5000) or 5000)

    fitness_val = FITNESS_MAP.get(fitness, 2)
    results = []
    for t in treks:
        score = 100.0
        reasons = []
        days = t["duration_days"]
        if days < min_days or days > max_days:
            score -= 35
            reasons.append(f"Duration {days}d outside preferred range")
        else:
            score += 10
            reasons.append(f"Duration {days}d fits well")

        trek_diff = DIFFICULTY_SCORE.get(t["difficulty"], 2)
        diff_gap = abs(trek_diff - fitness_val)
        if diff_gap == 0:
            score += 25
            reasons.append("Perfect difficulty match for your fitness")
        elif diff_gap == 1:
            score += 5
            reasons.append("Slightly challenging / easier – good progression")
        else:
            score -= 30
            reasons.append("Difficulty may not match fitness level")

        if t["difficulty"] == preferred_diff:
            score += 15
            reasons.append(f"Matches preferred difficulty ({preferred_diff})")

        if preferred_country and preferred_country in (t["country"] or "").lower():
            score += 20
            reasons.append(f"Located in preferred country: {t['country']}")

        if preferred_season and preferred_season in (t["best_season"] or "").lower():
            score += 12
            reasons.append("Best season aligns with your travel window")

        price = t["price_usd"] or 0
        if price > max_budget:
            score -= 25
            reasons.append(f"Price ${price:.0f} exceeds budget")
        elif price > 0:
            score += 5

        elev = t["max_elevation_m"] or 0
        if fitness == "beginner" and elev > 4000:
            score -= 20
            reasons.append("High altitude – caution for beginners")
        elif fitness == "advanced" and elev > 5000:
            score += 8
            reasons.append("High-altitude challenge suitable for advanced")

        results.append({
            "trek": dict(t),
            "score": round(max(0, min(100, score)), 1),
            "reasons": reasons
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def generate_ai_summary(top_results: list, prefs: dict) -> str:
    if not top_results:
        return "No treks match your current preferences. Try relaxing duration or difficulty filters."
    best = top_results[0]
    t = best["trek"]
    summary = (
        f"Based on your {prefs.get('fitness_level', 'intermediate')} fitness level and preference for a "
        f"{prefs.get('difficulty', 'moderate')} trek lasting up to {prefs.get('max_days', 15)} days, "
        f"I strongly recommend **{t['name']}** in {t['country']}. "
        f"It is a {t['difficulty']} trek of {t['duration_days']} days reaching {t['max_elevation_m']} m. "
        f"Match score: {best['score']}/100. "
    )
    if best["reasons"]:
        summary += "Key reasons: " + "; ".join(best["reasons"][:3]) + ". "
    if len(top_results) > 1:
        alternatives = [r["trek"]["name"] for r in top_results[1:4]]
        summary += f"Strong alternatives: {', '.join(alternatives)}."
    return summary


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    conn = get_db()
    treks = conn.execute(
        "SELECT * FROM treks WHERE is_active = 1 ORDER BY name LIMIT 6"
    ).fetchall()
    total = conn.execute("SELECT COUNT(*) FROM treks WHERE is_active = 1").fetchone()[0]
    conn.close()
    return render_template("index.html", featured=treks, total=total)


@app.route("/treks")
def treks_list():
    q = request.args.get("q", "").strip()
    difficulty = request.args.get("difficulty", "")
    country = request.args.get("country", "")
    max_days = request.args.get("max_days", type=int)

    sql = "SELECT * FROM treks WHERE is_active = 1"
    params = []
    if q:
        sql += " AND (name LIKE ? OR location LIKE ? OR description LIKE ?)"
        params.extend([f"%{q}%"] * 3)
    if difficulty:
        sql += " AND difficulty = ?"
        params.append(difficulty)
    if country:
        sql += " AND country LIKE ?"
        params.append(f"%{country}%")
    if max_days:
        sql += " AND duration_days <= ?"
        params.append(max_days)
    sql += " ORDER BY name"

    conn = get_db()
    treks = conn.execute(sql, params).fetchall()
    countries = [r[0] for r in conn.execute(
        "SELECT DISTINCT country FROM treks WHERE is_active = 1 ORDER BY country"
    ).fetchall()]
    conn.close()
    return render_template(
        "treks.html", treks=treks, q=q, difficulty=difficulty,
        country=country, max_days=max_days or "", countries=countries
    )


@app.route("/trek/<int:trek_id>")
def trek_detail(trek_id):
    conn = get_db()
    trek = conn.execute("SELECT * FROM treks WHERE id = ?", (trek_id,)).fetchone()
    conn.close()
    if not trek:
        flash("Trek not found.", "warning")
        return redirect(url_for("treks_list"))
    images = get_trek_images(trek_id)
    pois = get_trek_pois(trek_id)
    return render_template("trek_detail.html", trek=trek, images=images, pois=pois)


@app.route("/api/trek/<int:trek_id>/map")
def trek_map_data(trek_id):
    """JSON endpoint for map: start/end + POIs"""
    conn = get_db()
    trek = conn.execute("SELECT * FROM treks WHERE id = ?", (trek_id,)).fetchone()
    pois = conn.execute(
        "SELECT * FROM trek_pois WHERE trek_id = ?", (trek_id,)
    ).fetchall()
    conn.close()
    if not trek:
        return jsonify({"error": "not found"}), 404
    return jsonify({
        "trek": {
            "name": trek["name"],
            "lat": trek["lat"],
            "lng": trek["lng"],
            "end_lat": trek["end_lat"],
            "end_lng": trek["end_lng"],
        },
        "pois": [
            {
                "name": p["name"],
                "type": p["poi_type"],
                "lat": p["lat"],
                "lng": p["lng"],
                "description": p["description"] or ""
            }
            for p in pois
        ]
    })


@app.route("/ai-suggest", methods=["GET", "POST"])
def ai_suggest():
    if request.method == "POST":
        prefs = {
            "difficulty": request.form.get("difficulty", "moderate"),
            "min_days": request.form.get("min_days", 1),
            "max_days": request.form.get("max_days", 15),
            "fitness_level": request.form.get("fitness_level", "intermediate"),
            "country": request.form.get("country", ""),
            "season": request.form.get("season", ""),
            "max_budget": request.form.get("max_budget", 5000),
        }
        results = ai_suggest_treks(prefs)
        summary = generate_ai_summary(results, prefs)
        return render_template(
            "ai_suggest.html", results=results[:8], summary=summary,
            prefs=prefs, submitted=True
        )
    default_fitness = current_user.fitness_level if current_user.is_authenticated else "intermediate"
    return render_template(
        "ai_suggest.html", results=None, summary=None,
        prefs={"fitness_level": default_fitness}, submitted=False
    )


@app.route("/api/ai-suggest", methods=["POST"])
def api_ai_suggest():
    data = request.get_json() or {}
    results = ai_suggest_treks(data)
    summary = generate_ai_summary(results, data)
    return jsonify({
        "summary": summary,
        "recommendations": [
            {
                "id": r["trek"]["id"],
                "name": r["trek"]["name"],
                "score": r["score"],
                "difficulty": r["trek"]["difficulty"],
                "duration_days": r["trek"]["duration_days"],
                "country": r["trek"]["country"],
                "reasons": r["reasons"]
            }
            for r in results[:5]
        ]
    })


@app.route("/packing/<int:trek_id>")
@login_required
def packing_list(trek_id):
    conn = get_db()
    trek = conn.execute("SELECT * FROM treks WHERE id = ?", (trek_id,)).fetchone()
    if not trek:
        flash("Trek not found.", "warning")
        return redirect(url_for("treks_list"))
    diff_order = {"easy": 1, "moderate": 2, "hard": 3}
    trek_level = diff_order.get(trek["difficulty"], 2)
    items = conn.execute("SELECT * FROM packing_items ORDER BY category, item_name").fetchall()
    conn.close()
    filtered = [i for i in items if diff_order.get(i["difficulty_min"], 1) <= trek_level]
    grouped = {}
    for item in filtered:
        grouped.setdefault(item["category"], []).append(item["item_name"])
    return render_template("packing.html", trek=trek, grouped=grouped)


@app.route("/book/<int:trek_id>", methods=["GET", "POST"])
@login_required
def book_trek(trek_id):
    conn = get_db()
    trek = conn.execute("SELECT * FROM treks WHERE id = ?", (trek_id,)).fetchone()
    if not trek:
        flash("Trek not found.", "warning")
        return redirect(url_for("treks_list"))

    if request.method == "POST":
        start_date = request.form.get("start_date")
        notes = request.form.get("notes", "")
        conn.execute(
            "INSERT INTO bookings (user_id, trek_id, start_date, status, notes, created_at) "
            "VALUES (?, ?, ?, 'planned', ?, ?)",
            (current_user.id, trek_id, start_date, notes, datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()
        log_activity(current_user.id, "booking_created",
                     f"Booked trek: {trek['name']} (start: {start_date})")
        flash(f"Successfully added '{trek['name']}' to your treks!", "success")
        return redirect(url_for("my_treks"))

    conn.close()
    images = get_trek_images(trek_id)
    pois = get_trek_pois(trek_id)
    return render_template("book.html", trek=trek, images=images, pois=pois)


@app.route("/my-treks")
@login_required
def my_treks():
    conn = get_db()
    bookings = conn.execute(
        """SELECT b.*, t.name, t.location, t.difficulty, t.duration_days, t.image_url
           FROM bookings b JOIN treks t ON b.trek_id = t.id
           WHERE b.user_id = ? ORDER BY b.created_at DESC""",
        (current_user.id,)
    ).fetchall()
    conn.close()
    return render_template("my_treks.html", bookings=bookings)


@app.route("/booking/<int:booking_id>/status", methods=["POST"])
@login_required
def update_booking_status(booking_id):
    status = request.form.get("status")
    if status not in ("planned", "confirmed", "completed", "cancelled"):
        flash("Invalid status.", "danger")
        return redirect(url_for("my_treks"))
    conn = get_db()
    conn.execute(
        "UPDATE bookings SET status = ? WHERE id = ? AND user_id = ?",
        (status, booking_id, current_user.id)
    )
    conn.commit()
    conn.close()
    log_activity(current_user.id, "booking_status",
                 f"Booking #{booking_id} status → {status}")
    flash("Status updated.", "success")
    return redirect(url_for("my_treks"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        full_name = request.form.get("full_name", "").strip()
        fitness = request.form.get("fitness_level", "intermediate")
        if not username or not email or not password:
            flash("All fields are required.", "danger")
            return render_template("register.html")
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO users (username, email, password_hash, full_name, fitness_level, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (username, email, generate_password_hash(password), full_name, fitness,
                 datetime.utcnow().isoformat())
            )
            conn.commit()
            uid_row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            conn.close()
            if uid_row:
                log_activity(uid_row[0], "register", f"New account: {username}")
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            conn.close()
            flash("Username or email already exists.", "danger")
            return render_template("register.html")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """User login – regular trekkers only (admins should use /admin/login)."""
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("user_dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? OR email = ?", (username, username)
        ).fetchone()
        conn.close()
        if row and check_password_hash(row["password_hash"], password):
            user = User(row)
            if user.is_admin:
                flash("Please use the Admin Login portal.", "warning")
                return redirect(url_for("admin_login"))
            login_user(user)
            log_activity(user.id, "login", f"User login: {user.username}")
            flash(f"Welcome back, {user.full_name or user.username}!", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("user_dashboard"))
        flash("Invalid username or password.", "danger")
    return render_template("login_user.html")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """Dedicated Admin login portal."""
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("admin_dashboard"))
        flash("You are logged in as a regular user. Logout first to access admin.", "info")
        return redirect(url_for("user_dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? OR email = ?", (username, username)
        ).fetchone()
        conn.close()
        if row and check_password_hash(row["password_hash"], password):
            user = User(row)
            if not user.is_admin:
                flash("Access denied. This portal is for administrators only.", "danger")
                return render_template("login_admin.html")
            login_user(user)
            log_activity(user.id, "admin_login", f"Admin login: {user.username}")
            flash(f"Welcome, Admin {user.full_name or user.username}!", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Invalid admin credentials.", "danger")
    return render_template("login_admin.html")


@app.route("/dashboard")
@login_required
def user_dashboard():
    """User dashboard with all trekker features at a glance."""
    if current_user.is_admin:
        return redirect(url_for("admin_dashboard"))
    conn = get_db()
    bookings = conn.execute(
        """SELECT b.*, t.name, t.location, t.difficulty, t.duration_days, t.image_url, t.country
           FROM bookings b JOIN treks t ON b.trek_id = t.id
           WHERE b.user_id = ? ORDER BY b.created_at DESC LIMIT 8""",
        (current_user.id,)
    ).fetchall()
    all_bookings = conn.execute(
        "SELECT status FROM bookings WHERE user_id = ?", (current_user.id,)
    ).fetchall()
    stats = {
        "total": len(all_bookings),
        "planned": sum(1 for b in all_bookings if b["status"] == "planned"),
        "confirmed": sum(1 for b in all_bookings if b["status"] == "confirmed"),
        "completed": sum(1 for b in all_bookings if b["status"] == "completed"),
        "cancelled": sum(1 for b in all_bookings if b["status"] == "cancelled"),
    }
    featured = conn.execute(
        "SELECT * FROM treks WHERE is_active = 1 ORDER BY name LIMIT 4"
    ).fetchall()
    recent_activity = conn.execute(
        """SELECT * FROM activity_log WHERE user_id = ?
           ORDER BY created_at DESC LIMIT 8""",
        (current_user.id,)
    ).fetchall()
    total_treks = conn.execute("SELECT COUNT(*) FROM treks WHERE is_active = 1").fetchone()[0]
    conn.close()
    return render_template(
        "dashboard_user.html",
        bookings=bookings, stats=stats, featured=featured,
        recent_activity=recent_activity, total_treks=total_treks
    )


@app.route("/logout")
@login_required
def logout():
    was_admin = current_user.is_admin
    log_activity(current_user.id, "logout", f"Logged out: {current_user.username}")
    logout_user()
    flash("You have been logged out.", "info")
    if was_admin:
        return redirect(url_for("admin_login"))
    return redirect(url_for("login"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        fitness = request.form.get("fitness_level", "intermediate")
        conn = get_db()
        conn.execute(
            "UPDATE users SET full_name = ?, fitness_level = ? WHERE id = ?",
            (full_name, fitness, current_user.id)
        )
        conn.commit()
        conn.close()
        flash("Profile updated.", "success")
        return redirect(url_for("profile"))
    return render_template("profile.html")


@app.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    conn = get_db()
    treks = conn.execute("SELECT * FROM treks ORDER BY name").fetchall()
    users = conn.execute(
        "SELECT id, username, email, full_name, is_admin, fitness_level, created_at FROM users"
    ).fetchall()
    bookings = conn.execute(
        """SELECT b.id, b.status, b.start_date, b.created_at, u.username, t.name
           FROM bookings b
           JOIN users u ON b.user_id = u.id
           JOIN treks t ON b.trek_id = t.id
           ORDER BY b.created_at DESC LIMIT 20"""
    ).fetchall()
    all_b = conn.execute("SELECT status FROM bookings").fetchall()
    activity_count = conn.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
    recent_activity = conn.execute(
        """SELECT a.*, u.username FROM activity_log a
           LEFT JOIN users u ON a.user_id = u.id
           ORDER BY a.created_at DESC LIMIT 10"""
    ).fetchall()
    stats = {
        "treks": len(treks),
        "active_treks": sum(1 for t in treks if t["is_active"]),
        "users": len(users),
        "admins": sum(1 for u in users if u["is_admin"]),
        "bookings": len(all_b),
        "planned": sum(1 for b in all_b if b["status"] == "planned"),
        "confirmed": sum(1 for b in all_b if b["status"] == "confirmed"),
        "completed": sum(1 for b in all_b if b["status"] == "completed"),
        "cancelled": sum(1 for b in all_b if b["status"] == "cancelled"),
        "activities": activity_count,
    }
    conn.close()
    return render_template(
        "dashboard_admin.html",
        treks=treks, users=users, bookings=bookings,
        stats=stats, recent_activity=recent_activity
    )


@app.route("/admin/trek/add", methods=["GET", "POST"])
@login_required
@admin_required
def admin_add_trek():
    if request.method == "POST":
        conn = get_db()
        conn.execute(
            """INSERT INTO treks
               (name, location, country, difficulty, duration_days, distance_km,
                max_elevation_m, best_season, description, highlights, price_usd,
                image_url, lat, lng, end_lat, end_lng, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                request.form["name"], request.form["location"],
                request.form.get("country", ""), request.form["difficulty"],
                int(request.form["duration_days"]),
                float(request.form.get("distance_km") or 0),
                int(request.form.get("max_elevation_m") or 0),
                request.form.get("best_season", ""),
                request.form.get("description", ""),
                request.form.get("highlights", ""),
                float(request.form.get("price_usd") or 0),
                request.form.get("image_url", ""),
                float(request.form.get("lat") or 0) or None,
                float(request.form.get("lng") or 0) or None,
                float(request.form.get("end_lat") or 0) or None,
                float(request.form.get("end_lng") or 0) or None,
                datetime.utcnow().isoformat()
            )
        )
        conn.commit()
        conn.close()
        flash("Trek added successfully.", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_trek_form.html", trek=None)


@app.route("/admin/trek/<int:trek_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def admin_edit_trek(trek_id):
    conn = get_db()
    trek = conn.execute("SELECT * FROM treks WHERE id = ?", (trek_id,)).fetchone()
    if not trek:
        flash("Trek not found.", "warning")
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        conn.execute(
            """UPDATE treks SET
               name=?, location=?, country=?, difficulty=?, duration_days=?,
               distance_km=?, max_elevation_m=?, best_season=?, description=?,
               highlights=?, price_usd=?, image_url=?, lat=?, lng=?,
               end_lat=?, end_lng=?, is_active=?
               WHERE id=?""",
            (
                request.form["name"], request.form["location"],
                request.form.get("country", ""), request.form["difficulty"],
                int(request.form["duration_days"]),
                float(request.form.get("distance_km") or 0),
                int(request.form.get("max_elevation_m") or 0),
                request.form.get("best_season", ""),
                request.form.get("description", ""),
                request.form.get("highlights", ""),
                float(request.form.get("price_usd") or 0),
                request.form.get("image_url", ""),
                float(request.form.get("lat") or 0) or None,
                float(request.form.get("lng") or 0) or None,
                float(request.form.get("end_lat") or 0) or None,
                float(request.form.get("end_lng") or 0) or None,
                1 if request.form.get("is_active") else 0,
                trek_id
            )
        )
        conn.commit()
        conn.close()
        flash("Trek updated.", "success")
        return redirect(url_for("admin_dashboard"))
    conn.close()
    return render_template("admin_trek_form.html", trek=trek)


@app.route("/admin/trek/<int:trek_id>/delete", methods=["POST"])
@login_required
@admin_required
def admin_delete_trek(trek_id):
    conn = get_db()
    conn.execute("UPDATE treks SET is_active = 0 WHERE id = ?", (trek_id,))
    conn.commit()
    conn.close()
    flash("Trek deactivated.", "info")
    return redirect(url_for("admin_dashboard"))


# ---- User History ----
@app.route("/history")
@login_required
def user_history():
    """Full history for the current user: bookings + activity log."""
    conn = get_db()
    bookings = conn.execute(
        """SELECT b.*, t.name, t.location, t.difficulty, t.duration_days, t.image_url, t.country
           FROM bookings b JOIN treks t ON b.trek_id = t.id
           WHERE b.user_id = ? ORDER BY b.created_at DESC""",
        (current_user.id,)
    ).fetchall()
    activities = conn.execute(
        """SELECT * FROM activity_log WHERE user_id = ?
           ORDER BY created_at DESC LIMIT 100""",
        (current_user.id,)
    ).fetchall()
    # Stats
    stats = {
        "total": len(bookings),
        "completed": sum(1 for b in bookings if b["status"] == "completed"),
        "planned": sum(1 for b in bookings if b["status"] == "planned"),
        "confirmed": sum(1 for b in bookings if b["status"] == "confirmed"),
        "cancelled": sum(1 for b in bookings if b["status"] == "cancelled"),
    }
    conn.close()
    return render_template("history.html", bookings=bookings, activities=activities, stats=stats)


# ---- Admin: full controls ----
@app.route("/admin/bookings")
@login_required
@admin_required
def admin_bookings():
    conn = get_db()
    bookings = conn.execute(
        """SELECT b.*, u.username, u.email, t.name as trek_name, t.difficulty, t.duration_days
           FROM bookings b
           JOIN users u ON b.user_id = u.id
           JOIN treks t ON b.trek_id = t.id
           ORDER BY b.created_at DESC"""
    ).fetchall()
    conn.close()
    return render_template("admin_bookings.html", bookings=bookings)


@app.route("/admin/booking/<int:booking_id>/status", methods=["POST"])
@login_required
@admin_required
def admin_update_booking(booking_id):
    status = request.form.get("status")
    if status not in ("planned", "confirmed", "completed", "cancelled"):
        flash("Invalid status.", "danger")
        return redirect(url_for("admin_bookings"))
    conn = get_db()
    row = conn.execute("SELECT user_id FROM bookings WHERE id=?", (booking_id,)).fetchone()
    conn.execute("UPDATE bookings SET status = ? WHERE id = ?", (status, booking_id))
    conn.commit()
    conn.close()
    if row:
        log_activity(current_user.id, "admin_booking_status",
                     f"Admin set booking #{booking_id} → {status}")
    flash("Booking status updated by admin.", "success")
    return redirect(url_for("admin_bookings"))


@app.route("/admin/booking/<int:booking_id>/delete", methods=["POST"])
@login_required
@admin_required
def admin_delete_booking(booking_id):
    conn = get_db()
    conn.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
    conn.commit()
    conn.close()
    log_activity(current_user.id, "admin_booking_delete", f"Deleted booking #{booking_id}")
    flash("Booking deleted.", "info")
    return redirect(url_for("admin_bookings"))


@app.route("/admin/users")
@login_required
@admin_required
def admin_users():
    conn = get_db()
    users = conn.execute(
        """SELECT u.*,
           (SELECT COUNT(*) FROM bookings b WHERE b.user_id = u.id) as booking_count
           FROM users u ORDER BY u.created_at DESC"""
    ).fetchall()
    conn.close()
    return render_template("admin_users.html", users=users)


@app.route("/admin/user/<int:user_id>/toggle-admin", methods=["POST"])
@login_required
@admin_required
def admin_toggle_admin(user_id):
    if user_id == current_user.id:
        flash("You cannot change your own admin status.", "warning")
        return redirect(url_for("admin_users"))
    conn = get_db()
    row = conn.execute("SELECT is_admin, username FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        flash("User not found.", "danger")
        return redirect(url_for("admin_users"))
    new_val = 0 if row["is_admin"] else 1
    conn.execute("UPDATE users SET is_admin = ? WHERE id = ?", (new_val, user_id))
    conn.commit()
    conn.close()
    log_activity(current_user.id, "admin_toggle",
                 f"{'Granted' if new_val else 'Revoked'} admin for {row['username']}")
    flash(f"Admin status updated for {row['username']}.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/user/<int:user_id>/history")
@login_required
@admin_required
def admin_user_history(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        flash("User not found.", "warning")
        return redirect(url_for("admin_users"))
    bookings = conn.execute(
        """SELECT b.*, t.name, t.location, t.difficulty, t.duration_days, t.image_url, t.country
           FROM bookings b JOIN treks t ON b.trek_id = t.id
           WHERE b.user_id = ? ORDER BY b.created_at DESC""",
        (user_id,)
    ).fetchall()
    activities = conn.execute(
        """SELECT * FROM activity_log WHERE user_id = ?
           ORDER BY created_at DESC LIMIT 150""",
        (user_id,)
    ).fetchall()
    stats = {
        "total": len(bookings),
        "completed": sum(1 for b in bookings if b["status"] == "completed"),
        "planned": sum(1 for b in bookings if b["status"] == "planned"),
        "confirmed": sum(1 for b in bookings if b["status"] == "confirmed"),
        "cancelled": sum(1 for b in bookings if b["status"] == "cancelled"),
    }
    conn.close()
    return render_template("history.html", bookings=bookings, activities=activities,
                           stats=stats, viewed_user=user, is_admin_view=True)


@app.route("/admin/activity")
@login_required
@admin_required
def admin_activity():
    conn = get_db()
    activities = conn.execute(
        """SELECT a.*, u.username
           FROM activity_log a
           LEFT JOIN users u ON a.user_id = u.id
           ORDER BY a.created_at DESC LIMIT 200"""
    ).fetchall()
    conn.close()
    return render_template("admin_activity.html", activities=activities)


@app.route("/admin/trek/<int:trek_id>/delete-hard", methods=["POST"])
@login_required
@admin_required
def admin_hard_delete_trek(trek_id):
    """Permanently remove trek + related images/pois/bookings."""
    conn = get_db()
    conn.execute("DELETE FROM trek_images WHERE trek_id=?", (trek_id,))
    conn.execute("DELETE FROM trek_pois WHERE trek_id=?", (trek_id,))
    conn.execute("DELETE FROM bookings WHERE trek_id=?", (trek_id,))
    conn.execute("DELETE FROM treks WHERE id=?", (trek_id,))
    conn.commit()
    conn.close()
    log_activity(current_user.id, "admin_trek_delete", f"Hard-deleted trek #{trek_id}")
    flash("Trek permanently deleted.", "info")
    return redirect(url_for("admin_dashboard"))



if __name__ == "__main__":
    init_db()
    print("=" * 60)
    print("  TREK MANAGEMENT SYSTEM v2")
    print("  http://127.0.0.1:5000")
    print("  Admin  : admin / admin123")
    print("  User   : trekker / trekker123")
    print("=" * 60)
    app.run(debug=True, host="0.0.0.0", port=5000)
