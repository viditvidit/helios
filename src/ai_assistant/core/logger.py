import logging
import logging.config
from pathlib import Path
import yaml

def setup_logging(verbose: bool = False):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )
    """Setup logging configuration from configs/logging.yaml."""
    config_path = Path("configs/logging.yaml")
    level = logging.DEBUG if verbose else logging.INFO

    if config_path.exists():
        try:
            with open(config_path, 'rt') as f:
                config_data = yaml.safe_load(f.read())
            logging.config.dictConfig(config_data)
            logging.getLogger("ai_assistant").setLevel(level)
            logging.getLogger("root").setLevel(level)
        except Exception as e:
            logging.basicConfig(level=level, format='%(asctime)s - %(levelname)s - %(message)s')
            logging.warning(f"Failed to load logging config from {config_path}: {e}. Using basic config.")
    else:
        logging.basicConfig(level=level, format='%(asctime)s - %(levelname)s - %(message)s')
        logging.warning(f"{config_path} not found. Using basic config.")
    
    if not verbose:
        logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
        logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
        logging.getLogger("aiohttp").setLevel(logging.WARNING)
        logging.getLogger("asyncio").setLevel(logging.WARNING)