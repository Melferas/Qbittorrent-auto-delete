import unittest
from unittest.mock import patch
from torrent_filterer import connect_to_client, get_all_torrents, load_config
from torrent_fields_types import torrent_fields_types

class TestQbittorrentAutoDelete(unittest.TestCase):

    def setUp(self):
        # Mock the connection to the torrent client
        self.client = connect_to_client()
        self.config = load_config()

    @patch('main.get_all_torrents')
    def test_torrent_fields(self, mock_get_all_torrents):
        # Mock data for torrents
        mock_torrents = [
            {
                "name": "Torrent1",
                "size": 1024,
                "ratio": 1.5,
                "seed_time": 3600,
                "popularity": 100,
                "tracker": "tracker1.com"
            },
            {
                "name": "Torrent2",
                "size": 2048,
                "ratio": 0.8,
                "seed_time": 7200,
                "popularity": 50,
                "tracker": "tracker2.com"
            }
        ]
        mock_get_all_torrents.return_value = mock_torrents

        torrents = get_all_torrents(self.client)
        for torrent in torrents:
            for field, field_type in torrent_fields_types.items():
                self.assertIn(field, torrent, f"Field '{field}' is missing in torrent")
                self.assertIsInstance(torrent[field], field_type, f"Field '{field}' is not of type {field_type}")

    @patch('main.get_all_torrents')
    def test_rules_application(self, mock_get_all_torrents):
        # Mock data for torrents
        mock_torrents = [
            {
                "name": "Torrent1",
                "size": 1024,
                "ratio": 1.5,
                "seed_time": 3600,
                "popularity": 100,
                "tracker": "tracker1.com"
            },
            {
                "name": "Torrent2",
                "size": 2048,
                "ratio": 0.8,
                "seed_time": 7200,
                "popularity": 50,
                "tracker": "tracker2.com"
            }
        ]
        mock_get_all_torrents.return_value = mock_torrents

        torrents = get_all_torrents(self.client)
        rules = self.config.get("rules", {})

        for torrent in torrents:
            if "ratio" in rules:
                self.assertGreaterEqual(torrent["ratio"], rules["ratio"], f"Torrent '{torrent['name']}' failed ratio rule")
            if "popularity" in rules:
                self.assertGreaterEqual(torrent["popularity"], rules["popularity"], f"Torrent '{torrent['name']}' failed popularity rule")
            if "seed_time" in rules:
                self.assertGreaterEqual(torrent["seed_time"], rules["seed_time"], f"Torrent '{torrent['name']}' failed seed_time rule")
            if "tracker" in rules:
                self.assertIn(torrent["tracker"], rules["tracker"], f"Torrent '{torrent['name']}' failed tracker rule")

if __name__ == '__main__':
    unittest.main()