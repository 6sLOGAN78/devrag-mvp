import os
import logging
from logging.handlers import RotatingFileHandler

initialized_root_logger = False

def get_project_base_directory():
    # Assumes common/log_utils.py is one level down from the root (devRag_@)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def getLogger(name: str):
    """Factory to get logger instances ensuring root is initialized."""
    return logging.getLogger(name)

def init_root_logger(logfile_basename: str, log_format: str = "%(asctime)s %(levelname)s %(message)s"):
    global initialized_root_logger
    if initialized_root_logger:
        return
    initialized_root_logger = True

    logger = logging.getLogger()
    logger.handlers.clear()
    
    # Logs directory
    log_dir = os.path.join(get_project_base_directory(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    log_path = os.path.join(log_dir, f"{logfile_basename}.log")
    formatter = logging.Formatter(log_format)

    # 1. RotatingFileHandler: 10MB, 5 backups
    file_handler = RotatingFileHandler(log_path, maxBytes=10 * 1024 * 1024, backupCount=5)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 2. StreamHandler: stdout
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # Capture warnings
    logging.captureWarnings(True)

    # 3. Dynamic Filtering via LOG_LEVELS
    # e.g., LOG_LEVELS="root=INFO,peewee=WARNING"
    log_levels_str = os.environ.get("LOG_LEVELS", "root=INFO")
    for mapping in log_levels_str.split(","):
        parts = mapping.split("=")
        if len(parts) == 2:
            pkg_name = parts[0].strip()
            level_name = parts[1].strip().upper()
            
            # Map string to int level (e.g., 'INFO' -> 20)
            level = getattr(logging, level_name, logging.INFO)
            
            if pkg_name == "root":
                logger.setLevel(level)
            else:
                logging.getLogger(pkg_name).setLevel(level)
