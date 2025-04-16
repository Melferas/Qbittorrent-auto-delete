import os
import requests
from typing import Dict, Any
from logging import Logger
import logger_utils
import torrent_utils
from configparser import ConfigParser
import argparse

def check_space_and_remove_torrents(session: requests.Session, logger: Logger, config: ConfigParser, test_mode: bool, bonus_rules: Dict[str, Dict[str, Any]]) -> None:
    api_address = config.get('login', 'address')
    download_minspace_gb = config.get('cleanup', 'download_minspace_gb', fallback='')
    min_space_gb = config.getfloat('cleanup', 'min_space_gb')
    categories_space = [cat.strip().lower() for cat in config.get('cleanup', 'categories_to_check_for_space').split(',')]
    categories_count = [cat.strip().lower() for cat in config.get('cleanup', 'categories_to_check_for_number').split(',')]
    free_space = min_space_gb
    script_directory = os.path.dirname(os.path.abspath(__file__))

    for _ in range(2):  # Attempt twice: first try, then retry after login if unauthorized
        try:
            status = torrent_utils.get_status(session, api_address, logger)
            free_space = torrent_utils.parse_free_space(status['server_state']['free_space_on_disk'])
            logger.info(f"Free space on disk: {free_space:.2f} GB")
            all_torrents = torrent_utils.get_torrent_list(session, api_address, logger)
            break  # Exit loop if successful
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403 and _ == 0:  # Retry only on the first attempt
                torrent_utils.login_to_qbittorrent(session, api_address, 
                                                   config.get('login', 'username'), 
                                                   config.get('login', 'password'), logger)
            else:
                raise

    configured_drive_path = config.get('cleanup', 'drive_path', fallback='').strip()
    if configured_drive_path:
        free_space = torrent_utils.get_free_space(configured_drive_path)

    downloading_torrents = [t for t in all_torrents if t['state'] == 'downloading']
    total_remaining_size_gb = sum((t['size'] * (1 - t['progress'])) for t in downloading_torrents) / (1024 ** 3)

    space_left_after_downloads = free_space - total_remaining_size_gb
    logger.info(f"Free space after downloads: {space_left_after_downloads:.2f} GB")
    # Check if download_minspace_gb is set and not empty
    if download_minspace_gb and download_minspace_gb.strip():
        download_minspace_gb = float(download_minspace_gb)
        additional_space_needed = max(0, download_minspace_gb - space_left_after_downloads)
    else:
        additional_space_needed = 0

    space_needed = max(0, min_space_gb - free_space)

    category_rules = torrent_utils.get_category_rules(config, logger)

    filtered_torrents = torrent_utils.filter_torrents_by_rules(
        all_torrents, 
        category_rules, 
        logger
    )

    for torrent in filtered_torrents:
        logger.debug(f"Torrent {torrent['name']} eligible for removal: "
                f"category: {torrent['category']}, "
                f"seed time: {torrent['seeding_time']}, "
                f"ratio: {torrent['ratio']} "
                f"tracker: {torrent['tracker']} " 
                f"popularity: {torrent['popularity']} "
                f"eta: {torrent['eta']}")

    torrents_removed_by_space, space_to_be_freed = torrent_utils.remove_torrents_by_space(
        filtered_torrents,
        categories_space,
        max(additional_space_needed, space_needed),
        configured_drive_path,
        logger,
        session,
        api_address,
        test_mode,
        os.path.join(config.get('logging', 'location', fallback=script_directory), 'torrent_ratio_log.json'),
        bonus_rules,
        config
    ) if space_needed > 0 or additional_space_needed > 0 else ([], 0)

    if space_to_be_freed == 0:
        logger.info("No torrents to remove based on space requirements.")

    torrents_removed_by_count = torrent_utils.remove_torrents_by_count(
        filtered_torrents,
        categories_count,
        config.getint('cleanup', 'max_torrents_for_categories'), 
        logger, 
        session, 
        api_address, 
        test_mode,
        os.path.join(config.get('logging', 'location', fallback=script_directory), 'torrent_ratio_log.json'),
        bonus_rules,
        config.getboolean('cleanup', 'sort_count_removal_by_size', fallback=False),
        config
    )

    all_removed_torrents = torrents_removed_by_space + torrents_removed_by_count

    """Log information about removed or would-be removed torrents."""
    if all_removed_torrents:
        logger.info(f"{'TEST MODE: ' if test_mode else ''} "
                f"Free space: {free_space:.2f} GB, "
                f"DLremain: {total_remaining_size_gb:.1f} GB, "
                f"Diskneed: {max(space_needed, additional_space_needed):.0f} GB "
                f"Space to be freed: {space_to_be_freed:.2f} GB")
        logger_utils.log_torrent_removal_info(all_removed_torrents, logger, bonus_rules, config)

def main(test_mode: bool, logger: Logger, handler: Any, config: ConfigParser, session: requests.Session) -> None:
    try:
        bonus_rules = torrent_utils.load_bonus_rules(config)
        check_space_and_remove_torrents(session, logger, config, test_mode, bonus_rules)
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        handler.write_log_entries()
        return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Qbittorrent Auto Delete Script")
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