from __future__ import annotations

import unittest

from app.services.email_render_service import EmailRenderService


class EmailComposerMdxTests(unittest.TestCase):
    def setUp(self):
        self.service = EmailRenderService()

    def test_markdown_renders_safe_html(self):
        rendered = self.service.render_email_content(
            subject="Hola",
            content_format="markdown",
            content="# Titulo\n\nHola **Juan**",
            variables={},
        )

        self.assertIn("<h1>Titulo</h1>", rendered.html)
        self.assertIn("<strong>Juan</strong>", rendered.html)

    def test_mdx_allows_whitelisted_components(self):
        rendered = self.service.render_email_content(
            subject="Hola",
            content_format="mdx",
            content='<Button href="https://example.com/form">Completar</Button>\n\n<Divider />\n\n<Signature name="ServiGlobal IA" />',
            variables={},
        )

        self.assertIn("https://example.com/form", rendered.html)
        self.assertIn("<hr", rendered.html)
        self.assertIn("ServiGlobal IA", rendered.text)

    def test_mdx_rejects_script(self):
        with self.assertRaises(ValueError):
            self.service.render_email_content(subject="x", content_format="mdx", content="<script>alert(1)</script>")

    def test_mdx_rejects_form_inputs(self):
        with self.assertRaises(ValueError):
            self.service.render_email_content(subject="x", content_format="mdx", content="<form><input /></form>")

    def test_mdx_rejects_unknown_component(self):
        with self.assertRaises(ValueError):
            self.service.render_email_content(subject="x", content_format="mdx", content="<Chart />")

    def test_plain_text_is_generated(self):
        rendered = self.service.render_email_content(
            subject="Hola",
            content_format="mdx",
            content="Hola {{contact_name}}",
            variables={"contact_name": "Ana"},
        )

        self.assertEqual(rendered.text, "Hola Ana")


if __name__ == "__main__":
    unittest.main()
