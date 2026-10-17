"""Parse an order line; normalization belongs to the service boundary."""
def parse_order(line):
    item, quantity = line.split('|')
    return {'item': item, 'quantity': quantity}
