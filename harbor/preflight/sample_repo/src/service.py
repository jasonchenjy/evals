from parser import parse_order
from validator import validate_order


def build_order(line):
    parsed = parse_order(line)
    order = {'item': parsed['item']}
    validate_order(order)
    return dict(order, total=order['quantity'] * 3)
