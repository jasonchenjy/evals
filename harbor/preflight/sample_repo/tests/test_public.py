import unittest
from service import build_order


class PublicTests(unittest.TestCase):
    def test_order(self):
        self.assertEqual(build_order(' apples |2'),
                         {'item': 'apples', 'quantity': 2, 'total': 6})


if __name__ == '__main__':
    unittest.main()
