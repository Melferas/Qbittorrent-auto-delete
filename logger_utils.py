import logging
from logging.handlers import RotatingFileHandler
import os
from typing import Tuple, List, Dict, Any
import torrent_utils
import configparser

# Constants
MAX_BYTES = 1 * 1024 * 1024  # 1 MB
BACKUP_COUNT = 3
SEPARATOR_LENGTH = 127
MAX_NAME_LENGTH = 69
BYTES_TO_GB = 1024 ** 3
SECONDS_PER_WEEK = 7 * 86400
SECONDS_PER_DAY = 86400

class PrependingRotatingFileHandler(RotatingFileHandler):
    def __init__(self, *args, **kwargs):
        super(PrependingRotatingFileHandler, self).__init__(*args, **kwargs)
        self.log_entries: List[str] = []
        self.first_entry = True

    def emit(self, record: logging.LogRecord) -> None:
        if self.shouldRollover(record):
            self.doRollover()

        if self.first_entry:
            log_entry = "-" * SEPARATOR_LENGTH + "\n" + self.format(record)
            self.first_entry = False
        else:
            log_entry = record.getMessage()

        self.log_entries.append(log_entry)

    def write_log_entries(self) -> None:
        if self.log_entries:
            try:
                with open(self.baseFilename, 'r+') as file:
                    existing_content = file.read()
                    file.seek(0, 0)
                    file.write('\n'.join(self.log_entries) + '\n' + existing_content)
            except IOError as e:
                print(f"Error writing log entries: {e}")
            finally:
                self.log_entries = []
                self.first_entry = True

def setup_logger(log_path, debug: bool = False, log_file_name: str = 'deletelog.txt') -> Tuple[logging.Logger, PrependingRotatingFileHandler]:
    script_directory = os.path.dirname(os.path.abspath(__file__)) if not log_path else log_path
    log_file_path = os.path.join(script_directory, log_file_name)
    
    handler = PrependingRotatingFileHandler(log_file_path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT)
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    handler.setFormatter(log_formatter)
    logger = logging.getLogger()
    logger.addHandler(handler)

    if debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter('%(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    return logger, handler

def log_torrent_removal_info(torrents_info: List[Dict[str, Any]], logger: logging.Logger, bonus_rules: Dict[str, Dict[str, Any]], config: configparser.ConfigParser) -> None:
    if not torrents_info:
        logger.info("No torrents to remove based on current rules.")
        return

    logger.info(f"Total torrents to remove: {len(torrents_info)}")

    log_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'torrent_ratio_log.json')

    for torrent_info in torrents_info:
        size_gb = torrent_info['size'] / BYTES_TO_GB
        seeding_time_day = torrent_info['seeding_time'] / SECONDS_PER_DAY
        category = torrent_info.get('category', 'Unknown')
        popularity = torrent_info.get('popularity')
        eta = torrent_info.get('eta')
        tracker = torrent_info.get('tracker')

        average_ratio_per_week = torrent_utils.calculate_average_ratio(torrent_info, log_file_path, logger, bonus_rules, config)

        truncated_name = (torrent_info['name'][:MAX_NAME_LENGTH - 3] + '...') if len(torrent_info['name']) > MAX_NAME_LENGTH else torrent_info['name']

        size_str = f"{size_gb:.2f} GB".rjust(10)
        seeding_time_str = f"{seeding_time_day:.1f} Days".rjust(11)
        ratio_week_str = f"{average_ratio_per_week:.3f} R/W".rjust(11)
        popularity_str = f"{popularity:.2f} pop".rjust(6) if popularity else "N/A".rjust(6)
        eta_str = f"{eta} ETA".rjust(7)
        tracker_str = f"{tracker[8:24]}" if tracker else "N/A".rjust(20)

        logger.info(f"{truncated_name:<69}  \t{category} \t{size_str} \t{seeding_time_str} \t{ratio_week_str} \t {popularity_str} \t{eta_str} \t{tracker_str}")