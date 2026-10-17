def validate_order(order):
    if not order['item']:
        raise ValueError('item is required')
    if type(order['quantity']) is not int or not 1 <= order['quantity'] <= 100:
        raise ValueError('quantity must be an integer from 1 to 100')
