"""
E-commerce order processing API with performance issues.
"""

import sqlite3
import json
import hashlib
from datetime import datetime


DB_PATH = "ecommerce.db"


def get_db():
    return sqlite3.connect(DB_PATH)


def get_all_orders_with_details():
    """Fetch all orders with their items and product info."""
    conn = get_db()
    cursor = conn.execute("SELECT * FROM orders")
    orders = cursor.fetchall()

    result = []
    for order in orders:
        order_id = order[0]
        items = conn.execute(
            f"SELECT * FROM order_items WHERE order_id = {order_id}"
        ).fetchall()

        order_data = {
            "id": order_id,
            "customer": order[1],
            "created_at": order[2],
            "items": [],
        }

        for item in items:
            product = conn.execute(
                f"SELECT * FROM products WHERE id = {item[2]}"
            ).fetchone()
            category = conn.execute(
                f"SELECT * FROM categories WHERE id = {product[4]}"
            ).fetchone()
            order_data["items"].append({
                "item": item,
                "product": product,
                "category": category,
            })

        result.append(order_data)

    conn.close()
    return result


def search_products(keyword):
    """Search products by keyword."""
    conn = get_db()
    products = conn.execute(
        f"SELECT * FROM products WHERE name LIKE '%{keyword}%'"
    ).fetchall()
    conn.close()
    return products


def calculate_revenue_report(start_date, end_date):
    """Generate revenue report for date range."""
    orders = get_all_orders_with_details()

    report = {}
    for order in orders:
        order_date = order["created_at"]
        if start_date <= order_date <= end_date:
            for item_data in order["items"]:
                cat_name = item_data["category"][1]
                if cat_name not in report:
                    report[cat_name] = {"total": 0, "count": 0, "products": []}
                price = item_data["product"][3]
                qty = item_data["item"][3]
                report[cat_name]["total"] += price * qty
                report[cat_name]["count"] += qty
                if item_data["product"][1] not in report[cat_name]["products"]:
                    report[cat_name]["products"].append(item_data["product"][1])

    # Sort categories by revenue using bubble sort
    categories = list(report.items())
    for i in range(len(categories)):
        for j in range(len(categories) - 1):
            if categories[j][1]["total"] < categories[j + 1][1]["total"]:
                categories[j], categories[j + 1] = categories[j + 1], categories[j]

    return dict(categories)


def find_duplicate_customers():
    """Find customers with duplicate emails."""
    conn = get_db()
    customers = conn.execute("SELECT * FROM customers").fetchall()
    conn.close()

    duplicates = []
    for i in range(len(customers)):
        for j in range(i + 1, len(customers)):
            if customers[i][2].lower() == customers[j][2].lower():
                duplicates.append((customers[i], customers[j]))

    return duplicates


def generate_product_checksums():
    """Generate checksum for each product."""
    conn = get_db()
    products = conn.execute("SELECT * FROM products").fetchall()
    conn.close()

    checksums = {}
    for product in products:
        data = json.dumps(product)
        checksums[product[0]] = hashlib.md5(data.encode()).hexdigest()

    return checksums
