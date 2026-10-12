from functools import lru_cache
from azure.storage.blob import BlobServiceClient

import os

AZURE_STORAGE_CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")

@lru_cache(maxsize=1)
def load_system_prompt(prompt_name: str) -> str:
    blob_service = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    blob_client = blob_service.get_blob_client(
        container="diagram-iq-blob-az-eastus",
        blob=f"{prompt_name}.txt",
    )
    return blob_client.download_blob().readall().decode("utf-8")