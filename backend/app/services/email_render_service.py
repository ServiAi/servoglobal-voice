from __future__ import annotations

import html
import re
from dataclasses import dataclass


ALLOWED_COMPONENTS = {"Button", "Callout", "Divider", "Signature", "KeyValueList"}
DISALLOWED_PATTERNS = [
    r"<\s*(script|iframe|form|input|select|textarea|style)\b",
    r"\son[a-z]+\s*=",
    r"^\s*(import|export)\s+",
    r"javascript:",
]


@dataclass(frozen=True)
class RenderedEmailContent:
    subject: str
    html: str
    text: str


class EmailRenderService:
    def render_email_content(
        self,
        *,
        subject: str,
        content_format: str,
        content: str,
        variables: dict[str, str | None] | None = None,
    ) -> RenderedEmailContent:
        variables = variables or {}
        self.validate_disallowed_content(content)
        interpolated = self._interpolate(content, variables)
        body_html = self.render_mdx_controlled(interpolated) if content_format == "mdx" else self.render_markdown(interpolated)
        body_html = self.sanitize_html(body_html)
        return RenderedEmailContent(
            subject=subject,
            html=body_html,
            text=self.generate_plain_text(body_html),
        )

    def render_mdx_controlled(self, content: str) -> str:
        self._validate_components(content)
        content = re.sub(
            r'<Button\s+href="([^"]+)">([\s\S]*?)</Button>',
            lambda m: "{{button:%s|%s}}" % (m.group(2), m.group(1)),
            content,
        )
        content = re.sub(r"<Divider\s*/>", "{{divider}}", content)
        content = re.sub(
            r'<Signature\s+name="([^"]+)"\s*/>',
            lambda m: "{{signature:%s}}" % m.group(1),
            content,
        )
        content = re.sub(
            r'<Callout\s+type="(info|warning)">([\s\S]*?)</Callout>',
            lambda m: "{{callout:%s|%s}}" % (m.group(1), m.group(2).strip()),
            content,
        )
        return self.render_markdown(content)

    def render_markdown(self, content: str) -> str:
        blocks: list[str] = []
        for raw in re.split(r"\n\s*\n", content.strip()):
            block = raw.strip()
            if not block:
                continue
            shortcode = self._render_shortcode(block)
            if shortcode:
                blocks.append(shortcode)
                continue
            escaped = html.escape(block)
            escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
            if escaped.startswith("# "):
                blocks.append(f"<h1>{escaped[2:]}</h1>")
            elif escaped.startswith("## "):
                blocks.append(f"<h2>{escaped[3:]}</h2>")
            else:
                blocks.append(f"<p>{escaped.replace(chr(10), '<br />')}</p>")
        return "\n".join(blocks)

    def sanitize_html(self, value: str) -> str:
        self.validate_disallowed_content(value)
        return value

    def generate_plain_text(self, value: str) -> str:
        text = re.sub(r"<br\s*/?>", "\n", value)
        text = re.sub(r"</(p|h1|h2|div)>", "\n", text)
        text = re.sub(r"<[^>]+>", "", text)
        return html.unescape(re.sub(r"\n{3,}", "\n\n", text)).strip()

    def validate_disallowed_content(self, content: str) -> None:
        if re.search(r"<\s*button\b", content):
            raise ValueError("Email content contains disallowed HTML or MDX.")
        for pattern in DISALLOWED_PATTERNS:
            if re.search(pattern, content, flags=re.IGNORECASE | re.MULTILINE):
                raise ValueError("Email content contains disallowed HTML or MDX.")

    def _validate_components(self, content: str) -> None:
        for match in re.finditer(r"</?([A-Z][A-Za-z0-9]*)\b", content):
            if match.group(1) not in ALLOWED_COMPONENTS:
                raise ValueError("Email content contains an unsupported component.")

    def _interpolate(self, content: str, variables: dict[str, str | None]) -> str:
        def repl(match: re.Match[str]) -> str:
            return str(variables.get(match.group(1).strip()) or "")

        return re.sub(r"{{\s*([a-zA-Z0-9_]+)\s*}}", repl, content)

    def _render_shortcode(self, block: str) -> str | None:
        if block == "{{divider}}":
            return '<hr style="border:0;border-top:1px solid #e5e7eb;margin:24px 0" />'
        if block.startswith("{{signature:") and block.endswith("}}"):
            name = html.escape(block[len("{{signature:") : -2].strip())
            return f'<p style="margin-top:24px">Saludos,<br /><strong>{name}</strong></p>'
        if block.startswith("{{button:") and block.endswith("}}"):
            label, _, href = block[len("{{button:") : -2].partition("|")
            return self._button(label, href)
        if block.startswith("{{callout:") and block.endswith("}}"):
            callout_type, _, body = block[len("{{callout:") : -2].partition("|")
            return self._callout(body, callout_type if callout_type in {"info", "warning"} else "info")
        return None

    def _button(self, label: str, href: str) -> str:
        safe_href = html.escape(self._safe_url(href), quote=True)
        safe_label = html.escape(label.strip() or "Abrir enlace")
        return (
            '<p><a href="%s" style="display:inline-block;background:#0f766e;color:#ffffff;'
            'padding:10px 14px;border-radius:6px;text-decoration:none">%s</a></p>'
        ) % (safe_href, safe_label)

    def _callout(self, body: str, callout_type: str) -> str:
        color = "#0f766e" if callout_type == "info" else "#b45309"
        return f'<div style="border-left:4px solid {color};padding:8px 12px">{html.escape(body.strip())}</div>'

    def _safe_url(self, href: str) -> str:
        cleaned = href.strip()
        if not cleaned.startswith(("https://", "http://")):
            raise ValueError("Email button URL must be absolute HTTP(S).")
        return cleaned
