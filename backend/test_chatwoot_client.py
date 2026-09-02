from __future__ import annotations

import unittest

from app.services.chatwoot_client import sanitize_chatwoot_error


class SanitizeChatwootErrorTests(unittest.TestCase):
    def test_html_error_page_is_replaced_with_generic_message(self):
        html = "<!DOCTYPE html><html><head><title>Page not found</title></head><body>404</body></html>"
        result = sanitize_chatwoot_error(html)
        self.assertNotIn("<", result)
        self.assertIn("HTML", result)

    def test_html_error_page_case_and_whitespace_insensitive(self):
        html = "  \n<HTML><body>Not found</body></html>"
        result = sanitize_chatwoot_error(html)
        self.assertNotIn("<", result)

    def test_redacts_token_and_truncates_plain_text_errors(self):
        message = "Unauthorized api_access_token=abc123.def-ghi for account"
        result = sanitize_chatwoot_error(message)
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("abc123", result)

    def test_none_returns_none(self):
        self.assertIsNone(sanitize_chatwoot_error(None))

    def test_empty_string_returns_none(self):
        self.assertIsNone(sanitize_chatwoot_error(""))


if __name__ == "__main__":
    unittest.main()
