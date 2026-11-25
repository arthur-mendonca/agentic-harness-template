def load_order_emails(db, order_ids):
    orders = db.fetch_orders(order_ids)
    return [(order['id'], db.fetch_customer(order['customer_id'])['email']) for order in orders]
