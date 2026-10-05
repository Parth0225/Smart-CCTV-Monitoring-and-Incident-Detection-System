import sqlite3
import unittest

from run import DATABASE_PATH, app


class SettingsApiTests(unittest.TestCase):
    def setUp(self):
        with sqlite3.connect(DATABASE_PATH) as connection:
            connection.execute("DELETE FROM system_logs")
            connection.execute("DELETE FROM incidents")
            connection.execute("DELETE FROM users")
            connection.execute("DELETE FROM app_settings")
            connection.execute("DELETE FROM cameras")
            connection.execute("INSERT OR IGNORE INTO cameras (camera_id, camera_name, camera_status) VALUES (1, 'Laptop Webcam', 'Online')")
            connection.execute(
                "INSERT INTO app_settings (setting_key, setting_value) VALUES (?, ?)",
                ("camera_name", "Laptop Webcam"),
            )
            connection.execute(
                "INSERT INTO app_settings (setting_key, setting_value) VALUES (?, ?)",
                ("camera_status", "Online"),
            )
            connection.execute(
                "INSERT INTO app_settings (setting_key, setting_value) VALUES (?, ?)",
                ("motion_detection", "True"),
            )
            connection.execute(
                "INSERT INTO app_settings (setting_key, setting_value) VALUES (?, ?)",
                ("person_detection", "True"),
            )
            connection.execute(
                "INSERT INTO app_settings (setting_key, setting_value) VALUES (?, ?)",
                ("confidence_threshold", "80"),
            )

    def _register_and_login(self, client, username="settingsuser"):
        client.post(
            "/api/register",
            json={"name": "Test User", "username": username, "password": "secret123"},
        )
        response = client.post(
            "/api/login",
            json={"username": username, "password": "secret123"},
        )
        self.assertEqual(response.status_code, 200)

    def test_settings_api_round_trip(self):
        with app.test_client() as client:
            self._register_and_login(client, "settingsuser_roundtrip")

            payload = {
                "camera_name": "Front Gate",
                "camera_status": "Offline",
                "motion_detection": True,
                "person_detection": False,
                "confidence_threshold": 92,
            }

            response = client.post("/api/settings", json=payload)
            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

            saved = response.get_json()
            self.assertEqual(saved["camera_name"], "Front Gate")
            self.assertEqual(saved["camera_status"], "Offline")
            self.assertTrue(saved["motion_detection"])
            self.assertFalse(saved["person_detection"])
            self.assertEqual(saved["confidence_threshold"], 92)

            get_response = client.get("/api/settings")
            self.assertEqual(get_response.status_code, 200)
            loaded = get_response.get_json()
            self.assertEqual(loaded["camera_name"], "Front Gate")
            self.assertEqual(loaded["camera_status"], "Offline")
            self.assertTrue(loaded["motion_detection"])
            self.assertFalse(loaded["person_detection"])
            self.assertEqual(loaded["confidence_threshold"], 92)

    def test_settings_defaults_are_loaded(self):
        with app.test_client() as client:
            self._register_and_login(client, "settingsuser_defaults")
            response = client.get("/api/settings")
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertEqual(data["camera_name"], "Laptop Webcam")
            self.assertEqual(data["camera_status"], "Online")
            self.assertTrue(data["motion_detection"])
            self.assertTrue(data["person_detection"])
            self.assertGreater(data["confidence_threshold"], 0)
            self.assertLessEqual(data["confidence_threshold"], 100)


if __name__ == "__main__":
    unittest.main()
