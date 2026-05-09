#!/usr/bin/env python3
"""
Rutube Video Uploader CLI
Uploads and publishes videos to Rutube using captured API endpoints.
"""

import argparse
import base64
import http.cookiejar
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

import requests
from tqdm import tqdm


def load_cookies_from_file(cookie_file: Path) -> tuple[http.cookiejar.MozillaCookieJar, dict]:
    """
    Load cookies from a Netscape/Mozilla format cookie file.

    Args:
        cookie_file: Path to the cookie file

    Returns:
        tuple: (cookie_jar, extracted_values dict with csrf_token and user_id)
    """
    cookie_jar = http.cookiejar.MozillaCookieJar(str(cookie_file))
    cookie_jar.load(ignore_discard=True, ignore_expires=True)

    extracted = {
        'csrf_token': None,
        'user_id': None,
        'jwt': None,
    }

    for cookie in cookie_jar:
        if cookie.name == 'csrftoken':
            extracted['csrf_token'] = cookie.value
        elif cookie.name == 'visitorID':
            extracted['user_id'] = cookie.value
        elif cookie.name == 'jwt':
            extracted['jwt'] = cookie.value

    return cookie_jar, extracted


class RutubeUploader:
    """Handles video upload and publishing to Rutube."""

    BASE_URL = "https://studio.rutube.ru"
    UPLOAD_URL = "https://u.rutube.ru"

    def __init__(self, user_id: str = None, dry_run: bool = False, cookie_file: Path = None):
        """
        Initialize the uploader.

        Args:
            user_id: User ID (optional, can be extracted from cookies)
            dry_run: If True, simulate upload without actually uploading
            cookie_file: Path to Netscape format cookie file (required)
        """
        if not cookie_file:
            raise ValueError("Cookie file is required. Please provide --cookies argument or place cookies.txt in project folder.")

        if not cookie_file.exists():
            raise FileNotFoundError(f"Cookie file not found: {cookie_file}")

        self.dry_run = dry_run
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            'Origin': 'https://studio.rutube.ru',
            'Referer': 'https://studio.rutube.ru/',
        })

        # Load cookies from file
        print(f"🍪 Loading cookies from: {cookie_file.name}")
        cookie_jar, extracted = load_cookies_from_file(cookie_file)
        self.session.cookies = cookie_jar

        # Extract values from cookies
        self.csrf_token = extracted['csrf_token']
        self.user_id = user_id or extracted['user_id']

        if not self.csrf_token:
            raise ValueError("CSRF token not found in cookie file. Please ensure cookies are valid and exported from studio.rutube.ru")

        print(f"✓ CSRF token: {self.csrf_token[:10]}...")
        print(f"✓ User ID: {self.user_id}")
        if extracted['jwt']:
            print(f"✓ JWT token found")
        print()

        if dry_run:
            print("🔵 DRY RUN MODE - No actual uploads will be performed\n")

    def create_upload_session(self) -> tuple[str, str]:
        """
        Create an upload session.

        Returns:
            tuple: (session_id, video_id)
        """
        print("Creating upload session...")

        if self.dry_run:
            session_id = "dry_run_" + uuid.uuid4().hex
            video_id = "dry_run_" + uuid.uuid4().hex
            print(f"✓ [DRY RUN] Session created: {session_id}")
            print(f"✓ [DRY RUN] Video ID: {video_id}")
            return session_id, video_id

        batch_id = uuid.uuid4().hex

        url = f"{self.BASE_URL}/api/uploader/upload_session/"
        params = {
            'client': 'vulp',
            'batch_id': batch_id
        }
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'X-CSRFToken': self.csrf_token,
        }
        data = json.dumps({"cancelToken": {"promise": {}}})

        try:
            response = self.session.post(url, params=params, headers=headers, data=data)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                raise Exception(
                    "Authentication failed (403 Forbidden). "
                    "Your CSRF token may be invalid or expired. "
                    "Please get a fresh token from your browser."
                ) from e
            elif e.response.status_code == 401:
                raise Exception(
                    "Unauthorized (401). Please check your CSRF token and ensure you're logged in."
                ) from e
            else:
                raise

        result = response.json()
        session_id = result['sid']
        video_id = result['video']

        print(f"✓ Session created: {session_id}")
        print(f"✓ Video ID: {video_id}")

        return session_id, video_id

    def _encode_upload_metadata(self, session_id: str, video_id: str, video_filename: str) -> str:
        """
        Encode upload metadata in base64 format for TUS protocol.

        Args:
            session_id: Upload session ID
            video_id: Video ID
            video_filename: Name of the video file

        Returns:
            str: Encoded metadata string
        """
        # Create metadata similar to captured request
        metadata = {
            'sessionId': base64.b64encode(session_id.encode()).decode(),
            'videoId': base64.b64encode(video_id.encode()).decode(),
            'userId': base64.b64encode(self.user_id.encode()).decode(),
            'uploadSessionId': base64.b64encode(
                f"{video_filename}::user-{self.user_id}::{datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]}Z".encode()
            ).decode()
        }

        # Format as comma-separated key value pairs
        return ','.join([f"{k} {v}" for k, v in metadata.items()])

    def initialize_tus_upload(self, session_id: str, video_id: str,
                            video_path: Path, video_size: int) -> None:
        """
        Initialize TUS upload.

        Args:
            session_id: Upload session ID
            video_id: Video ID
            video_path: Path to video file
            video_size: Size of video file in bytes
        """
        print("Initializing TUS upload...")

        if self.dry_run:
            print("✓ [DRY RUN] TUS upload initialized")
            return

        url = f"{self.UPLOAD_URL}/upload/{session_id}"
        metadata = self._encode_upload_metadata(session_id, video_id, video_path.name)

        headers = {
            'Accept': '*/*',
            'Content-Type': 'application/offset+octet-stream',
            'Tus-Resumable': '1.0.0',
            'Upload-Length': str(video_size),
            'Upload-Metadata': metadata,
        }

        response = self.session.post(url, headers=headers)
        response.raise_for_status()

        print("✓ TUS upload initialized")

    def upload_video_data(self, session_id: str, video_path: Path) -> None:
        """
        Upload the actual video data using TUS protocol.

        Args:
            session_id: Upload session ID
            video_path: Path to video file
        """
        print(f"Uploading video: {video_path.name}")

        video_size = video_path.stat().st_size

        if self.dry_run:
            # Simulate upload progress
            import time
            with tqdm(total=video_size, unit='B', unit_scale=True, desc="[DRY RUN] Uploading") as pbar:
                chunk_size = video_size // 10
                for _ in range(10):
                    time.sleep(0.1)
                    pbar.update(chunk_size)
            print(f"✓ [DRY RUN] Video uploaded successfully ({video_size} bytes)")
            return

        url = f"{self.UPLOAD_URL}/upload/{session_id}"

        headers = {
            'Accept': '*/*',
            'Content-Type': 'application/offset+octet-stream',
            'Tus-Resumable': '1.0.0',
            'Upload-Offset': '0',
        }

        # Upload with progress bar
        with open(video_path, 'rb') as f:
            with tqdm(total=video_size, unit='B', unit_scale=True, desc="Uploading") as pbar:
                # For large files, you might want to implement chunked upload
                # For now, we'll upload the entire file at once
                data = f.read()

                response = self.session.patch(url, headers=headers, data=data)
                response.raise_for_status()
                pbar.update(video_size)

        # Verify upload offset
        upload_offset = response.headers.get('Upload-Offset')
        if upload_offset and int(upload_offset) == video_size:
            print(f"✓ Video uploaded successfully ({video_size} bytes)")
        else:
            print(f"⚠ Warning: Upload offset mismatch. Expected {video_size}, got {upload_offset}")

    def publish_video(self, video_id: str, title: str, description: str = "",
                     category: str = "63", is_hidden: bool = False,
                     is_adult: bool = False, hide_comments: bool = False) -> dict:
        """
        Publish the video with metadata.

        Args:
            video_id: Video ID
            title: Video title
            description: Video description
            category: Category ID (default: "63" for Religion)
            is_hidden: Whether video is hidden
            is_adult: Whether video has adult content
            hide_comments: Whether to hide comments

        Returns:
            dict: Response data from API
        """
        print("Publishing video...")

        if self.dry_run:
            video_url = f"https://rutube.ru/video/{video_id}/"
            print(f"✓ [DRY RUN] Video published successfully!")
            print(f"✓ [DRY RUN] Video URL: {video_url}")
            return {
                'id': video_id,
                'title': title,
                'video_url': video_url,
                'is_hidden': is_hidden
            }

        url = f"{self.BASE_URL}/api/v2/video/{video_id}/"
        params = {
            'client': 'vulp'
        }
        headers = {
            'Accept': '*/*',
            'Content-Type': 'application/json',
            'X-CSRFToken': self.csrf_token,
        }
        data = {
            'title': title,
            'description': description,
            'is_hidden': is_hidden,
            'is_adult': is_adult,
            'category': category,
            'properties': {
                'hide_comments': hide_comments
            }
        }

        response = self.session.patch(url, params=params, headers=headers,
                                     data=json.dumps(data))
        response.raise_for_status()

        result = response.json()
        video_url = result.get('video_url', '')

        print(f"✓ Video published successfully!")
        print(f"✓ Video URL: {video_url}")

        return result

    def upload_and_publish(self, video_path: Path, title: str,
                          description: str = "", **kwargs) -> dict:
        """
        Complete upload and publish workflow.

        Args:
            video_path: Path to video file
            title: Video title
            description: Video description
            **kwargs: Additional parameters for publish_video

        Returns:
            dict: Video metadata from API
        """
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        video_size = video_path.stat().st_size
        print(f"\n{'='*60}")
        print(f"Video: {video_path.name}")
        print(f"Size: {video_size:,} bytes ({video_size / 1024 / 1024:.2f} MB)")
        print(f"Title: {title}")
        print(f"{'='*60}\n")

        # Step 1: Create upload session
        session_id, video_id = self.create_upload_session()

        # Step 2: Initialize TUS upload
        self.initialize_tus_upload(session_id, video_id, video_path, video_size)

        # Step 3: Upload video data
        self.upload_video_data(session_id, video_path)

        # Step 4: Publish video
        result = self.publish_video(video_id, title, description, **kwargs)

        print(f"\n{'='*60}")
        print("Upload complete!")
        print(f"{'='*60}\n")

        return result


def find_cookie_file():
    """Find cookie file in common locations."""
    # Check common locations relative to script
    script_dir = Path(__file__).parent

    locations = [
        script_dir / "cookies.txt",
        script_dir / "studio.rutube.ru_cookies.txt",
        script_dir / "artifacts" / "studio.rutube.ru_cookies on upload.txt",
        Path.home() / ".rutube_cookies.txt",
    ]

    for path in locations:
        if path.exists():
            return path

    # Check environment variable
    env_path = os.getenv('RUTUBE_COOKIES')
    if env_path:
        path = Path(env_path)
        if path.exists():
            return path

    return None


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Upload and publish videos to Rutube",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using cookie file (auto-detected if cookies.txt exists)
  python rutube.py video.mp4 "My Video Title"

  # Explicitly specify cookie file
  python rutube.py video.mp4 "My Video Title" --cookies cookies.txt

  # Or set cookie file path in environment
  export RUTUBE_COOKIES=~/.rutube_cookies.txt
  python rutube.py video.mp4 "My Video Title"

  # Upload with options
  python rutube.py video.mp4 "Title" --cookies cookies.txt -d "Description" --category 63

Categories:
  63 - Religion
  1  - News & Politics
  (Add more categories as needed)
        """
    )

    parser.add_argument('video', type=Path, help='Path to video file')
    parser.add_argument('title', help='Video title')
    parser.add_argument('--description', '-d', default='', help='Video description')
    parser.add_argument('--category', '-c', default='63', help='Category ID (default: 63)')
    parser.add_argument('--hidden', action='store_true', help='Make video hidden')
    parser.add_argument('--adult', action='store_true', help='Mark as adult content')
    parser.add_argument('--hide-comments', action='store_true', help='Hide comments')
    parser.add_argument('--cookies', type=Path,
                       help='Path to Netscape format cookie file (required if not auto-detected)')
    parser.add_argument('--user-id', help='User ID (optional, extracted from cookies)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Simulate upload without actually uploading')

    args = parser.parse_args()

    try:
        # Find cookie file
        cookie_file = args.cookies

        # Try to find cookie file automatically if not provided
        if not cookie_file:
            cookie_file = find_cookie_file()
            if cookie_file:
                print(f"📁 Auto-detected cookie file: {cookie_file}")

        # Dry run mode - use dummy cookie file
        if args.dry_run and not cookie_file:
            # Create a temporary dummy cookie file for dry run
            import tempfile
            dummy_cookie = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
            dummy_cookie.write("# Netscape HTTP Cookie File\n")
            dummy_cookie.write(".rutube.ru\tTRUE\t/\tFALSE\t0\tcsrftoken\tdry_run_token\n")
            dummy_cookie.write(".rutube.ru\tTRUE\t/\tFALSE\t0\tvisitorID\t72297043\n")
            dummy_cookie.close()
            cookie_file = Path(dummy_cookie.name)

        # Create uploader
        uploader = RutubeUploader(
            user_id=args.user_id,
            dry_run=args.dry_run,
            cookie_file=cookie_file
        )

        # Upload and publish
        uploader.upload_and_publish(
            video_path=args.video,
            title=args.title,
            description=args.description,
            category=args.category,
            is_hidden=args.hidden,
            is_adult=args.adult,
            hide_comments=args.hide_comments
        )

    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
