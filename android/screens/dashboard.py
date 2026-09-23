from kivy.app import App
from kivy.factory import Factory
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import BooleanProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen

import db as dbmod

KV = """
<StatCard@BoxLayout>:
    label: ""
    value: "0"
    orientation: "vertical"
    padding: dp(10)
    canvas.before:
        Color:
            rgba: 1, 1, 1, 1
        Rectangle:
            pos: self.pos
            size: self.size
        Color:
            rgba: 0.85, 0.87, 0.9, 1
        Line:
            rectangle: self.x, self.y, self.width, self.height

    Label:
        text: root.label
        color: 0.3, 0.35, 0.4, 1
        font_size: "12sp"
        size_hint_y: 0.4
        text_size: self.width, None
    Label:
        text: root.value
        color: 0.1, 0.1, 0.15, 1
        font_size: "24sp"
        bold: True
        size_hint_y: 0.6

<DashboardScreen>:
    BoxLayout:
        orientation: "vertical"

        BoxLayout:
            size_hint_y: None
            height: dp(56)
            padding: dp(8)
            canvas.before:
                Color:
                    rgba: 0.122, 0.306, 0.471, 1
                Rectangle:
                    pos: self.pos
                    size: self.size
            Label:
                text: "SA-US ERP — " + root.user_label
                bold: True
            Button:
                text: "Admin"
                size_hint_x: None
                width: dp(80)
                opacity: 1 if root.show_admin else 0
                disabled: not root.show_admin
                on_release: root.open_admin()
            Button:
                text: "Password"
                size_hint_x: None
                width: dp(90)
                on_release: root.open_change_password()
            Button:
                text: "Logout"
                size_hint_x: None
                width: dp(80)
                on_release: root.do_logout()

        ScrollView:
            BoxLayout:
                id: content
                orientation: "vertical"
                padding: dp(12)
                spacing: dp(12)
                size_hint_y: None
                height: self.minimum_height
"""
Builder.load_string(KV)


class DashboardScreen(Screen):
    user_label = StringProperty("")
    show_admin = BooleanProperty(False)

    def refresh(self):
        app = App.get_running_app()
        user = app.current_user
        self.user_label = f"{user['full_name']} ({user['role']})"
        self.show_admin = user["role"] in ("Owner", "Business Manager")

        data = app.database.dashboard(user["role"])
        content = self.ids.content
        content.clear_widgets()

        stats = [
            ("Open Leads", data.get("open_leads", 0)),
            ("Overdue AR", data.get("overdue_ar", 0)),
            ("Open Complaints", data.get("open_complaints", 0)),
            ("Open Exceptions", data.get("open_exceptions", 0)),
        ]
        stats_row = BoxLayout(size_hint_y=None, height=dp(90), spacing=dp(10))
        for label, value in stats:
            card = Factory.StatCard()
            card.label = label
            card.value = str(value)
            stats_row.add_widget(card)
        content.add_widget(stats_row)

        content.add_widget(Label(
            text="Modules", bold=True, size_hint_y=None, height=dp(30),
            color=(0.1, 0.1, 0.15, 1),
        ))
        for module, count in data.get("counts", {}).items():
            row = Button(
                text=f"{dbmod.display_name(module)}   ({count})",
                size_hint_y=None,
                height=dp(48),
                halign="left",
            )
            row.bind(on_release=lambda inst, m=module: App.get_running_app().open_module(m))
            content.add_widget(row)

    def open_admin(self):
        App.get_running_app().sm.get_screen("admin").refresh()
        App.get_running_app().sm.current = "admin"

    def open_change_password(self):
        App.get_running_app().sm.get_screen("change_password").forced = False
        App.get_running_app().sm.current = "change_password"

    def do_logout(self):
        App.get_running_app().logout()
