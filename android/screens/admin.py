from kivy.app import App
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.uix.behaviors import ToggleButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

import db as dbmod

KV = """
<UserRow>:
    size_hint_y: None
    height: dp(56)
    group: "user_rows"
    text: ""
    halign: "left"
    valign: "middle"
    text_size: self.width - dp(16), None
    padding: dp(8), dp(8)

<AdminScreen>:
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
                text: "< Back"
                size_hint_x: None
                width: dp(80)
                on_release: root.go_back()
            Label:
                text: "Admin — Users"
                bold: True
            Button:
                text: "New User"
                size_hint_x: None
                width: dp(100)
                on_release: root.open_create_user()

        ScrollView:
            BoxLayout:
                id: user_list
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height

        BoxLayout:
            size_hint_y: None
            height: dp(52)
            padding: dp(6)
            spacing: dp(6)
            Button:
                text: "Reset Password"
                on_release: root.reset_password()
            Button:
                text: "Deactivate"
                on_release: root.set_active(False)
            Button:
                text: "Activate"
                on_release: root.set_active(True)
"""
Builder.load_string(KV)


class UserRow(ToggleButtonBehavior, Label):
    username = None


class AdminScreen(Screen):
    def refresh(self):
        app = App.get_running_app()
        users = app.database.list_users()
        container = self.ids.user_list
        container.clear_widgets()
        for u in users:
            status = "Active" if u["is_active"] else "Inactive"
            row = UserRow(text=f"{u['username']}  |  {u['full_name']}  |  {u['role']}  |  {status}")
            row.username = u["username"]
            container.add_widget(row)

    def selected_username(self):
        for widget in self.ids.user_list.children:
            if isinstance(widget, UserRow) and widget.state == "down":
                return widget.username
        return None

    def go_back(self):
        App.get_running_app().go_to_dashboard()

    def open_create_user(self):
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(12))
        username_in = TextInput(hint_text="Username", multiline=False, size_hint_y=None, height=dp(44))
        fullname_in = TextInput(hint_text="Full Name", multiline=False, size_hint_y=None, height=dp(44))
        role_in = Spinner(text=dbmod.ROLES[-1], values=dbmod.ROLES, size_hint_y=None, height=dp(44))
        password_in = TextInput(hint_text="Password (min 8 chars)", password=True, multiline=False, size_hint_y=None, height=dp(44))
        error_label = Label(text="", color=(0.8, 0.1, 0.1, 1), size_hint_y=None, height=dp(20))
        box.add_widget(Label(text="Create or Update User", bold=True, size_hint_y=None, height=dp(28)))
        for w in (username_in, fullname_in, role_in, password_in, error_label):
            box.add_widget(w)
        btn_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        save_btn = Button(text="Save")
        cancel_btn = Button(text="Cancel")
        btn_row.add_widget(save_btn)
        btn_row.add_widget(cancel_btn)
        box.add_widget(btn_row)
        popup = Popup(title="", content=box, size_hint=(0.9, 0.7))

        def do_save(_):
            app = App.get_running_app()
            username = username_in.text.strip()
            if not username:
                error_label.text = "Username is required."
                return
            try:
                app.database.create_or_update_user(
                    username, fullname_in.text.strip(), role_in.text, password_in.text, app.current_user["username"]
                )
            except dbmod.ValidationError as e:
                error_label.text = str(e)
                return
            popup.dismiss()
            self.refresh()

        save_btn.bind(on_release=do_save)
        cancel_btn.bind(on_release=lambda inst: popup.dismiss())
        popup.open()

    def reset_password(self):
        username = self.selected_username()
        if not username:
            self._notify("Select a user first.")
            return

        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(12))
        box.add_widget(Label(text=f"New password for '{username}'", bold=True, size_hint_y=None, height=dp(28)))
        new_pw = TextInput(hint_text="New Password", password=True, multiline=False, size_hint_y=None, height=dp(44))
        confirm_pw = TextInput(hint_text="Confirm New Password", password=True, multiline=False, size_hint_y=None, height=dp(44))
        error_label = Label(text="", color=(0.8, 0.1, 0.1, 1), size_hint_y=None, height=dp(20))
        for w in (new_pw, confirm_pw, error_label):
            box.add_widget(w)
        btn_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        save_btn = Button(text="Reset")
        cancel_btn = Button(text="Cancel")
        btn_row.add_widget(save_btn)
        btn_row.add_widget(cancel_btn)
        box.add_widget(btn_row)
        popup = Popup(title="", content=box, size_hint=(0.9, 0.6))

        def do_reset(_):
            if new_pw.text != confirm_pw.text:
                error_label.text = "Passwords do not match."
                return
            app = App.get_running_app()
            try:
                app.database.reset_password(username, new_pw.text, app.current_user["username"])
            except dbmod.ValidationError as e:
                error_label.text = str(e)
                return
            popup.dismiss()
            self._notify(f"Password reset for '{username}'.")

        save_btn.bind(on_release=do_reset)
        cancel_btn.bind(on_release=lambda inst: popup.dismiss())
        popup.open()

    def set_active(self, active):
        username = self.selected_username()
        if not username:
            self._notify("Select a user first.")
            return
        app = App.get_running_app()
        try:
            app.database.set_user_active(username, active, app.current_user["username"])
        except dbmod.ValidationError as e:
            self._notify(str(e))
            return
        self.refresh()

    def _notify(self, message):
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(12))
        box.add_widget(Label(text=message))
        btn = Button(text="OK", size_hint_y=None, height=dp(44))
        box.add_widget(btn)
        popup = Popup(title="", content=box, size_hint=(0.85, 0.4))
        btn.bind(on_release=lambda inst: popup.dismiss())
        popup.open()
