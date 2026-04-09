import os
import requests
from typing import Any
from logging import Logger
import logger_utils
import torrent_utils
from configparser import ConfigParser
import argparse

def main(logger: Logger, handler: Any, config: ConfigParser, session: requests.Session, detail: bool = False, verbose: bool = False) -> None:
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
        size_by_tracker = {}
        size_by_tracker_and_category = {}

        for torrent in all_torrents:
            torrent_size = torrent['size'] / (1024 ** 3)  # Convert size to GB
            category = torrent['category'].lower()
            tracker = torrent.get('tracker', '').lower()

            # By category
            size_by_category.setdefault(category, 0)
            size_by_category[category] += torrent_size

            # By tracker
            size_by_tracker.setdefault(tracker, 0)
            size_by_tracker[tracker] += torrent_size

            # By tracker and category
            if tracker not in size_by_tracker_and_category:
                size_by_tracker_and_category[tracker] = {}
            size_by_tracker_and_category[tracker].setdefault(category, 0)
            size_by_tracker_and_category[tracker][category] += torrent_size

            if verbose:
                logger.info(f"Torrent {torrent['name']} size: {torrent_size:.2f} GB, category: {category}, tracker: {tracker}")

        sorted_trackers = sorted(size_by_tracker.items(), key=lambda x: x[1], reverse=True)
        total_size = sum(size_by_category.values())
        
        # Summary section
        logger.info("=" * 60)
        logger.info("TORRENT STORAGE SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total torrents: {len(all_torrents)}")
        logger.info(f"Total size: {total_size:.2f} GB ({total_size/1024:.2f} TB)")
        logger.info("")

        # By category section
        logger.info("=" * 60)
        logger.info("BY CATEGORY")
        logger.info("=" * 60)
        for category, size in sorted(size_by_category.items()):
            logger.info(f"{category:20s} {size:10.2f} GB")
        logger.info("")

        # By tracker section
        logger.info("=" * 60)
        logger.info("BY TRACKER")
        logger.info("=" * 60)
        for tracker, size in sorted_trackers:
            logger.info(f"{tracker:20s} {size:10.2f} GB")
            if detail:
                cat_dict = size_by_tracker_and_category[tracker]
                for category in sorted(cat_dict):
                    cat_size = cat_dict[category]
                    logger.info(f"  └─ {category:18s} {cat_size:10.2f} GB")
        logger.info("")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        handler.write_log_entries()
        return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Qbittorrent Space Checker Script")
    parser.add_argument('--config', type=str, help='Path to the configuration file')
    parser.add_argument('--detail', action='store_true', help='Show detailed category-by-tracker breakdown')
    parser.add_argument('--verbose', action='store_true', help='Show individual torrent details')
    args = parser.parse_args()
    config_path = args.config if args.config else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini')

    script_directory = os.path.dirname(os.path.abspath(__file__))
    config = torrent_utils.load_configuration(script_directory)
    logger, log_handler = logger_utils.setup_logger(config.get('logging', 'location', fallback=''), config.getboolean('logging', 'debug'))
    session = requests.Session()
    main(logger, log_handler, config, session, detail=args.detail, verbose=args.verbose)