import sqlite3
from pathlib import Path

from flask import current_app, g

MENU = [
    ("Margherita Pizza", "Tomato, mozzarella and fresh basil on a thin crust.", "Mains", 1199),
    ("Paneer Tikka Wrap", "Grilled paneer, peppers and mint chutney in a warm wrap.", "Mains", 1049),
    ("Chicken Burrito Bowl", "Rice, black beans, grilled chicken, salsa and lime crema.", "Mains", 1299),
    ("Garden Salad", "Mixed greens, cucumber, cherry tomatoes and lemon vinaigrette.", "Sides", 699),
    ("Masala Fries", "Crispy fries tossed in a house spice blend.", "Sides", 549),
    ("Garlic Bread", "Toasted ciabatta with garlic butter and herbs.", "Sides", 499),
    ("Mango Lassi", "Chilled yoghurt drink blended with mango.", "Drinks", 449),
    ("Iced Lemon Tea", "Freshly brewed black tea with lemon.", "Drinks", 349),
    ("Chocolate Brownie", "Warm brownie with a scoop of vanilla ice cream.", "Desserts", 599),
]


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    """Create tables and seed the menu on first run. Safe to call on every start."""
    db = get_db()
    db.executescript((Path(__file__).parent / "schema.sql").read_text())
    if db.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0] == 0:
        db.executemany("INSERT INTO menu_items (name, description, category, price_cents) VALUES (?, ?, ?, ?)", MENU)
    db.commit()
