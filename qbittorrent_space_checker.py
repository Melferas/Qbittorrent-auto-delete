import os
import requests
from typing import Dict, Any
from logging import Logger
import logger_utils
import torrent_utils
from configparser import ConfigParser
import argparse

def check_space_and_remove_torrents(session: requests.Session, logger: Logger, config: ConfigParser, test_mode: bool) -> None:
    api_address = config.get('login', 'address')
    categories_force = [cat.strip().lower() for cat in config.get('cleanup', 'categories_to_force_seed').split(',')]

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
                filtered_torrents.append(torrent)
                logger.debug(f"Torrent {torrent['name']} marked for force seeding in category: {category}")

    torrent_utils.force_torrents(session, api_address, filtered_torrents, logger, test_mode)

def main(logger: Logger, handler: Any, config: ConfigParser, session: requests.Session) -> None:
    try:
        api_address = config.get('login', 'address')

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
        
        size_by_category = {}
        for torrent in all_torrents:
            torrent_size = torrent['size'] / (1024 ** 3)  # Convert size to GB
            category = torrent['category'].lower()
            size_by_category.setdefault(category, 0)
            size_by_category[category] += torrent_size
            logger.info(f"Torrent {torrent['name']} size: {torrent_size:.2f} GB, category: {category}")
        
        for category, size in size_by_category.items():
            logger.info(f"Total size for category '{category}': {size:.2f} GB")

        suma = sum(size_by_category.values())
        logger.info(f"Total size of torrents: {suma:.2f} GB")


        sum_of_seeds = 0
        for torrent in all_torrents:
            if any(category in torrent['category'] for category in ("seeds", "tv", "movies")) and torrent['eta'] == 0:
                torrent_size = torrent['size'] / (1024 ** 3)
                sum_of_seeds += torrent_size
        logger.info(f"Total size of completed seeds: {sum_of_seeds:.2f} GB")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        handler.write_log_entries()
        return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Qbittorrent Force Seeding Script")
    parser.add_argument('--config', type=str, help='Path to the configuration file')
    args = parser.parse_args()
    config_path = args.config if args.config else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini')

    script_directory = os.path.dirname(os.path.abspath(__file__))
    config = torrent_utils.load_configuration(script_directory)
    logger, log_handler = logger_utils.setup_logger(config.get('logging', 'location', fallback=''), config.getboolean('logging', 'debug'))
    session = requests.Session()
    main(logger, log_handler, config, session)