from kivy.app import App
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

import db as dbmod

KV = """
<RecordFormScreen>:
    BoxLayout:
        orientation: "vertical"

        BoxLayout:
            size_hint_y: None
            height: dp(52)
            padding: dp(6)
            canvas.before:
                Color:
                    rgba: 0.122, 0.306, 0.471, 1
                Rectangle:
                    pos: self.pos
                    size: self.size
            Button:
                text: "Cancel"
                size_hint_x: None
                width: dp(90)
                on_release: root.cancel()
            Label:
                text: root.title_text
                bold: True
            Button:
                text: "Save"
                size_hint_x: None
                width: dp(90)
                on_release: root.save()

        ScrollView:
            BoxLayout:
                id: form_fields
                orientation: "vertical"
                padding: dp(12)
                spacing: dp(10)
                size_hint_y: None
                height: self.minimum_height
"""
Builder.load_string(KV)


class RecordFormScreen(Screen):
    title_text = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.module = None
        self.record = None
        self.entries = {}

    def load(self, module, record=None, prefill=None):
        self.module = module
        self.record = record
        self.title_text = ("Edit " if record else "Add ") + module.title()
        data = (record or {}).get("data", {}) or (prefill or {})

        app = App.get_running_app()
        auto_cfg = dbmod.AUTO_ID_FIELDS.get(module, {})
        cross_ref = dbmod.CROSS_REF_FIELDS.get(module, {})

        container = self.ids.form_fields
        container.clear_widgets()
        self.entries = {}

        for field in dbmod.MODULES[module]:
            row = BoxLayout(size_hint_y=None, height=dp(64), spacing=dp(8))
            row.add_widget(Label(text=field, size_hint_x=0.35, halign="left", valign="middle"))

            existing = str(data.get(field, ""))

            if field in (auto_cfg.get("id_field"), auto_cfg.get("date_field")):
                widget = TextInput(text=existing or "(assigned automatically on save)", disabled=True, multiline=False)
            elif field in cross_ref:
                source_module = cross_ref[field]
                source_id_field = dbmod.AUTO_ID_FIELDS.get(source_module, {}).get("id_field", field)
                ref_records = app.database.list_records(source_module, "")
                ref_ids = sorted({
                    r.get("data", {}).get(source_id_field, "").strip()
                    for r in ref_records
                    if r.get("data", {}).get(source_id_field, "").strip()
                })
                widget = Spinner(text=existing, values=[""] + ref_ids)
            elif field == "Client Name" and module in ("leads", "quotations"):
                widget = self._build_client_name_widget(module, existing)
            elif field in dbmod.DROPDOWNS:
                choices = list(dbmod.DROPDOWNS[field])
                if existing and existing not in choices:
                    choices = [existing] + choices
                widget = Spinner(text=existing, values=[""] + choices)
            elif field in dbmod.NOTES_LIKE_FIELDS:
                widget = TextInput(text=existing, multiline=True)
                row.height = dp(96)
            else:
                widget = TextInput(text=existing, multiline=False)

            row.add_widget(widget)
            container.add_widget(row)
            self.entries[field] = widget

    def _build_client_name_widget(self, module, existing):
        app = App.get_running_app()
        clients = app.database.list_records("clients", "")
        names = sorted({
            c.get("data", {}).get("Client Name", "").strip()
            for c in clients
            if c.get("data", {}).get("Client Name", "").strip()
        })
        text_input = TextInput(text=existing, multiline=False)

        wrapper = BoxLayout(orientation="vertical", spacing=dp(4))
        wrapper.add_widget(text_input)
        if names:
            picker = Spinner(text="Pick existing client...", values=names, size_hint_y=None, height=dp(32))

            def on_pick(spinner_inst, value):
                if value and value != "Pick existing client...":
                    text_input.text = value
                    self._autofill_from_client(module, value)

            picker.bind(text=on_pick)
            wrapper.add_widget(picker)

        # Keep a .text proxy so save() can read it uniformly like other widgets.
        wrapper.text = existing

        def sync(instance, value):
            wrapper.text = value

        text_input.bind(text=sync)
        return wrapper

    def _autofill_from_client(self, module, client_name):
        if module != "leads":
            return
        app = App.get_running_app()
        clients = app.database.list_records("clients", "")
        match = next(
            (c for c in clients if c.get("data", {}).get("Client Name", "").strip().lower() == client_name.strip().lower()),
            None,
        )
        if not match:
            return
        cdata = match.get("data", {})
        mapping = {
            "Company": cdata.get("Company", "").strip(),
            "Phone/Email": " / ".join(p for p in [cdata.get("Phone", "").strip(), cdata.get("Email", "").strip()] if p),
        }
        for field, value in mapping.items():
            widget = self.entries.get(field)
            if widget is not None and value and not widget.text.strip():
                widget.text = value

    def save(self):
        data = {}
        for field, widget in self.entries.items():
            data[field] = (widget.text or "").strip()

        app = App.get_running_app()
        try:
            if self.record:
                app.database.update_record(self.record["id"], data, app.current_user["username"])
                new_id = None
            else:
                saved = app.database.create_record(self.module, data, app.current_user["username"])
                id_field = dbmod.AUTO_ID_FIELDS.get(self.module, {}).get("id_field")
                new_id = saved["data"].get(id_field) if id_field else None
        except (dbmod.AuthError, dbmod.ValidationError) as e:
            self._notify(str(e))
            return

        app.open_module(self.module)
        if new_id:
            self._notify(f"{self.module.title()[:-1]} created as {new_id}.")

    def cancel(self):
        App.get_running_app().open_module(self.module)

    def _notify(self, message):
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(12))
        box.add_widget(Label(text=message))
        btn = Button(text="OK", size_hint_y=None, height=dp(44))
        box.add_widget(btn)
        popup = Popup(title="", content=box, size_hint=(0.85, 0.4))
        btn.bind(on_release=lambda inst: popup.dismiss())
        popup.open()
