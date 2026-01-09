"""Controller for managing local media files (music and video)."""

from __future__ import annotations

import asyncio
import base64
import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import aiofiles
import shortuuid
from aiohttp import web
from music_assistant_models.enums import MediaType

from music_assistant.helpers.api import api_command
from music_assistant.models.core_controller import CoreController

if TYPE_CHECKING:
    from music_assistant.mass import MusicAssistant

# Directory names
MUSIC_DIR = "music"
VIDEO_DIR = "video"
THUMBNAILS_DIR = "video_thumbnails"

# Thumbnail settings
THUMBNAIL_TIME = 5  # Extract frame at 5 seconds
THUMBNAIL_WIDTH = 320  # Thumbnail width in pixels

# Supported extensions
AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a", ".wma", ".opus"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv"}


@dataclass
class MediaFileInfo:
    """Information about a media file."""

    id: str
    name: str
    path: str
    size: int
    media_type: str  # "audio" or "video"
    created_at: int
    is_folder: bool = False
    children_count: int = 0


@dataclass
class BrowseItem:
    """Browse item for local media."""

    item_id: str
    name: str
    path: str
    is_folder: bool
    media_type: str = ""
    size: int = 0
    uri: str = ""


class MediaFilesController(CoreController):
    """Controller for managing local media files."""

    domain: str = "media_files"
    _music_path: str = ""
    _video_path: str = ""
    _thumbnails_path: str = ""

    def __init__(self, mass: MusicAssistant) -> None:
        """Initialize the controller."""
        super().__init__(mass)
        self._music_path = ""
        self._video_path = ""
        self._thumbnails_path = ""

    async def setup(self, config: dict[str, Any] | None = None) -> None:
        """Set up the controller."""
        # Create directories for media storage
        self._music_path = os.path.join(self.mass.storage_path, MUSIC_DIR)
        self._video_path = os.path.join(self.mass.storage_path, VIDEO_DIR)
        self._thumbnails_path = os.path.join(self.mass.storage_path, THUMBNAILS_DIR)

        for path in (self._music_path, self._video_path, self._thumbnails_path):
            if not await asyncio.to_thread(os.path.exists, path):
                await asyncio.to_thread(os.makedirs, path)
                self.logger.info("Created media directory: %s", path)

        self.logger.info("MediaFilesController initialized")

    async def close(self) -> None:
        """Close the controller."""
        pass

    async def _generate_thumbnail(self, video_path: str, relative_path: str) -> str | None:
        """Generate a thumbnail for a video file using ffmpeg.

        :param video_path: Full path to the video file.
        :param relative_path: Relative path used for thumbnail naming.
        :return: Relative path to the thumbnail or None if failed.
        """
        try:
            # Create thumbnail filename based on video relative path
            thumb_name = relative_path.replace("/", "_").replace("\\", "_") + ".jpg"
            thumb_path = os.path.join(self._thumbnails_path, thumb_name)

            # Use ffmpeg to extract a frame at THUMBNAIL_TIME seconds
            cmd = [
                "ffmpeg",
                "-y",  # Overwrite output
                "-ss", str(THUMBNAIL_TIME),  # Seek to time
                "-i", video_path,  # Input file
                "-vframes", "1",  # Extract 1 frame
                "-vf", f"scale={THUMBNAIL_WIDTH}:-1",  # Scale to width, auto height
                "-q:v", "3",  # Quality (2-5 is good, lower is better)
                thumb_path,
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()

            if process.returncode != 0:
                # If seeking to 5s fails (video too short), try 1 second
                cmd[3] = "1"
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await process.communicate()

            if process.returncode == 0 and await asyncio.to_thread(os.path.exists, thumb_path):
                self.logger.info("Generated thumbnail: %s", thumb_path)
                return thumb_name
            else:
                self.logger.warning("Failed to generate thumbnail for %s: %s", video_path, stderr.decode())
                return None

        except Exception as e:
            self.logger.exception("Error generating thumbnail: %s", e)
            return None

    def _get_thumbnail_path(self, relative_path: str) -> str | None:
        """Get thumbnail path for a video file if it exists.

        :param relative_path: Relative path to the video file.
        :return: Thumbnail filename or None.
        """
        thumb_name = relative_path.replace("/", "_").replace("\\", "_") + ".jpg"
        thumb_path = os.path.join(self._thumbnails_path, thumb_name)
        if os.path.exists(thumb_path):
            return thumb_name
        return None

    @api_command("media_files/upload")
    async def upload_file(
        self,
        file_data: str,
        file_name: str,
        media_type: str,
        folder_path: str = "",
    ) -> dict[str, Any]:
        """Upload a media file.

        :param file_data: Base64 encoded file data.
        :param file_name: Original file name.
        :param media_type: Type of media ("music" or "video").
        :param folder_path: Relative folder path (optional).
        """
        # Determine base path
        if media_type == "video":
            base_path = self._video_path
        else:
            base_path = self._music_path

        # Build target directory
        if folder_path:
            # Security: prevent path traversal
            safe_folder = os.path.normpath(folder_path).lstrip(os.sep)
            if ".." in safe_folder:
                raise ValueError("Invalid folder path")
            target_dir = os.path.join(base_path, safe_folder)
        else:
            target_dir = base_path

        # Ensure directory exists
        if not await asyncio.to_thread(os.path.exists, target_dir):
            await asyncio.to_thread(os.makedirs, target_dir)

        # Generate unique filename
        file_id = shortuuid.random(8)
        name, ext = os.path.splitext(file_name)
        safe_filename = f"{name}_{file_id}{ext}"
        file_path = os.path.join(target_dir, safe_filename)

        # Decode and save file
        file_bytes = base64.b64decode(file_data)
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_bytes)

        self.logger.info("Uploaded media file: %s", file_path)

        return {
            "id": file_id,
            "name": file_name,
            "path": file_path,
            "size": len(file_bytes),
            "media_type": media_type,
        }

    @api_command("media_files/create_folder")
    async def create_folder(
        self,
        folder_name: str,
        media_type: str,
        parent_path: str = "",
    ) -> dict[str, Any]:
        """Create a new folder.

        :param folder_name: Name of the new folder.
        :param media_type: Type of media ("music" or "video").
        :param parent_path: Relative parent folder path (optional).
        """
        # Determine base path
        if media_type == "video":
            base_path = self._video_path
        else:
            base_path = self._music_path

        # Build target directory
        if parent_path:
            safe_parent = os.path.normpath(parent_path).lstrip(os.sep)
            if ".." in safe_parent:
                raise ValueError("Invalid parent path")
            target_dir = os.path.join(base_path, safe_parent, folder_name)
        else:
            target_dir = os.path.join(base_path, folder_name)

        # Security check
        if not target_dir.startswith(base_path):
            raise ValueError("Invalid folder path")

        # Create folder
        if await asyncio.to_thread(os.path.exists, target_dir):
            raise ValueError("Folder already exists")

        await asyncio.to_thread(os.makedirs, target_dir)
        self.logger.info("Created folder: %s", target_dir)

        return {
            "name": folder_name,
            "path": target_dir,
            "media_type": media_type,
        }

    @api_command("media_files/delete")
    async def delete_item(
        self,
        path: str,
        media_type: str,
    ) -> bool:
        """Delete a file or folder.

        :param path: Relative path to the item.
        :param media_type: Type of media ("music" or "video").
        """
        # Determine base path
        if media_type == "video":
            base_path = self._video_path
        else:
            base_path = self._music_path

        # Build full path
        safe_path = os.path.normpath(path).lstrip(os.sep)
        if ".." in safe_path:
            raise ValueError("Invalid path")
        full_path = os.path.join(base_path, safe_path)

        # Security check
        if not full_path.startswith(base_path):
            raise ValueError("Invalid path")

        if not await asyncio.to_thread(os.path.exists, full_path):
            raise ValueError("Item not found")

        # Delete
        if await asyncio.to_thread(os.path.isdir, full_path):
            import shutil
            await asyncio.to_thread(shutil.rmtree, full_path)
            self.logger.info("Deleted folder: %s", full_path)
        else:
            await asyncio.to_thread(os.remove, full_path)
            self.logger.info("Deleted file: %s", full_path)

        return True

    @api_command("media_files/move")
    async def move_item(
        self,
        source_path: str,
        dest_folder: str,
        media_type: str,
    ) -> dict[str, Any]:
        """Move a file or folder to another location.

        :param source_path: Relative path to the source item.
        :param dest_folder: Relative path to destination folder (empty for root).
        :param media_type: Type of media ("music" or "video").
        """
        import shutil

        # Determine base path
        if media_type == "video":
            base_path = self._video_path
        else:
            base_path = self._music_path

        # Build source path
        safe_source = os.path.normpath(source_path).lstrip(os.sep)
        if ".." in safe_source:
            raise ValueError("Invalid source path")
        full_source = os.path.join(base_path, safe_source)

        # Security check for source
        if not full_source.startswith(base_path):
            raise ValueError("Invalid source path")

        if not await asyncio.to_thread(os.path.exists, full_source):
            raise ValueError("Source item not found")

        # Build destination path
        if dest_folder:
            safe_dest = os.path.normpath(dest_folder).lstrip(os.sep)
            if ".." in safe_dest:
                raise ValueError("Invalid destination path")
            dest_dir = os.path.join(base_path, safe_dest)
        else:
            dest_dir = base_path

        # Security check for destination
        if not dest_dir.startswith(base_path):
            raise ValueError("Invalid destination path")

        # Ensure destination exists
        if not await asyncio.to_thread(os.path.exists, dest_dir):
            raise ValueError("Destination folder not found")

        # Get filename and build new path
        filename = os.path.basename(full_source)
        new_path = os.path.join(dest_dir, filename)

        # Check if destination already exists
        if await asyncio.to_thread(os.path.exists, new_path):
            raise ValueError("Item with same name already exists in destination")

        # Move the item
        await asyncio.to_thread(shutil.move, full_source, new_path)
        self.logger.info("Moved %s to %s", full_source, new_path)

        return {
            "name": filename,
            "old_path": source_path,
            "new_path": os.path.relpath(new_path, base_path),
            "media_type": media_type,
        }

    @api_command("media_files/list_folders")
    async def list_folders(
        self,
        media_type: str,
    ) -> list[dict[str, Any]]:
        """List all folders for move destination selection.

        :param media_type: Type of media ("music" or "video").
        """
        # Determine base path
        if media_type == "video":
            base_path = self._video_path
        else:
            base_path = self._music_path

        folders: list[dict[str, Any]] = []
        # Add root folder
        folders.append({"name": "/", "path": ""})

        # Walk through all directories
        for root, dirs, _ in os.walk(base_path):
            for d in sorted(dirs):
                full_path = os.path.join(root, d)
                rel_path = os.path.relpath(full_path, base_path)
                folders.append({
                    "name": rel_path,
                    "path": rel_path,
                })

        return folders

    @api_command("media_files/browse")
    async def browse(
        self,
        media_type: str,
        folder_path: str = "",
    ) -> list[dict[str, Any]]:
        """Browse media files and folders.

        :param media_type: Type of media ("music" or "video").
        :param folder_path: Relative folder path (optional).
        """
        # Determine base path
        if media_type == "video":
            base_path = self._video_path
            allowed_extensions = VIDEO_EXTENSIONS
        else:
            base_path = self._music_path
            allowed_extensions = AUDIO_EXTENSIONS

        # Build target directory
        if folder_path:
            safe_folder = os.path.normpath(folder_path).lstrip(os.sep)
            if ".." in safe_folder:
                raise ValueError("Invalid folder path")
            target_dir = os.path.join(base_path, safe_folder)
        else:
            target_dir = base_path

        # Security check
        if not target_dir.startswith(base_path):
            raise ValueError("Invalid folder path")

        if not await asyncio.to_thread(os.path.exists, target_dir):
            return []

        result: list[dict[str, Any]] = []
        entries = await asyncio.to_thread(os.listdir, target_dir)

        for entry in sorted(entries):
            entry_path = os.path.join(target_dir, entry)
            relative_path = os.path.relpath(entry_path, base_path)

            if await asyncio.to_thread(os.path.isdir, entry_path):
                # Count children
                children = await asyncio.to_thread(os.listdir, entry_path)
                result.append({
                    "id": relative_path,
                    "name": entry,
                    "path": relative_path,
                    "is_folder": True,
                    "media_type": media_type,
                    "size": 0,
                    "children_count": len(children),
                    "uri": f"file://{entry_path}",
                })
            else:
                # Check if it's a supported media file
                _, ext = os.path.splitext(entry.lower())
                if ext in allowed_extensions:
                    stat = await asyncio.to_thread(os.stat, entry_path)
                    item = {
                        "id": relative_path,
                        "name": entry,
                        "path": relative_path,
                        "is_folder": False,
                        "media_type": media_type,
                        "size": stat.st_size,
                        "uri": f"file://{entry_path}",
                    }
                    # Add thumbnail for video files
                    if media_type == "video":
                        thumb = self._get_thumbnail_path(relative_path)
                        self.logger.debug("Thumbnail check for %s: %s", relative_path, thumb)
                        if thumb:
                            item["thumbnail"] = thumb
                    result.append(item)

        # Sort: folders first, then files
        result.sort(key=lambda x: (not x["is_folder"], x["name"].lower()))
        return result

    @api_command("media_files/info")
    async def get_info(self) -> dict[str, Any]:
        """Get information about media storage."""
        music_count = 0
        video_count = 0
        music_size = 0
        video_size = 0

        # Count music files
        for root, _, files in os.walk(self._music_path):
            for f in files:
                _, ext = os.path.splitext(f.lower())
                if ext in AUDIO_EXTENSIONS:
                    music_count += 1
                    music_size += os.path.getsize(os.path.join(root, f))

        # Count video files
        for root, _, files in os.walk(self._video_path):
            for f in files:
                _, ext = os.path.splitext(f.lower())
                if ext in VIDEO_EXTENSIONS:
                    video_count += 1
                    video_size += os.path.getsize(os.path.join(root, f))

        return {
            "music_path": self._music_path,
            "video_path": self._video_path,
            "music_count": music_count,
            "video_count": video_count,
            "music_size": music_size,
            "video_size": video_size,
        }

    async def handle_http_upload(self, request: web.Request) -> web.Response:
        """Handle HTTP multipart file upload for large files.

        :param request: aiohttp request with multipart data.
        """
        try:
            reader = await request.multipart()

            media_type = request.query.get("media_type", "video")
            folder_path = request.query.get("folder_path", "")

            # Determine base path
            if media_type == "video":
                base_path = self._video_path
            else:
                base_path = self._music_path

            # Build target directory
            if folder_path:
                safe_folder = os.path.normpath(folder_path).lstrip(os.sep)
                if ".." in safe_folder:
                    return web.json_response({"error": "Invalid folder path"}, status=400)
                target_dir = os.path.join(base_path, safe_folder)
            else:
                target_dir = base_path

            # Ensure directory exists
            if not await asyncio.to_thread(os.path.exists, target_dir):
                await asyncio.to_thread(os.makedirs, target_dir)

            uploaded_files = []

            # Process each file in the multipart request
            while True:
                part = await reader.next()
                if part is None:
                    break

                if part.name == "file":
                    original_filename = part.filename or "unknown"
                    file_id = shortuuid.random(8)
                    name, ext = os.path.splitext(original_filename)
                    safe_filename = f"{name}_{file_id}{ext}"
                    file_path = os.path.join(target_dir, safe_filename)

                    # Stream file to disk
                    size = 0
                    async with aiofiles.open(file_path, "wb") as f:
                        while True:
                            chunk = await part.read_chunk()
                            if not chunk:
                                break
                            await f.write(chunk)
                            size += len(chunk)

                    self.logger.info("Uploaded file via HTTP: %s (%d bytes)", file_path, size)
                    rel_path = os.path.relpath(file_path, base_path)
                    uploaded_files.append({
                        "id": file_id,
                        "name": original_filename,
                        "path": rel_path,
                        "size": size,
                        "media_type": media_type,
                    })

                    # Generate thumbnail for video files in background
                    if media_type == "video":
                        asyncio.create_task(self._generate_thumbnail(file_path, rel_path))

            return web.json_response({"success": True, "files": uploaded_files})

        except Exception as e:
            self.logger.exception("HTTP upload failed: %s", e)
            return web.json_response({"error": str(e)}, status=500)

    async def handle_video_stream(self, request: web.Request) -> web.StreamResponse:
        """Handle HTTP video streaming with range support.

        :param request: aiohttp request.
        """
        try:
            path = request.query.get("path", "")
            if not path:
                return web.json_response({"error": "Path required"}, status=400)

            # Security: prevent path traversal
            safe_path = os.path.normpath(path).lstrip(os.sep)
            if ".." in safe_path:
                return web.json_response({"error": "Invalid path"}, status=400)

            full_path = os.path.join(self._video_path, safe_path)

            # Security check
            if not full_path.startswith(self._video_path):
                return web.json_response({"error": "Invalid path"}, status=400)

            if not await asyncio.to_thread(os.path.exists, full_path):
                return web.json_response({"error": "File not found"}, status=404)

            if await asyncio.to_thread(os.path.isdir, full_path):
                return web.json_response({"error": "Cannot stream directory"}, status=400)

            # Get file info
            stat = await asyncio.to_thread(os.stat, full_path)
            file_size = stat.st_size

            # Determine content type
            ext = os.path.splitext(full_path)[1].lower()
            content_types = {
                ".mp4": "video/mp4",
                ".mkv": "video/x-matroska",
                ".avi": "video/x-msvideo",
                ".mov": "video/quicktime",
                ".webm": "video/webm",
                ".wmv": "video/x-ms-wmv",
                ".flv": "video/x-flv",
            }
            content_type = content_types.get(ext, "video/mp4")

            # Handle range requests for seeking support
            range_header = request.headers.get("Range")
            start = 0
            end = file_size - 1

            if range_header:
                # Parse range header (e.g., "bytes=0-1023")
                range_match = range_header.replace("bytes=", "").split("-")
                start = int(range_match[0]) if range_match[0] else 0
                end = int(range_match[1]) if range_match[1] else file_size - 1

                # Validate range
                if start >= file_size or end >= file_size or start > end:
                    return web.Response(status=416)  # Range Not Satisfiable

            content_length = end - start + 1

            # Create response
            if range_header:
                response = web.StreamResponse(
                    status=206,
                    headers={
                        "Content-Type": content_type,
                        "Content-Length": str(content_length),
                        "Content-Range": f"bytes {start}-{end}/{file_size}",
                        "Accept-Ranges": "bytes",
                    },
                )
            else:
                response = web.StreamResponse(
                    status=200,
                    headers={
                        "Content-Type": content_type,
                        "Content-Length": str(file_size),
                        "Accept-Ranges": "bytes",
                    },
                )

            await response.prepare(request)

            # Stream file content
            chunk_size = 1024 * 1024  # 1MB chunks for faster buffering
            async with aiofiles.open(full_path, "rb") as f:
                await f.seek(start)
                remaining = content_length
                while remaining > 0:
                    read_size = min(chunk_size, remaining)
                    chunk = await f.read(read_size)
                    if not chunk:
                        break
                    await response.write(chunk)
                    remaining -= len(chunk)

            await response.write_eof()
            return response

        except Exception as e:
            self.logger.exception("Video streaming failed: %s", e)
            return web.json_response({"error": str(e)}, status=500)

    async def handle_thumbnail(self, request: web.Request) -> web.Response:
        """Serve video thumbnail image.

        :param request: aiohttp request.
        """
        try:
            name = request.query.get("name", "")
            if not name:
                return web.json_response({"error": "Name required"}, status=400)

            # Security: only allow jpg files, no path traversal
            if ".." in name or "/" in name or "\\" in name:
                return web.json_response({"error": "Invalid name"}, status=400)

            if not name.endswith(".jpg"):
                return web.json_response({"error": "Invalid file type"}, status=400)

            thumb_path = os.path.join(self._thumbnails_path, name)

            if not await asyncio.to_thread(os.path.exists, thumb_path):
                return web.json_response({"error": "Thumbnail not found"}, status=404)

            # Read and return the thumbnail
            async with aiofiles.open(thumb_path, "rb") as f:
                data = await f.read()

            return web.Response(
                body=data,
                content_type="image/jpeg",
                headers={
                    "Cache-Control": "public, max-age=86400",  # Cache for 1 day
                },
            )

        except Exception as e:
            self.logger.exception("Thumbnail serving failed: %s", e)
            return web.json_response({"error": str(e)}, status=500)
