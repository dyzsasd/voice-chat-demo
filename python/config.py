import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# Reading environment variables
OPENAI_TOKEN = os.getenv('OPENAI_TOKEN')
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny")
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
