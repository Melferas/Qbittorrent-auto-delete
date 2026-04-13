import os
import requests
import time
from typing import Any
from logging import Logger
import logger_utils
import torrent_utils
from configparser import ConfigParser
import argparse

def main(logger: Logger, handler: Any, config: ConfigParser, session: requests.Session, fuzzy_match: bool = False, min_group_size: int = 2, exclude_categories: str = 'cross-seed-link') -> None:
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
        
        # Group torrents by hash
        hash_groups = {}
        for torrent in all_torrents:
            torrent_hash = torrent.get('hash', '').upper()  # Normalize to uppercase
            if torrent_hash not in hash_groups:
                hash_groups[torrent_hash] = []
            hash_groups[torrent_hash].append(torrent)

        # If fuzzy matching enabled, also group by size + normalized name
        if fuzzy_match:
            import difflib
            size_name_groups = {}
            for torrent in all_torrents:
                size = torrent.get('size', 0)
                name = torrent.get('name', '').lower().replace(' ', '').replace('-', '').replace('_', '')
                key = (size, name)
                if key not in size_name_groups:
                    size_name_groups[key] = []
                size_name_groups[key].append(torrent)
            
            # Merge fuzzy groups into hash_groups if they have >1 and aren't already grouped by hash
            for key, group in size_name_groups.items():
                if len(group) > 1:
                    # Check if any in group have same hash
                    hashes = set(t.get('hash', '').upper() for t in group)
                    if len(hashes) > 1:  # Different hashes, so fuzzy match
                        # Create a pseudo-hash key for fuzzy groups
                        fuzzy_key = f"fuzzy_{key[0]}_{key[1]}"
                        hash_groups[fuzzy_key] = group

        # Filter to groups with at least min_group_size
        cross_seed_groups = {k: v for k, v in hash_groups.items() if len(v) >= min_group_size}

        # Identify originals and copies, calculate totals
        exclude_cats = set(cat.strip().lower() for cat in exclude_categories.split(','))
        total_groups = len(cross_seed_groups)
        total_copies = 0

        # Prepare groups with originals/copies
        processed_groups = []
        for group_key, torrents in cross_seed_groups.items():
            # Find original
            originals = [t for t in torrents if t.get('category', '').lower() not in exclude_cats]
            if not originals:
                originals = torrents
            
            originals.sort(key=lambda t: (t.get('num_seeds', 0), t.get('seeding_time', 0)), reverse=True)
            original = originals[0]
            copies = [t for t in torrents if t != original]
            
            total_copies += len(copies)
            
            processed_groups.append((group_key, torrents, original, copies))

        # Sort groups by number of copies descending
        processed_groups.sort(key=lambda x: len(x[3]), reverse=True)

        logger.info("=" * 60)
        logger.info("CROSS-SEED DETECTION REPORT")
        logger.info("=" * 60)
        logger.info(f"Total cross-seed groups: {total_groups}")
        logger.info(f"Total cross-seed copies identified: {total_copies}")
        logger.info("(Note: Cross-seeds use hardlinks, so deleting copies won't reclaim disk space)")
        logger.info("")

        if total_groups == 0:
            logger.info("No cross-seed groups found.")
            if not fuzzy_match:
                logger.info("Tip: Use --fuzzy-match to detect cross-seeds by size and name similarity (for torrents with different hashes).")
            return

        group_num = 1
        for group_key, torrents, original, copies in processed_groups:
            group_name = original.get('name', 'Unknown')
            if group_key.startswith('fuzzy_'):
                logger.info(f"Group {group_num}: \"{group_name}\" (Fuzzy match)")
            else:
                logger.info(f"Group {group_num}: \"{group_name}\" (Hash: {group_key[:16]}...)")
            
            # Log original
            orig_size_gb = original['size'] / (1024 ** 3)
            orig_tracker = original.get('tracker', 'N/A')[:50]
            orig_seeds = original.get('num_seeds', 'N/A')
            logger.info(f"🏆 Original: {original['name']} [{original.get('category', 'N/A')}] - {orig_size_gb:.2f} GB - Tracker: {orig_tracker} - Seeders: {orig_seeds}")
            
            # Log copies
            for i, copy in enumerate(copies, 1):
                copy_size_gb = copy['size'] / (1024 ** 3)
                copy_tracker = copy.get('tracker', 'N/A')[:50]
                copy_seeds = copy.get('num_seeds', 'N/A')
                logger.info(f"📋 Copy {i}: {copy['name']} [{copy.get('category', 'N/A')}] - {copy_size_gb:.2f} GB - Tracker: {copy_tracker} - Seeders: {copy_seeds}")
            
            logger.info(f"   → Copies in this group: {len(copies)}")
            logger.info("")
            group_num += 1

    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        handler.write_log_entries()
        return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Qbittorrent Cross-Seed Detector Script")
    parser.add_argument('--config', type=str, help='Path to the configuration file')
    parser.add_argument('--fuzzy-match', action='store_true', help='Enable fuzzy matching by size and name similarity')
    parser.add_argument('--min-group-size', type=int, default=2, help='Minimum number of torrents in a group to report')
    parser.add_argument('--exclude-categories', type=str, default='cross-seed-link', help='Comma-separated categories to exclude as originals')
    args = parser.parse_args()
    config_path = args.config if args.config else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini')

    script_directory = os.path.dirname(os.path.abspath(__file__))
    config = torrent_utils.load_configuration(script_directory)
    logger, log_handler = logger_utils.setup_logger(config.get('logging', 'location', fallback=''), config.getboolean('logging', 'debug'))
    session = requests.Session()
    main(logger, log_handler, config, session, fuzzy_match=args.fuzzy_match, min_group_size=args.min_group_size, exclude_categories=args.exclude_categories)