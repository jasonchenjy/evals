"""Independent verifier tests; never included in the Agent image."""
import unittest
from service import build_order


class HiddenTests(unittest.TestCase):
    def test_quantities(self):
        for n in (1, 3, 17, 100):
            with self.subTest(n=n):
                self.assertEqual(build_order(' pears | '+str(n)+' '),
                                 {'item':'pears','quantity':n,'total':n*3})

    def test_invalid(self):
        for line in (' |2', 'a|0', 'a|-1', 'a|101', 'a|x', 'a|1.5', 'a', 'a|2|3'):
            with self.subTest(line=line), self.assertRaises(ValueError):
                build_order(line)

    def test_distinct_requests(self):
        self.assertEqual(build_order('kiwi|4')['quantity'],4)
        self.assertEqual(build_order('plum|1')['item'],'plum')


if __name__ == '__main__':
    unittest.main()
