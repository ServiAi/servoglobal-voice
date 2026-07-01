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

    def test_signature_component_renders_to_html(self):
        rendered = self.service.render_email_content(
            subject="Test",
            content_format="mdx",
            content='<Signature name="ServiGlobal IA" />',
            variables={},
        )
        self.assertIn("ServiGlobal IA", rendered.html)
        self.assertIn("Saludos", rendered.html)
        self.assertNotIn("{{signature:", rendered.html)
        self.assertNotIn("<Signature", rendered.html)

    def test_signature_shortcode_renders_to_html(self):
        rendered = self.service.render_email_content(
            subject="Test",
            content_format="mdx",
            content="{{signature:ServiGlobal IA}}",
            variables={},
        )
        self.assertIn("ServiGlobal IA", rendered.html)
        self.assertIn("Saludos", rendered.html)

    def test_signature_adjacent_to_heading_does_not_leak_raw_shortcode(self):
        rendered = self.service.render_email_content(
            subject="Test",
            content_format="mdx",
            content="{{signature:ServiGlobal IA}}# Propuesta ServiGlobal IA",
            variables={},
        )
        self.assertNotIn("{{signature:", rendered.html)
        self.assertNotIn("{{signature:", rendered.text)
        self.assertIn("ServiGlobal IA", rendered.html)
        self.assertIn("Propuesta", rendered.html)

    def test_button_with_real_href_renders_to_html(self):
        rendered = self.service.render_email_content(
            subject="Test",
            content_format="mdx",
            content='<Button href="https://example.com">Completar formulario</Button>',
            variables={},
        )
        self.assertIn("https://example.com", rendered.html)
        self.assertIn("Completar formulario", rendered.html)
        self.assertNotIn("<Button", rendered.html)
        self.assertNotIn("{{button:", rendered.html)

    def test_button_with_empty_href_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.render_email_content(
                subject="Test",
                content_format="mdx",
                content='<Button href="">Completar formulario</Button>',
                variables={},
            )

    def test_button_with_unresolved_form_link_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.render_email_content(
                subject="Test",
                content_format="mdx",
                content='<Button href="{{form_link}}">Completar formulario</Button>',
                variables={"form_link": ""},
            )

    def test_markdown_image_data_url_renders_to_html(self):
        rendered = self.service.render_email_content(
            subject="Test",
            content_format="mdx",
            content="![image.png](data:image/png;base64,aW1hZ2U=)",
            variables={},
        )

        self.assertIn('<img src="data:image/png;base64,aW1hZ2U="', rendered.html)
        self.assertIn('alt="image.png"', rendered.html)

    def test_markdown_image_rejects_non_image_data_url(self):
        with self.assertRaises(ValueError):
            self.service.render_email_content(
                subject="Test",
                content_format="mdx",
                content="![x](data:text/html;base64,PHNjcmlwdD4=)",
                variables={},
            )

    def test_callout_component_renders_to_html(self):
        rendered = self.service.render_email_content(
            subject="Test",
            content_format="mdx",
            content="<Callout type=\"info\">\nPodemos adaptar esta solucion a tu operacion actual.\n</Callout>",
            variables={},
        )
        self.assertIn("Podemos adaptar", rendered.html)
        self.assertNotIn("<Callout", rendered.html)
        self.assertNotIn("{{callout:", rendered.html)

    def test_callout_shortcode_renders_to_html(self):
        rendered = self.service.render_email_content(
            subject="Test",
            content_format="mdx",
            content="{{callout:info|Podemos adaptar esta solucion a tu operacion actual.}}",
            variables={},
        )
        self.assertIn("Podemos adaptar", rendered.html)
        self.assertNotIn("{{callout:", rendered.html)

    def test_no_unrendered_mdx_or_shortcodes_remain(self):
        with self.assertRaises(ValueError):
            self.service.render_email_content(
                subject="Test",
                content_format="mdx",
                content="{{signature:ServiGlobal IA}}# Propuesta\n\n<Button href=\"\">Test</Button>",
                variables={},
            )

    def test_email_content_does_not_duplicate_template_body(self):
        rendered = self.service.render_email_content(
            subject="Sujeto",
            content_format="mdx",
            content="# Propuesta\n\nHola {{contact_name}}\n\nGracias por tu interes.",
            variables={"contact_name": "PEDRO"},
        )
        self.assertEqual(rendered.html.count("Propuesta"), 1)
        self.assertEqual(rendered.html.count("PEDRO"), 1)
        self.assertEqual(rendered.html.count("interes"), 1)

    def test_preview_returns_html_and_text(self):
        content = "# Propuesta\n\nHola {{contact_name}}\n\n<Signature name=\"ServiGlobal IA\" />"
        rendered = self.service.render_email_content(
            subject="Sujeto",
            content_format="mdx",
            content=content,
            variables={"contact_name": "Ana"},
        )
        self.assertTrue(len(rendered.html) > 0)
        self.assertTrue(len(rendered.text) > 0)
        self.assertNotEqual(rendered.html, rendered.text)
        self.assertIn("Ana", rendered.text)
        self.assertIn("ServiGlobal IA", rendered.text)

    def test_multiline_callout_does_not_break(self):
        rendered = self.service.render_email_content(
            subject="Test",
            content_format="mdx",
            content="<Callout type=\"info\">\nLinea uno\nLinea dos\nLinea tres\n</Callout>",
            variables={},
        )
        self.assertIn("Linea uno", rendered.html)
        self.assertIn("Linea dos", rendered.html)

    def test_normalize_separates_adjacent_shortcodes(self):
        rendered = self.service.render_email_content(
            subject="Test",
            content_format="mdx",
            content="{{signature:ServiGlobal IA}}<Divider />{{signature:ServiGlobal IA}}",
            variables={},
        )
        self.assertNotIn("{{signature:", rendered.html)
        self.assertNotIn("<Divider", rendered.html)
        self.assertNotIn("{{divider}}", rendered.html)

    def test_divider_renders_as_hr(self):
        rendered = self.service.render_email_content(
            subject="Test",
            content_format="mdx",
            content="<Divider />",
            variables={},
        )
        self.assertIn("<hr", rendered.html)

    def test_valid_complex_mdx_does_not_raise(self):
        content = "# Propuesta ServiGlobal IA\n\nHola {{contact_name}}\n\nGracias por tu interes en ServiGlobal IA.\n\n<Signature name=\"ServiGlobal IA\" />\n\n<Button href=\"https://staging.serviglobal-ia.com/es/forms/public/token-demo\">Completar formulario</Button>\n\n<Callout type=\"info\">\nPodemos adaptar esta solucion a tu operacion actual.\n</Callout>"
        rendered = self.service.render_email_content(
            subject="Sujeto",
            content_format="mdx",
            content=content,
            variables={"contact_name": "Ana"},
        )
        self.assertIn("Propuesta", rendered.html)
        self.assertIn("Ana", rendered.html)
        self.assertIn("ServiGlobal IA", rendered.html)
        self.assertIn("staging.serviglobal-ia.com", rendered.html)
        self.assertIn("Podemos adaptar", rendered.html)


if __name__ == "__main__":
    unittest.main()
