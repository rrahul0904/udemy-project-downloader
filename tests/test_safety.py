import unittest

from app.safety import UrlValidationError, normalize_udemy_url, slug_from_url


class SafetyTests(unittest.TestCase):
    def test_accepts_udemy_course_urls(self):
        self.assertEqual(
            normalize_udemy_url("http://www.udemy.com/course/python-101/?coupon=abc"),
            "https://www.udemy.com/course/python-101/?coupon=abc",
        )

    def test_accepts_udemy_business_subdomains(self):
        self.assertEqual(
            normalize_udemy_url("https://example.udemy.com/course/python-101/learn/"),
            "https://example.udemy.com/course/python-101/learn/",
        )

    def test_rejects_non_udemy_urls(self):
        with self.assertRaises(UrlValidationError):
            normalize_udemy_url("https://example.com/?next=https://www.udemy.com/course/x/")

    def test_rejects_missing_scheme(self):
        with self.assertRaises(UrlValidationError):
            normalize_udemy_url("www.udemy.com/course/x/")

    def test_slug_from_url(self):
        self.assertEqual(slug_from_url("https://www.udemy.com/course/python-101/"), "python-101")


if __name__ == "__main__":
    unittest.main()

