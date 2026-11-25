def load_order_emails(db, order_ids):
    orders = db.fetch_orders(order_ids)
    customer_ids = list(dict.fromkeys(order['customer_id'] for order in orders))
    if not customer_ids:
        return []
    customers = {customer['id']: customer for customer in db.fetch_customers(customer_ids)}
    return [(order['id'], customers[order['customer_id']]['email']) for order in orders]
