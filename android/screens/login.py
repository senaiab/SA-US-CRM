from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import Screen

import db as dbmod

KV = """
<LoginScreen>:
    canvas.before:
        Color:
            rgba: 0.122, 0.306, 0.471, 1
        Rectangle:
            pos: self.pos
            size: self.size

    BoxLayout:
        orientation: "vertical"
        padding: dp(32)
        spacing: dp(12)
        size_hint: None, None
        size: min(dp(420), root.width - dp(48)), self.minimum_height
        pos_hint: {"center_x": 0.5, "center_y": 0.5}

        Label:
            text: "SA-US ERP"
            font_size: "28sp"
            bold: True
            size_hint_y: None
            height: dp(48)

        Label:
            text: "Sign in"
            color: 0.85, 0.9, 1, 1
            size_hint_y: None
            height: dp(24)

        TextInput:
            id: username
            hint_text: "Username"
            multiline: False
            size_hint_y: None
            height: dp(48)
            text: "admin"

        TextInput:
            id: password
            hint_text: "Password"
            password: True
            multiline: False
            size_hint_y: None
            height: dp(48)

        Label:
            id: error_label
            text: ""
            color: 1, 0.6, 0.6, 1
            size_hint_y: None
            height: dp(24) if self.text else 0

        Button:
            text: "Login"
            size_hint_y: None
            height: dp(48)
            on_release: root.do_login()
"""
Builder.load_string(KV)


class LoginScreen(Screen):
    def do_login(self):
        username = self.ids.username.text.strip()
        password = self.ids.password.text
        app = App.get_running_app()
        try:
            user_row = app.database.login(username, password)
        except dbmod.AuthError as e:
            self.ids.error_label.text = str(e)
            return
        self.ids.error_label.text = ""
        self.ids.password.text = ""
        app.on_login_success(user_row)
