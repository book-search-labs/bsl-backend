#!/usr/bin/env python3
import argparse
import os
from typing import List

import pymysql


MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "bsl")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "bsl")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "bsl")


def connect_mysql():
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        autocommit=False,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def fetch_ids(conn, sql: str, params: tuple) -> List[int]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [row[next(iter(row.keys()))] for row in cur.fetchall()]


def execute(conn, sql: str, params: tuple) -> int:
    with conn.cursor() as cur:
        return cur.execute(sql, params)


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete or anonymize user data.")
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--delete-commerce", action="store_true", help="hard-delete commerce rows")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    user_id = args.user_id
    conn = connect_mysql()
    try:
        cart_ids = fetch_ids(conn, "SELECT cart_id FROM cart WHERE user_id=%s", (user_id,))
        order_ids = fetch_ids(conn, "SELECT order_id FROM orders WHERE user_id=%s", (user_id,))

        if args.dry_run:
            print(f"[dry-run] carts={len(cart_ids)} orders={len(order_ids)}")
            return 0

        if cart_ids:
            placeholders = ",".join(["%s"] * len(cart_ids))
            execute(conn, f"DELETE FROM cart_item WHERE cart_id IN ({placeholders})", tuple(cart_ids))
            execute(conn, f"DELETE FROM cart WHERE cart_id IN ({placeholders})", tuple(cart_ids))

        execute(conn, "DELETE FROM user_address WHERE user_id=%s", (user_id,))
        execute(conn, "DELETE FROM user_recent_query WHERE user_id=%s", (user_id,))
        execute(conn, "DELETE FROM user_recent_view WHERE user_id=%s", (user_id,))
        execute(conn, "DELETE FROM user_saved_material WHERE user_id=%s", (user_id,))
        execute(conn, "DELETE FROM user_shelf WHERE user_id=%s", (user_id,))
        execute(conn, "DELETE FROM user_preference WHERE user_id=%s", (user_id,))
        execute(conn, "DELETE FROM user_consent WHERE user_id=%s", (user_id,))
        execute(conn, "DELETE FROM user_feedback WHERE user_id=%s", (user_id,))

        if order_ids:
            placeholders = ",".join(["%s"] * len(order_ids))
            if args.delete_commerce:
                execute(conn, f"DELETE FROM order_event WHERE order_id IN ({placeholders})", tuple(order_ids))
                execute(conn, f"DELETE FROM order_item WHERE order_id IN ({placeholders})", tuple(order_ids))
                execute(conn, f"DELETE FROM payment WHERE order_id IN ({placeholders})", tuple(order_ids))
                refund_ids = fetch_ids(conn, f"SELECT refund_id FROM refund WHERE order_id IN ({placeholders})", tuple(order_ids))
                if refund_ids:
                    refund_placeholders = ",".join(["%s"] * len(refund_ids))
                    execute(conn, f"DELETE FROM refund_item WHERE refund_id IN ({refund_placeholders})", tuple(refund_ids))
                execute(conn, f"DELETE FROM refund WHERE order_id IN ({placeholders})", tuple(order_ids))
                shipment_ids = fetch_ids(conn, f"SELECT shipment_id FROM shipment WHERE order_id IN ({placeholders})", tuple(order_ids))
                if shipment_ids:
                    ship_placeholders = ",".join(["%s"] * len(shipment_ids))
                    execute(conn, f"DELETE FROM shipment_event WHERE shipment_id IN ({ship_placeholders})", tuple(shipment_ids))
                    execute(conn, f"DELETE FROM shipment_item WHERE shipment_id IN ({ship_placeholders})", tuple(shipment_ids))
                execute(conn, f"DELETE FROM shipment WHERE order_id IN ({placeholders})", tuple(order_ids))
                execute(conn, f"DELETE FROM orders WHERE order_id IN ({placeholders})", tuple(order_ids))
            else:
                execute(conn, f"UPDATE orders SET user_id=0, shipping_snapshot_json=NULL WHERE order_id IN ({placeholders})", tuple(order_ids))

        conn.commit()
        print("[delete] user data removed/anonymized")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
