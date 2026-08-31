from __future__ import annotations

import hashlib
import json

from app.schemas.whatsapp_flows import FlowBuilder, FlowComponent


FLOW_JSON_VERSION = "7.3"
INPUT_TYPES = {
    "text_input": ("TextInput", "text"),
    "email_input": ("TextInput", "email"),
    "phone_input": ("TextInput", "phone"),
    "number_input": ("TextInput", "number"),
}


class WhatsAppFlowCompiler:
    def compile(self, raw_builder: dict) -> tuple[dict, str]:
        builder = FlowBuilder.model_validate(raw_builder)
        self._validate(builder)
        all_inputs = [
            (screen.id, component)
            for screen in builder.screens
            for component in screen.components
            if self._is_input(component)
        ]
        compiled = {
            "version": FLOW_JSON_VERSION,
            "screens": [self._compile_screen(screen, all_inputs) for screen in builder.screens],
        }
        canonical = json.dumps(compiled, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return compiled, hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _validate(self, builder: FlowBuilder) -> None:
        screen_ids = [screen.id for screen in builder.screens]
        if len(screen_ids) != len(set(screen_ids)):
            raise ValueError("Screen IDs must be unique.")
        component_ids = [component.id for screen in builder.screens for component in screen.components]
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("Component IDs must be unique across the Flow.")
        if sum(screen.terminal for screen in builder.screens) != 1:
            raise ValueError("A Flow must have exactly one terminal screen.")
        known_screens = set(screen_ids)
        for screen in builder.screens:
            footers = [component for component in screen.components if component.type == "footer"]
            if len(footers) != 1:
                raise ValueError(f"Screen {screen.id} must have exactly one footer.")
            footer = footers[0]
            assert footer.action is not None
            if screen.terminal and footer.action.type != "complete":
                raise ValueError(f"Terminal screen {screen.id} must complete the Flow.")
            if not screen.terminal and footer.action.type != "navigate":
                raise ValueError(f"Non-terminal screen {screen.id} must navigate.")
            if footer.action.target_screen_id and footer.action.target_screen_id not in known_screens:
                raise ValueError(f"Navigation target {footer.action.target_screen_id} does not exist.")
            for component in screen.components:
                if component.binding and not self._is_input(component):
                    raise ValueError("Context bindings are only valid on input components.")

    def _compile_screen(self, screen, all_inputs: list[tuple[str, FlowComponent]]) -> dict:
        children = [self._compile_component(component, screen.id, all_inputs) for component in screen.components]
        return {
            "id": screen.id,
            "title": screen.title,
            "terminal": screen.terminal,
            "layout": {
                "type": "SingleColumnLayout",
                "children": [{"type": "Form", "name": f"{screen.id.lower()}_form", "children": children}],
            },
        }

    def _compile_component(
        self,
        component: FlowComponent,
        screen_id: str,
        all_inputs: list[tuple[str, FlowComponent]],
    ) -> dict:
        if component.type == "heading":
            return {"type": "TextHeading", "text": component.text}
        if component.type == "body":
            return {"type": "TextBody", "text": component.text}
        if component.type in INPUT_TYPES:
            meta_type, input_type = INPUT_TYPES[component.type]
            result = self._input_base(component, meta_type)
            result["input-type"] = input_type
            return result
        if component.type == "text_area":
            return self._input_base(component, "TextArea")
        if component.type in {"dropdown", "radio"}:
            result = self._input_base(
                component, "Dropdown" if component.type == "dropdown" else "RadioButtonsGroup"
            )
            result["data-source"] = [{"id": option.id, "title": option.title} for option in component.options]
            return result
        if component.type == "checkbox":
            return self._input_base(component, "OptIn")
        if component.type == "date":
            return self._input_base(component, "DatePicker")
        if component.type == "footer":
            assert component.action is not None
            action: dict = {"name": component.action.type}
            if component.action.type == "navigate":
                action["next"] = {"type": "screen", "name": component.action.target_screen_id}
                current_inputs = [item for item in all_inputs if item[0] == screen_id]
                if current_inputs:
                    action["payload"] = {
                        self._payload_key(item): f"${{form.{item.id}}}" for _, item in current_inputs
                    }
            else:
                action["payload"] = {
                    self._payload_key(item): (
                        f"${{form.{item.id}}}" if source == screen_id else f"${{screen.{source}.form.{item.id}}}"
                    )
                    for source, item in all_inputs
                }
            return {"type": "Footer", "label": component.label, "on-click-action": action}
        raise ValueError(f"Unsupported component type: {component.type}")

    @staticmethod
    def _input_base(component: FlowComponent, meta_type: str) -> dict:
        result = {
            "type": meta_type,
            "name": component.id,
            "label": component.label,
            "required": component.required,
        }
        if component.placeholder and meta_type in {"TextInput", "TextArea"}:
            result["helper-text"] = component.placeholder
        return result

    @staticmethod
    def _is_input(component: FlowComponent) -> bool:
        return component.type not in {"heading", "body", "footer"}

    @staticmethod
    def _payload_key(component: FlowComponent) -> str:
        return component.binding.context_field_key if component.binding else component.id
