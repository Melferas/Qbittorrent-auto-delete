import os
import requests
from typing import Dict, Any
from logging import Logger
import logger_utils
import torrent_utils
from configparser import ConfigParser
import argparse

def force_seed(session: requests.Session, logger: Logger, config: ConfigParser, test_mode: bool) -> None:
    api_address = config.get('login', 'address')
    categories_force = [cat.strip().lower() for cat in config.get('cleanup', 'categories_to_force_seed').split(',')]
    tracker_names = [kw.strip().lower() for kw in config.get('cleanup', 'trackers_to_force_seed').split(',') if kw.strip()]

    for _ in range(2):  # Attempt twice: first try, then retry after login if unauthorized
        try:
            all_torrents = torrent_utils.get_torrent_list(session, api_address, logger)
            break  # Exit loop if successful
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403 and _ == 0:  # Retry only on the first attempt
                torrent_utils.login_to_qbittorrent(session, api_address, 
                                                   config.get('login', 'username'), 
                                                   config.get('login', 'password'), logger)
            else:
                raise

    filtered_torrents = []
    
    for torrent in all_torrents:
        for category in categories_force:
            if torrent['category'].lower() == category:
                if any(tracker_prefix in torrent['name'].lower() for tracker_prefix in tracker_names):
                    filtered_torrents.append(torrent)
                    logger.debug(f"Torrent {torrent['name']} marked for force seeding in category: {category} (matched keyword in name)")


    torrent_utils.force_torrents(session, api_address, filtered_torrents, logger, test_mode)

def main(test_mode: bool, logger: Logger, handler: Any, config: ConfigParser, session: requests.Session) -> None:
    try:
        force_seed(session, logger, config, test_mode)
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        handler.write_log_entries()
        return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Qbittorrent Force Seeding Script")
    parser.add_argument('--config', type=str, help='Path to the configuration file')
    parser.add_argument('--test', action='store_true', help='Run in test mode')
    args = parser.parse_args()

    config_path = args.config if args.config else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini')
    test_mode = args.test

    script_directory = os.path.dirname(os.path.abspath(__file__))
    config = torrent_utils.load_configuration(script_directory)
    logger, log_handler = logger_utils.setup_logger(config.get('logging', 'location', fallback=''), config.getboolean('logging', 'debug'))
    session = requests.Session()
    main(test_mode, logger, log_handler, config, session)