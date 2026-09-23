from kivy.app import App
from kivy.lang import Builder
from kivy.properties import BooleanProperty
from kivy.uix.screenmanager import Screen

import db as dbmod

KV = """
<ChangePasswordScreen>:
    BoxLayout:
        orientation: "vertical"
        padding: dp(24)
        spacing: dp(10)
        size_hint: None, None
        size: min(dp(420), root.width - dp(48)), self.minimum_height
        pos_hint: {"center_x": 0.5, "center_y": 0.5}

        Label:
            text: "Set a new password" if root.forced else "Change Password"
            font_size: "20sp"
            bold: True
            color: 0, 0, 0, 1
            size_hint_y: None
            height: dp(36)

        Label:
            text: "This account must set a new password before continuing." if root.forced else ""
            color: 0.7, 0.1, 0.1, 1
            size_hint_y: None
            height: dp(24) if root.forced else 0

        TextInput:
            id: current_pw
            hint_text: "Current Password"
            password: True
            multiline: False
            size_hint_y: None
            height: dp(44)

        TextInput:
            id: new_pw
            hint_text: "New Password (min 8 characters)"
            password: True
            multiline: False
            size_hint_y: None
            height: dp(44)

        TextInput:
            id: confirm_pw
            hint_text: "Confirm New Password"
            password: True
            multiline: False
            size_hint_y: None
            height: dp(44)

        Label:
            id: error_label
            text: ""
            color: 0.8, 0.1, 0.1, 1
            size_hint_y: None
            height: dp(22) if self.text else 0

        Button:
            text: "Set Password"
            size_hint_y: None
            height: dp(44)
            on_release: root.do_change()

        Button:
            text: "Cancel"
            size_hint_y: None
            height: dp(40)
            opacity: 0 if root.forced else 1
            disabled: root.forced
            on_release: root.cancel()
"""
Builder.load_string(KV)


class ChangePasswordScreen(Screen):
    forced = BooleanProperty(False)

    def on_pre_enter(self):
        self.ids.current_pw.text = ""
        self.ids.new_pw.text = ""
        self.ids.confirm_pw.text = ""
        self.ids.error_label.text = ""

    def do_change(self):
        app = App.get_running_app()
        new = self.ids.new_pw.text
        confirm = self.ids.confirm_pw.text
        if new != confirm:
            self.ids.error_label.text = "New passwords do not match."
            return
        if len(new) < 8:
            self.ids.error_label.text = "New password must be at least 8 characters."
            return
        try:
            app.database.change_password(app.current_user["username"], self.ids.current_pw.text, new)
        except (dbmod.AuthError, dbmod.ValidationError) as e:
            self.ids.error_label.text = str(e)
            return
        self.forced = False
        app.go_to_dashboard()

    def cancel(self):
        App.get_running_app().go_to_dashboard()
