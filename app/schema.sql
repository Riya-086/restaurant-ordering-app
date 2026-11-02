CREATE TABLE IF NOT EXISTS menu_items (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    category    TEXT NOT NULL,
    price_cents INTEGER NOT NULL CHECK (price_cents > 0),
    available   INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS orders (
    id            INTEGER PRIMARY KEY,
    code          TEXT NOT NULL UNIQUE,
    customer_name TEXT NOT NULL,
    phone         TEXT NOT NULL,
    notes         TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'received'
                  CHECK (status IN ('received', 'preparing', 'ready', 'collected', 'cancelled')),
    total_cents   INTEGER NOT NULL,
    created_at    TEXT NOT NULL
);

-- Name and price are copied onto each line so later menu changes never alter past orders.
CREATE TABLE IF NOT EXISTS order_items (
    order_id         INTEGER NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    menu_item_id     INTEGER NOT NULL REFERENCES menu_items (id),
    name             TEXT NOT NULL,
    unit_price_cents INTEGER NOT NULL,
    quantity         INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 20),
    PRIMARY KEY (order_id, menu_item_id)
);
