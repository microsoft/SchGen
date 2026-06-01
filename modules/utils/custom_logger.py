import logging

# ANSI escape codes for colors
class Colors:
    RESET = '\033[0m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    ORANGE = '\033[33m'

class ColoredFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': Colors.BLUE,
        'INFO': Colors.GREEN,
        'WARNING': Colors.YELLOW,
        'ERROR': Colors.RED,
        'CRITICAL': Colors.PURPLE
    }

    def format(self, record):
        color = self.COLORS.get(record.levelname, Colors.RESET)
        
        # Wrap the whole message with the level's color, except for DEBUG
        if record.levelname != 'DEBUG':
            record.msg = f'{color}{record.msg}{Colors.RESET}'
        
        # Add color to levelname
        record.levelname = f'{color}{record.levelname}{Colors.RESET}'
        
        return super().format(record)

LOG_DIR = './logs/'

def setup_logger(level=logging.DEBUG, log_capture_string=None):
    logger = logging.getLogger(__name__)
    logger.setLevel(level)

    # Check if the logger already has handlers
    if not logger.handlers:
        # StreamHandler for terminal output
        stream_handler = logging.StreamHandler()
        stream_formatter = ColoredFormatter(
            '[%(asctime)s] %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
            )
        stream_handler.setFormatter(stream_formatter)

        # Add handlers to the logger
        logger.addHandler(stream_handler)

        # Ensure log directory exists
        import os, datetime
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR, exist_ok=True)

        # Create a unique log file with timestamp
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        log_filename = os.path.join(LOG_DIR, f'log_{timestamp}.ansi')

        file_handler = logging.FileHandler(log_filename, encoding="utf-8")

        file_handler.setFormatter(stream_formatter)

        logger.addHandler(file_handler)

    # Optional: StringIO Handler for capturing logs to a variable
    if log_capture_string is not None:
        stream_formatter = ColoredFormatter(
            '[%(asctime)s] %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
            )
        string_handler = logging.StreamHandler(log_capture_string)
        string_handler.setFormatter(stream_formatter)
        logger.addHandler(string_handler)


    return logger

import io
if __name__ == '__main__':
    # Create a logger instance
    # logger = setup_logger()

    # Usage example:
    log_stream = io.StringIO()
    logger = setup_logger(log_capture_string=log_stream)
    logger.info("Hello, world!")
    logs_collected = log_stream.getvalue()
    print("Collected logs:\n", logs_collected)

    log_stream.seek(0)
    log_stream.truncate(0)

    # Different logging levels
    logger.debug('Debug message')    # Detailed info for debugging
    logger.info('Info message')     # General info about program execution
    logger.warning('Warning')       # Something unexpected, but program still works
    logger.error('Error message')   # More serious problem
    logger.critical('Critical')     # Program may not be able to continue


    print("Collected logs:\n", log_stream.getvalue())


    # # Advanced setup with both file and console handlers
    # def setup_logger():
    #     logger = logging.getLogger(__name__)
    #     logger.setLevel(logging.DEBUG)

    #     # Create handlers
    #     file_handler = logging.FileHandler('app.log')
    #     console_handler = logging.StreamHandler()
        
    #     # Set levels
    #     file_handler.setLevel(logging.DEBUG)
    #     console_handler.setLevel(logging.INFO)
        
    #     # Create formatters
    #     formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    #     file_handler.setFormatter(formatter)
    #     console_handler.setFormatter(formatter)
        
    #     # Add handlers to logger
    #     logger.addHandler(file_handler)
    #     logger.addHandler(console_handler)
        
    #     return logger

    # # Usage
    # logger = setup_logger()
    # logger.debug("Debug message will go to file only")
    # logger.info("Info message will go to both file and console")