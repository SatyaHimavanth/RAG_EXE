import logging

def setup_logger(name):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
    )
    return logging.getLogger(name)
