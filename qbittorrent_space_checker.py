import os
import requests
import time
from typing import Any
from logging import Logger
import logger_utils
import torrent_utils
from configparser import ConfigParser
import argparse

def main(logger: Logger, handler: Any, config: ConfigParser, session: requests.Session, detail: bool = False, verbose: bool = False, enable_cross_report: bool = False, max_trackers: int = 10) -> None:
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

        exclude_categories = [] if enable_cross_report else ['cross-seed-link']
        filtered_size_by_category = {cat: size for cat, size in size_by_category.items() if cat not in exclude_categories}
        filtered_size_by_tracker_and_category = {}
        for tracker, cat_dict in size_by_tracker_and_category.items():
            filtered_size_by_tracker_and_category[tracker] = {cat: size for cat, size in cat_dict.items() if cat not in exclude_categories}
        filtered_size_by_tracker = {tracker: sum(cat_dict.values()) for tracker, cat_dict in filtered_size_by_tracker_and_category.items()}
        total_size = sum(filtered_size_by_category.values())
        
        # Calculate top contributors for quick insights
        top_categories = sorted(filtered_size_by_category.items(), key=lambda x: x[1], reverse=True)[:5]
        sorted_trackers = sorted(filtered_size_by_tracker.items(), key=lambda x: x[1], reverse=True)
        displayed_trackers = sorted_trackers[:max_trackers] if max_trackers > 0 else sorted_trackers
        top_trackers = displayed_trackers[:5]
        
        # Summary section with highlights
        logger.info("=" * 60)
        logger.info("TORRENT STORAGE SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total torrents: {len(all_torrents)}")
        logger.info(f"Total size: {total_size:.2f} GB ({total_size/1024:.2f} TB)")
        logger.info("")
        logger.info("🔍 KEY INSIGHTS:")
        logger.info(f"   • Largest category: '{top_categories[0][0]}' ({top_categories[0][1]:.2f} GB)")
        logger.info(f"   • Largest tracker: '{top_trackers[0][0][:30]}...' ({top_trackers[0][1]:.2f} GB)")
        if len(all_torrents) > 0:
            avg_size = total_size / len(all_torrents)
            logger.info(f"   • Average torrent size: {avg_size:.2f} GB")
        logger.info("")

        # By category section (sorted, with percentages)
        logger.info("=" * 60)
        logger.info("BY CATEGORY (Top 10, sorted by size)")
        logger.info("=" * 60)
        sorted_categories = sorted(filtered_size_by_category.items(), key=lambda x: x[1], reverse=True)
        for i, (category, size) in enumerate(sorted_categories[:10]):
            pct = (size / total_size) * 100 if total_size > 0 else 0
            marker = "🏆" if i == 0 else "📊"
            logger.info(f"{marker} {category:18s} {size:10.2f} GB ({pct:5.1f}%)")
        if len(sorted_categories) > 10:
            others = sum(size for _, size in sorted_categories[10:])
            logger.info(f"   ... and {len(sorted_categories)-10} more categories: {others:.2f} GB")
        logger.info("")

        # By tracker section (top X, with warnings for large ones)
        logger.info("=" * 60)
        logger.info(f"BY TRACKER (Top {len(displayed_trackers)}, sorted by size)")
        logger.info("=" * 60)
        for i, (tracker, size) in enumerate(displayed_trackers):
            pct = (size / total_size) * 100 if total_size > 0 else 0
            marker = "🚨" if size > 500 else "📍"  # Warn if >500 GB
            short_tracker = tracker[:50] + "..." if len(tracker) > 50 else tracker
            logger.info(f"{marker} {short_tracker:50s} {size:10.2f} GB ({pct:5.1f}%)")
            if detail:
                cat_dict = filtered_size_by_tracker_and_category.get(tracker, {})
                sorted_cats = sorted(cat_dict.items(), key=lambda x: x[1], reverse=True)
                for cat, cat_size in sorted_cats[:3]:  # Top 3 categories per tracker
                    logger.info(f"     └─ {cat:16s} {cat_size:10.2f} GB")
                if len(sorted_cats) > 3:
                    others_cat = sum(size for _, size in sorted_cats[3:])
                    logger.info(f"     └─ ... {len(sorted_cats)-3} more: {others_cat:.2f} GB")
        if max_trackers > 0 and len(sorted_trackers) > max_trackers:
            others_track = sum(size for _, size in sorted_trackers[max_trackers:])
            logger.info(f"   ... and {len(sorted_trackers)-max_trackers} more trackers: {others_track:.2f} GB")
        elif max_trackers == 0:
            # No "more" message if showing all
            pass
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
    parser.add_argument('--enable-cross-report', action='store_true', help='Include cross-seed-link category in the report')
    parser.add_argument('--max-trackers', type=int, default=10, help='Maximum number of trackers to display (0 for all)')
    args = parser.parse_args()
    config_path = args.config if args.config else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini')

    script_directory = os.path.dirname(os.path.abspath(__file__))
    config = torrent_utils.load_configuration(script_directory)
    logger, log_handler = logger_utils.setup_logger(config.get('logging', 'location', fallback=''), config.getboolean('logging', 'debug'))
    session = requests.Session()
    main(logger, log_handler, config, session, detail=args.detail, verbose=args.verbose, enable_cross_report=args.enable_cross_report, max_trackers=args.max_trackers)