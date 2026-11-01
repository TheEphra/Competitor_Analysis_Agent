import unittest
from unittest.mock import patch

import requests

from src.competitor_discovery import discover_competitors


class DiscoveryTests(unittest.TestCase):
    def test_missing_key_does_not_call_google(self):
        with patch("src.competitor_discovery.load_dotenv"), \
             patch.dict("os.environ", {}, clear=True), \
             patch("src.competitor_discovery.requests.post") as post:
            with self.assertRaisesRegex(RuntimeError, "No live request was made"):
                discover_competitors("Parassala", "Salon")
            post.assert_not_called()

    def test_maps_text_search_response(self):
        response = requests.Response()
        response.status_code = 200
        response._content = (b'{"places":[{"displayName":{"text":"A Salon"},'
                            b'"formattedAddress":"Main Road", "websiteUri":"https://a.example",'
                            b'"location":{"latitude":8.3,"longitude":77.1}}]}')
        with patch("src.competitor_discovery.load_dotenv"), \
             patch("src.competitor_discovery.requests.post", return_value=response) as post:
            found = discover_competitors("Parassala", "Salon", 5, api_key="test-key")
        self.assertEqual(found[0]["Business"], "A Salon")
        self.assertEqual(found[0]["Latitude"], 8.3)
        self.assertEqual(found[0]["Source"], "Google Places API (New)")
        self.assertEqual(post.call_args.kwargs["json"]["textQuery"], "hair salons and beauty salons in Parassala")
        self.assertNotIn("places.rating", post.call_args.kwargs["headers"]["X-Goog-FieldMask"])

    def test_validates_inputs_before_request(self):
        for location, industry, limit in [("", "salon", 5), ("Here", "salon", 21)]:
            with self.subTest(location=location, industry=industry, limit=limit):
                with patch("src.competitor_discovery.requests.post") as post:
                    with self.assertRaises(ValueError):
                        discover_competitors(location, industry, limit, api_key="key")
                    post.assert_not_called()

    def test_custom_industry_is_used_as_typed(self):
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"places":[]}'
        with patch("src.competitor_discovery.load_dotenv"), \
             patch("src.competitor_discovery.requests.post", return_value=response) as post:
            self.assertEqual(
                discover_competitors("Parassala", "mobile bike repair", api_key="test-key"),
                [],
            )
        self.assertEqual(
            post.call_args.kwargs["json"]["textQuery"],
            "mobile bike repair in Parassala",
        )


if __name__ == "__main__":
    unittest.main()
