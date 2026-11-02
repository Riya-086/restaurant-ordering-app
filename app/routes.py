import hmac
import re
import secrets
from datetime import UTC, datetime
from functools import wraps

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for

from .db import get_db

bp = Blueprint("shop", __name__)

MAX_QTY = 20
STATUS_FLOW = {"received": "preparing", "preparing": "ready", "ready": "collected"}
STATUS_LABELS = {
    "received": "Received",
    "preparing": "Being prepared",
    "ready": "Ready for pickup",
    "collected": "Collected",
    "cancelled": "Cancelled",
}


# ---------- CSRF protection for every form post ----------
@bp.app_context_processor
def inject_globals():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return {
        "csrf_token": session["csrf"],
        "cart_count": sum(session.get("cart", {}).values()),
        "status_labels": STATUS_LABELS,
    }


@bp.before_app_request
def check_csrf():
    if request.method == "POST":
        sent = request.form.get("csrf", "")
        if not sent or not hmac.compare_digest(sent, session.get("csrf", "")):
            abort(400, "Invalid or missing form token. Reload the page and try again.")


# ---------- cart helpers ----------
def _cart() -> dict[str, int]:
    return session.setdefault("cart", {})


def _cart_lines():
    cart = _cart()
    if not cart:
        return [], 0
    rows = (
        get_db()
        .execute(f"SELECT * FROM menu_items WHERE available = 1 AND id IN ({','.join('?' * len(cart))})", list(cart))
        .fetchall()
    )
    lines = [{"item": r, "qty": cart[str(r["id"])], "subtotal": r["price_cents"] * cart[str(r["id"])]} for r in rows]
    return lines, sum(line["subtotal"] for line in lines)


def _quantity(raw: str | None) -> int:
    try:
        return int(raw or "")
    except ValueError:
        abort(400, "Quantity must be a whole number.")


# ---------- customer pages ----------
@bp.get("/")
def menu():
    items = get_db().execute("SELECT * FROM menu_items WHERE available = 1 ORDER BY category, name").fetchall()
    categories: dict[str, list] = {}
    for item in items:
        categories.setdefault(item["category"], []).append(item)
    return render_template("menu.html", categories=categories)


@bp.post("/cart/add")
def add_to_cart():
    item_id = request.form.get("item_id", "")
    qty = _quantity(request.form.get("quantity", "1"))
    item = get_db().execute("SELECT name FROM menu_items WHERE id = ? AND available = 1", (item_id,)).fetchone()
    if item is None:
        abort(404, "That item is not on the menu.")
    cart = _cart()
    cart[item_id] = min(cart.get(item_id, 0) + max(qty, 1), MAX_QTY)
    session.modified = True
    flash(f"Added {item['name']} to your order.")
    return redirect(url_for("shop.menu"))


@bp.get("/cart")
def cart():
    lines, total = _cart_lines()
    return render_template("cart.html", lines=lines, total=total, max_qty=MAX_QTY)


@bp.post("/cart/update")
def update_cart():
    cart = _cart()
    for key, value in request.form.items():
        if key.startswith("qty-"):
            item_id, qty = key[4:], _quantity(value)
            if qty <= 0:
                cart.pop(item_id, None)
            else:
                cart[item_id] = min(qty, MAX_QTY)
    session.modified = True
    return redirect(url_for("shop.cart"))


@bp.route("/checkout", methods=["GET", "POST"])
def checkout():
    lines, total = _cart_lines()
    if not lines:
        flash("Your order is empty.")
        return redirect(url_for("shop.menu"))
    errors, form = {}, {"name": "", "phone": "", "notes": ""}
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in form}
        digits = re.sub(r"[\s()+.-]", "", form["phone"])
        if not 2 <= len(form["name"]) <= 60:
            errors["name"] = "Enter a name between 2 and 60 characters."
        if not (digits.isdigit() and 7 <= len(digits) <= 15):
            errors["phone"] = "Enter a phone number with 7 to 15 digits."
        if len(form["notes"]) > 200:
            errors["notes"] = "Notes can be at most 200 characters."
        if not errors:
            code = _place_order(form, lines, total)
            session.pop("cart", None)
            return redirect(url_for("shop.order_status", code=code))
    return render_template("checkout.html", lines=lines, total=total, form=form, errors=errors), 400 if errors else 200


def _place_order(form: dict, lines: list, total: int) -> str:
    db = get_db()
    code = secrets.token_hex(3).upper()
    with db:  # one transaction: the order and all its lines, or nothing
        cur = db.execute(
            "INSERT INTO orders (code, customer_name, phone, notes, total_cents, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (code, form["name"], form["phone"], form["notes"], total, datetime.now(UTC).isoformat(timespec="seconds")),
        )
        db.executemany(
            "INSERT INTO order_items (order_id, menu_item_id, name, unit_price_cents, quantity) VALUES (?, ?, ?, ?, ?)",
            [
                (cur.lastrowid, ln["item"]["id"], ln["item"]["name"], ln["item"]["price_cents"], ln["qty"])
                for ln in lines
            ],
        )
    return code


@bp.get("/orders/<code>")
def order_status(code: str):
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE code = ?", (code.upper(),)).fetchone()
    if order is None:
        abort(404, "We couldn't find that order.")
    items = db.execute("SELECT * FROM order_items WHERE order_id = ?", (order["id"],)).fetchall()
    return render_template("order.html", order=order, items=items)


# ---------- kitchen dashboard ----------
def kitchen_only(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("kitchen"):
            return redirect(url_for("shop.kitchen_login"))
        return view(*args, **kwargs)

    return wrapped


@bp.route("/kitchen/login", methods=["GET", "POST"])
def kitchen_login():
    error = None
    if request.method == "POST":
        if hmac.compare_digest(request.form.get("password", ""), current_app.config["KITCHEN_PASSWORD"]):
            session["kitchen"] = True
            return redirect(url_for("shop.kitchen"))
        error = "Incorrect password."
    return render_template("login.html", error=error), 401 if error else 200


@bp.post("/kitchen/logout")
def kitchen_logout():
    session.pop("kitchen", None)
    return redirect(url_for("shop.menu"))


@bp.get("/kitchen")
@kitchen_only
def kitchen():
    db = get_db()
    orders = db.execute(
        "SELECT * FROM orders WHERE status NOT IN ('collected', 'cancelled') ORDER BY created_at, id"
    ).fetchall()
    items = {o["id"]: db.execute("SELECT * FROM order_items WHERE order_id = ?", (o["id"],)).fetchall() for o in orders}
    return render_template("kitchen.html", orders=orders, items=items, flow=STATUS_FLOW)


@bp.post("/kitchen/orders/<int:order_id>/status")
@kitchen_only
def change_status(order_id: int):
    db = get_db()
    order = db.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
    if order is None:
        abort(404)
    target = request.form.get("status", "")
    allowed = target == STATUS_FLOW.get(order["status"]) or (
        target == "cancelled" and order["status"] not in ("collected", "cancelled")
    )
    if not allowed:
        abort(409, f"An order that is {order['status']} cannot move to {target or 'nothing'}.")
    # Guard against two staff members updating the same order at once.
    with db:
        updated = db.execute(
            "UPDATE orders SET status = ? WHERE id = ? AND status = ?", (target, order_id, order["status"])
        ).rowcount
    if not updated:
        abort(409, "This order was just updated by someone else.")
    return redirect(url_for("shop.kitchen"))
