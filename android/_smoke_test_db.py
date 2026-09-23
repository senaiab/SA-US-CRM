import tempfile, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import db as dbmod

tmpdir = tempfile.mkdtemp()
database = dbmod.Database(os.path.join(tmpdir, "test.db"))

user = database.login("admin", "admin123")
assert user["role"] == "Owner"
assert user["must_change_password"] == 1
print("login OK")

try:
    database.login("admin", "wrong")
    assert False
except dbmod.AuthError:
    print("wrong password rejected OK")

database.change_password("admin", "admin123", "newpassword123")
user2 = database.login("admin", "newpassword123")
assert user2["must_change_password"] == 0
print("change_password OK")

rec = database.create_record("leads", {"Lead ID": "HACKED", "Inquiry Date": "1999-01-01", "Client Name": "Acme"}, "admin")
assert rec["data"]["Lead ID"].startswith("L-"), rec["data"]
assert rec["data"]["Inquiry Date"] != "1999-01-01"
print("auto-id create OK:", rec["data"]["Lead ID"], rec["data"]["Inquiry Date"])

rec2 = database.create_record("leads", {"Client Name": "Beta"}, "admin")
assert rec2["data"]["Lead ID"].endswith("-002"), rec2["data"]["Lead ID"]
print("sequence increment OK:", rec2["data"]["Lead ID"])

updated = database.update_record(rec["id"], {"Lead ID": "STILL-HACKED", "Inquiry Date": "2000-01-01", "Client Name": "Acme Updated"}, "admin")
assert updated["data"]["Lead ID"] == rec["data"]["Lead ID"], updated["data"]
assert updated["data"]["Inquiry Date"] == rec["data"]["Inquiry Date"]
assert updated["data"]["Client Name"] == "Acme Updated"
print("update-lock OK:", updated["data"]["Lead ID"], updated["data"]["Inquiry Date"])

quote = database.create_record("quotations", {"Lead ID": rec["data"]["Lead ID"], "Client Name": "Acme Updated", "Quoted Amount": "500"}, "admin")
assert quote["data"]["Lead ID"] == rec["data"]["Lead ID"]
assert quote["data"]["Quote ID"].startswith("Q-")
print("cross-ref OK:", quote["data"]["Lead ID"], quote["data"]["Quote ID"])

booking = database.create_record("bookings", {"Booking Ref": "PNR123", "Booking Date": "1999-09-09"}, "admin")
assert booking["data"]["Booking Ref"] == "PNR123"
assert booking["data"]["Booking Date"] != "1999-09-09"
print("booking auto-date OK, Booking Ref stayed manual:", booking["data"]["Booking Ref"], booking["data"]["Booking Date"])

assert dbmod.Database.can_access("Sales Agent", "leads", write=True) is True
assert dbmod.Database.can_access("Sales Agent", "ar", write=True) is False
assert dbmod.Database.can_access("Viewer", "leads", write=False) is True
assert dbmod.Database.can_access("Viewer", "leads", write=True) is False
print("permissions OK")

database.create_or_update_user("agent1", "Agent One", "Sales Agent", "password123", "admin")
users = database.list_users()
assert any(u["username"] == "agent1" for u in users)
database.reset_password("agent1", "newpass1234", "admin")
u = database.login("agent1", "newpass1234")
assert u["must_change_password"] == 1
print("admin user mgmt OK")

try:
    database.set_user_active("admin", False, "admin")
    assert False
except dbmod.ValidationError:
    print("self-deactivate blocked OK")
database.set_user_active("agent1", False, "admin")
try:
    database.login("agent1", "newpass1234")
    assert False
except dbmod.AuthError:
    print("deactivated user login blocked OK")

dash = database.dashboard("Owner")
assert dash["counts"]["leads"] == 2
assert dash["open_leads"] == 2
print("dashboard OK:", dash)

print("\nALL SMOKE TESTS PASSED")
