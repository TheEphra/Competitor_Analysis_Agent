import io
import unittest
from unittest.mock import patch

from flask_server import WORKSPACES, app, fresh_workspace, normalize_website_url


class FlaskSelectionTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.client.get("/")
        with self.client.session_transaction() as browser_session:
            workspace_id = browser_session["workspace_id"]
        self.workspace = WORKSPACES[workspace_id]
        self.workspace.clear()
        self.workspace.update(fresh_workspace())

    def csrf(self):
        return self.workspace["csrf"]

    def test_selected_checkbox_adds_only_checked_business(self):
        self.workspace["discovered"] = [
            {"Business": "Unselected Salon", "Website": "https://one.example"},
            {"Business": "Selected Salon", "Website": "https://two.example"},
            {"Business": "No Website Salon", "Website": ""},
        ]

        response = self.client.post(
            "/add-discovered",
            data={"csrf_token": self.csrf(), "place_index": ["1"]},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.workspace["competitors"],
            [{"Business": "Selected Salon", "Website": "https://two.example"}],
        )

    def test_failed_new_search_clears_old_choices_and_keeps_search_context(self):
        self.workspace["discovered"] = [{"Business": "Old result", "Website": "https://old.example"}]

        with patch("flask_server.discover_competitors", side_effect=RuntimeError("offline")) as search:
            response = self.client.post(
                "/discover",
                data={"csrf_token": self.csrf(), "location": "Parassala", "industry": "Salon", "limit": "10"},
            )

        search.assert_called_once_with("Parassala", "Salon", 10)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.workspace["discovered"], [])
        self.assertEqual(self.workspace["profile"]["location"], "Parassala")
        self.assertEqual(self.workspace["profile"]["industry"], "Salon")

    def test_manual_competitor_rejects_non_http_link_schemes(self):
        response = self.client.post(
            "/competitors/add",
            data={"csrf_token": self.csrf(), "business": "Unsafe", "website": "javascript:alert(1)"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.workspace["competitors"], [])

    def test_url_normalizer_adds_https_and_rejects_credentials(self):
        self.assertEqual(normalize_website_url("example.com/page"), "https://example.com/page")
        with self.assertRaises(ValueError):
            normalize_website_url("https://user:pass@example.com")

    def test_csv_import_skips_unsafe_links(self):
        upload = (io.BytesIO(b"Business,Website\nUnsafe,javascript:alert(1)\nSafe,example.com\n"), "competitors.csv")
        response = self.client.post(
            "/competitors/import",
            data={"csrf_token": self.csrf(), "file": upload},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.workspace["competitors"],
            [{"Business": "Safe", "Website": "https://example.com"}],
        )

    def test_pdf_report_handles_ampersands_in_profile_text(self):
        self.workspace["profile"]["company"] = "A & B <Salon>"
        self.workspace["results"] = [{
            "Business": "A & B",
            "Website": "https://example.com",
            "Status": "Analysed",
            "Website Score": 80,
            "Coverage": "6/6 signals",
            "HTTPS": True,
        }]

        response = self.client.get("/download.pdf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")
        self.assertTrue(response.data.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
