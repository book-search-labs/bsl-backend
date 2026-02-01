#!/usr/bin/env python3
import argparse
import json
import os
from typing import Any, Dict, List

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
        autocommit=True,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def fetch_rows(conn, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def main() -> int:
    parser = argparse.ArgumentParser(description="Export user data across BSL tables.")
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--output", help="output file path (json)")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    args = parser.parse_args()

    user_id = args.user_id
    output = args.output or f"var/privacy/user_{user_id}_export.json"

    os.makedirs(os.path.dirname(output), exist_ok=True)

    conn = connect_mysql()
    try:
        data: Dict[str, Any] = {}

        data["user_account"] = fetch_rows(conn, "SELECT * FROM user_account WHERE user_id=%s", (user_id,))
        data["user_preference"] = fetch_rows(conn, "SELECT * FROM user_preference WHERE user_id=%s", (user_id,))
        data["user_consent"] = fetch_rows(conn, "SELECT * FROM user_consent WHERE user_id=%s", (user_id,))
        data["user_saved_material"] = fetch_rows(conn, "SELECT * FROM user_saved_material WHERE user_id=%s", (user_id,))
        data["user_shelf"] = fetch_rows(conn, "SELECT * FROM user_shelf WHERE user_id=%s", (user_id,))
        data["user_recent_query"] = fetch_rows(conn, "SELECT * FROM user_recent_query WHERE user_id=%s", (user_id,))
        data["user_recent_view"] = fetch_rows(conn, "SELECT * FROM user_recent_view WHERE user_id=%s", (user_id,))
        data["user_feedback"] = fetch_rows(conn, "SELECT * FROM user_feedback WHERE user_id=%s", (user_id,))

        data["user_address"] = fetch_rows(conn, "SELECT * FROM user_address WHERE user_id=%s", (user_id,))
        cart_rows = fetch_rows(conn, "SELECT * FROM cart WHERE user_id=%s", (user_id,))
        data["cart"] = cart_rows
        cart_ids = [row["cart_id"] for row in cart_rows]
        if cart_ids:
            placeholders = ",".join(["%s"] * len(cart_ids))
            data["cart_item"] = fetch_rows(
                conn, f"SELECT * FROM cart_item WHERE cart_id IN ({placeholders})", tuple(cart_ids)
            )
        else:
            data["cart_item"] = []

        order_rows = fetch_rows(conn, "SELECT * FROM orders WHERE user_id=%s", (user_id,))
        data["orders"] = order_rows
        order_ids = [row["order_id"] for row in order_rows]
        if order_ids:
            placeholders = ",".join(["%s"] * len(order_ids))
            data["order_item"] = fetch_rows(
                conn, f"SELECT * FROM order_item WHERE order_id IN ({placeholders})", tuple(order_ids)
            )
            data["order_event"] = fetch_rows(
                conn, f"SELECT * FROM order_event WHERE order_id IN ({placeholders})", tuple(order_ids)
            )
            data["payment"] = fetch_rows(
                conn, f"SELECT * FROM payment WHERE order_id IN ({placeholders})", tuple(order_ids)
            )
            data["refund"] = fetch_rows(
                conn, f"SELECT * FROM refund WHERE order_id IN ({placeholders})", tuple(order_ids)
            )
            refund_ids = [row["refund_id"] for row in data["refund"]]
            if refund_ids:
                refund_placeholders = ",".join(["%s"] * len(refund_ids))
                data["refund_item"] = fetch_rows(
                    conn, f"SELECT * FROM refund_item WHERE refund_id IN ({refund_placeholders})", tuple(refund_ids)
                )
            else:
                data["refund_item"] = []

            data["shipment"] = fetch_rows(
                conn, f"SELECT * FROM shipment WHERE order_id IN ({placeholders})", tuple(order_ids)
            )
            shipment_ids = [row["shipment_id"] for row in data["shipment"]]
            if shipment_ids:
                ship_placeholders = ",".join(["%s"] * len(shipment_ids))
                data["shipment_item"] = fetch_rows(
                    conn, f"SELECT * FROM shipment_item WHERE shipment_id IN ({ship_placeholders})", tuple(shipment_ids)
                )
                data["shipment_event"] = fetch_rows(
                    conn, f"SELECT * FROM shipment_event WHERE shipment_id IN ({ship_placeholders})", tuple(shipment_ids)
                )
            else:
                data["shipment_item"] = []
                data["shipment_event"] = []
        else:
            data["order_item"] = []
            data["order_event"] = []
            data["payment"] = []
            data["refund"] = []
            data["refund_item"] = []
            data["shipment"] = []
            data["shipment_item"] = []
            data["shipment_event"] = []

        with open(output, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2 if args.pretty else None, default=str)

        print(f"[export] wrote {output}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
