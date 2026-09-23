"""
SA-US ERP — standalone Android app.

No network, no server: all data lives in a local sqlite database inside the
app's own private storage (see db.py). This file just wires up the Kivy
App and ScreenManager; each screen is defined in screens/.
"""
import os

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, NoTransition

import db as dbmod
from screens.login import LoginScreen
from screens.change_password import ChangePasswordScreen
from screens.dashboard import DashboardScreen
from screens.module_list import ModuleListScreen
from screens.record_form import RecordFormScreen
from screens.admin import AdminScreen


class SAUSERPApp(App):
    title = "SA-US ERP"

    def build(self):
        self.current_user = None  # dict: username, full_name, role
        self.database = dbmod.get_db(self.user_data_dir)

        sm = ScreenManager(transition=NoTransition())
        sm.add_widget(LoginScreen(name="login"))
        sm.add_widget(ChangePasswordScreen(name="change_password"))
        sm.add_widget(DashboardScreen(name="dashboard"))
        for module in dbmod.MODULES:
            sm.add_widget(ModuleListScreen(module=module, name=f"module_{module}"))
        sm.add_widget(RecordFormScreen(name="record_form"))
        sm.add_widget(AdminScreen(name="admin"))
        sm.current = "login"
        self.sm = sm
        return sm

    # ── Session helpers used across screens ─────────────────────────────

    def on_login_success(self, user_row):
        self.current_user = {
            "username": user_row["username"],
            "full_name": user_row["full_name"],
            "role": user_row["role"],
        }
        if user_row["must_change_password"]:
            self.sm.get_screen("change_password").forced = True
            self.sm.current = "change_password"
        else:
            self.go_to_dashboard()

    def go_to_dashboard(self):
        self.sm.get_screen("dashboard").refresh()
        self.sm.current = "dashboard"

    def open_module(self, module):
        screen = self.sm.get_screen(f"module_{module}")
        screen.refresh()
        self.sm.current = f"module_{module}"

    def open_record_form(self, module, record=None, prefill=None):
        form = self.sm.get_screen("record_form")
        form.load(module, record=record, prefill=prefill)
        self.sm.current = "record_form"

    def logout(self):
        self.current_user = None
        self.sm.current = "login"

    def can_access(self, module, write=False):
        if not self.current_user:
            return False
        return dbmod.Database.can_access(self.current_user["role"], module, write=write)


if __name__ == "__main__":
    SAUSERPApp().run()
