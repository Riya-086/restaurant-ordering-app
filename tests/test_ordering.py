from app.db import get_db


def place_order(post, items=((1, 2),), name="Asha", phone="(301) 555-0199"):
    for item_id, qty in items:
        post("/cart/add", {"item_id": str(item_id), "quantity": str(qty)})
    return post("/checkout", {"name": name, "phone": phone, "notes": "Extra napkins"})


def test_menu_lists_items_by_category(client):
    page = client.get("/").get_data(as_text=True)
    assert "Margherita Pizza" in page and "Desserts" in page and "$11.99" in page


def test_cart_totals_and_quantity_limits(post, client):
    post("/cart/add", {"item_id": "1", "quantity": "2"})
    post("/cart/add", {"item_id": "1", "quantity": "50"})  # capped at 20
    post("/cart/add", {"item_id": "7", "quantity": "1"})
    page = client.get("/cart").get_data(as_text=True)
    assert 'value="20"' in page and "$244.29" in page  # 20 x 11.99 + 4.49
    post("/cart/update", {"qty-1": "0"})
    assert "Margherita" not in client.get("/cart").get_data(as_text=True)


def test_unknown_item_and_bad_quantity(post):
    assert post("/cart/add", {"item_id": "999"}).status_code == 404
    assert post("/cart/add", {"item_id": "1", "quantity": "two"}).status_code == 400


def test_checkout_validates_fields(post):
    post("/cart/add", {"item_id": "1"})
    res = post("/checkout", {"name": "A", "phone": "12ab", "notes": "x" * 201})
    page = res.get_data(as_text=True)
    assert res.status_code == 400
    assert "between 2 and 60" in page and "7 to 15 digits" in page and "at most 200" in page


def test_empty_cart_cannot_check_out(client):
    assert client.get("/checkout").status_code == 302


def test_order_is_saved_with_server_side_total(post, client, app):
    res = place_order(post, items=((1, 2), (8, 1)))
    assert res.status_code == 302
    code = res.headers["Location"].rsplit("/", 1)[-1]
    page = client.get(f"/orders/{code}").get_data(as_text=True)
    assert "Received" in page and "$27.47" in page  # 2 x 11.99 + 3.49
    assert "Your order is empty" in client.get("/cart").get_data(as_text=True)
    with app.app_context():
        row = get_db().execute("SELECT total_cents, phone FROM orders WHERE code = ?", (code,)).fetchone()
    assert row["total_cents"] == 2747


def test_past_orders_keep_their_price_when_the_menu_changes(post, client, app):
    code = place_order(post).headers["Location"].rsplit("/", 1)[-1]
    with app.app_context():
        db = get_db()
        db.execute("UPDATE menu_items SET price_cents = 9999 WHERE id = 1")
        db.commit()
    assert "$23.98" in client.get(f"/orders/{code}").get_data(as_text=True)


def test_unknown_order_code(client):
    assert client.get("/orders/NOPE00").status_code == 404


def test_forms_require_csrf_token(client):
    assert client.post("/cart/add", data={"item_id": "1"}).status_code == 400


def test_kitchen_requires_login(client, post):
    assert client.get("/kitchen").status_code == 302
    assert post("/kitchen/login", {"password": "wrong"}).status_code == 401
    assert post("/kitchen/login", {"password": "secret-pass"}).status_code == 302
    assert client.get("/kitchen").status_code == 200


def test_kitchen_moves_orders_through_the_workflow(post, client, app):
    code = place_order(post).headers["Location"].rsplit("/", 1)[-1]
    post("/kitchen/login", {"password": "secret-pass"})
    with app.app_context():
        order_id = get_db().execute("SELECT id FROM orders WHERE code = ?", (code,)).fetchone()["id"]
    url = f"/kitchen/orders/{order_id}/status"
    assert post(url, {"status": "ready"}).status_code == 409  # cannot skip "preparing"
    for step in ("preparing", "ready", "collected"):
        assert post(url, {"status": step}).status_code == 302
    assert post(url, {"status": "cancelled"}).status_code == 409  # collected orders are final
    assert "Collected" in client.get(f"/orders/{code}").get_data(as_text=True)
    assert code not in client.get("/kitchen").get_data(as_text=True)  # no longer an open ticket
