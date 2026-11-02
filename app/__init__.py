import logging
import os
import secrets
from pathlib import Path

from flask import Flask

from . import db, routes


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        DATABASE=os.environ.get("DATABASE_PATH") or str(Path(app.instance_path) / "restaurant.db"),
        KITCHEN_PASSWORD=os.environ.get("KITCHEN_PASSWORD", "kitchen-demo"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config:
        app.config.update(test_config)
    if app.config["KITCHEN_PASSWORD"] == "kitchen-demo" and not app.testing:
        logging.getLogger(__name__).warning("Using the demo kitchen password. Set KITCHEN_PASSWORD for real use.")

    app.teardown_appcontext(db.close_db)
    app.register_blueprint(routes.bp)
    app.jinja_env.filters["money"] = lambda cents: f"${cents / 100:,.2f}"
    with app.app_context():
        db.init_db()
    return app
