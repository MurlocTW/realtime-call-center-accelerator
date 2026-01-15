import os
import uuid
from typing import List, Dict, Optional
from datetime import datetime
from azure.storage.blob.aio import BlobServiceClient, ContainerClient


class PDFManager:
    """Manages PDF files in Azure Blob Storage."""

    def __init__(self, connection_string: str, container_name: str):
        self.connection_string = connection_string
        self.container_name = container_name
        self._blob_service_client: Optional[BlobServiceClient] = None
        self._container_client: Optional[ContainerClient] = None

    async def _get_container_client(self) -> ContainerClient:
        """Get or create the container client."""
        if self._container_client is None:
            self._blob_service_client = BlobServiceClient.from_connection_string(
                self.connection_string
            )
            self._container_client = self._blob_service_client.get_container_client(
                self.container_name
            )
        return self._container_client

    async def upload_pdf(
        self,
        file_content: bytes,
        original_filename: str
    ) -> Dict[str, str]:
        """
        Upload a PDF file to blob storage.

        Args:
            file_content: The PDF file content as bytes
            original_filename: Original filename from upload

        Returns:
            Dict with id, filename, and upload timestamp
        """
        container = await self._get_container_client()

        # Generate UUID for the file
        file_id = str(uuid.uuid4())

        # Store with UUID prefix to ensure uniqueness
        blob_name = f"{file_id}_{original_filename}"

        blob_client = container.get_blob_client(blob_name)

        # Upload with metadata
        upload_timestamp = datetime.utcnow().isoformat()
        metadata = {
            "file_id": file_id,
            "original_filename": original_filename,
            "upload_timestamp": upload_timestamp
        }

        await blob_client.upload_blob(
            file_content,
            metadata=metadata,
            overwrite=False
        )

        return {
            "id": file_id,
            "filename": original_filename,
            "blob_name": blob_name,
            "uploaded_at": upload_timestamp
        }

    async def list_pdfs(self) -> List[Dict[str, str]]:
        """
        List all PDF files in the container.

        Returns:
            List of dicts with id, filename, size, and metadata
        """
        container = await self._get_container_client()
        pdfs = []

        async for blob in container.list_blobs(include=['metadata']):
            metadata = blob.metadata or {}
            pdfs.append({
                "id": metadata.get("file_id", blob.name.split("_")[0] if "_" in blob.name else blob.name),
                "filename": metadata.get("original_filename", blob.name),
                "blob_name": blob.name,
                "size_bytes": blob.size,
                "uploaded_at": metadata.get("upload_timestamp", ""),
                "content_type": blob.content_settings.content_type if blob.content_settings else "application/pdf"
            })

        return pdfs

    async def delete_pdf(self, file_id: str) -> bool:
        """
        Delete a PDF by its ID.

        Args:
            file_id: The UUID of the file to delete

        Returns:
            True if deleted, False if not found
        """
        container = await self._get_container_client()

        # Find the blob with matching file_id
        async for blob in container.list_blobs(include=['metadata']):
            metadata = blob.metadata or {}
            if metadata.get("file_id") == file_id or blob.name.startswith(f"{file_id}_"):
                blob_client = container.get_blob_client(blob.name)
                await blob_client.delete_blob()
                return True

        return False

    async def delete_all_pdfs(self) -> int:
        """
        Delete all PDF files in the container.

        Returns:
            Number of files deleted
        """
        container = await self._get_container_client()
        deleted_count = 0

        async for blob in container.list_blobs():
            blob_client = container.get_blob_client(blob.name)
            await blob_client.delete_blob()
            deleted_count += 1

        return deleted_count

    async def get_pdf(self, file_id: str) -> Optional[Dict]:
        """
        Get PDF metadata by ID.

        Args:
            file_id: The UUID of the file

        Returns:
            Dict with file info or None if not found
        """
        container = await self._get_container_client()

        async for blob in container.list_blobs(include=['metadata']):
            metadata = blob.metadata or {}
            if metadata.get("file_id") == file_id or blob.name.startswith(f"{file_id}_"):
                return {
                    "id": file_id,
                    "filename": metadata.get("original_filename", blob.name),
                    "blob_name": blob.name,
                    "size_bytes": blob.size,
                    "uploaded_at": metadata.get("upload_timestamp", "")
                }

        return None
