# retrieves the api key from the .env file

import os
from dotenv import load_dotenv

load_dotenv()

hf_token = os.getenv("HF_TOKEN")

if not hf_token:
    raise RuntimeError("HF_TOKEN is not set. Create a .env file in the project root directory and set the access token in the files")

if __name__ == "__main__":
    print(f"Huggingface token: {hf_token}")