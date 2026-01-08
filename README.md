# Rutube Video Uploader

A Python CLI utility to upload and publish videos to Rutube (Russian video platform similar to YouTube). Uses cookie-based authentication for easy setup - no manual CSRF token extraction needed!

## Features

- ✅ Cookie-based authentication (easiest method)
- ✅ TUS resumable upload protocol
- ✅ Progress bar with upload speed
- ✅ Video metadata publishing (title, description, category)
- ✅ Privacy controls (hidden videos)
- ✅ Content moderation (adult content, comments)
- ✅ Dry-run testing mode
- ✅ Auto-detection of cookie files

## Quick Start

### 1. Install Dependencies

```bash
python3 -m pip install -r requirements.txt
```

### 2. Setup Authentication

1. Install browser extension:

   - **Chrome**: [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
   - **Firefox**: [Get cookies.txt LOCALLY](https://addons.mozilla.org/en-US/firefox/addon/get-cookies-txt-locally/)

2. Go to https://studio.rutube.ru and **login**

3. Click extension → "Get cookies.txt LOCALLY" → "Current Site"

4. Save as `cookies.txt` in the project folder

5. Done! The script will auto-detect it.

### 3. Upload Your First Video

```bash
# Using cookies (auto-detected)
python3 rutube.py video.mp4 "My Video Title"

# Or explicitly specify cookie file
python3 rutube.py video.mp4 "My Video Title" --cookies cookies.txt

# Test without uploading
python3 rutube.py video.mp4 "Test" --dry-run
```

## Usage Examples

### Basic Upload

```bash
python3 rutube.py video.mp4 "My Video Title"
```

### Upload with Description

```bash
python3 rutube.py video.mp4 "My Video Title" \
  --description "This is my video description"
```

### Upload with Custom Settings

```bash
python3 rutube.py video.mp4 "My Video Title" \
  --description "Description" \
  --category 63 \
  --hidden \
  --hide-comments
```

### All Command Options

```bash
python3 rutube.py --help
```

**Options:**

- `--description, -d`: Video description
- `--category, -c`: Category ID (default: 63)
- `--hidden`: Make video private/hidden
- `--adult`: Mark as adult content
- `--hide-comments`: Disable comments
- `--cookies`: Path to cookie file (required if not auto-detected)
- `--user-id`: User ID (optional, auto-extracted from cookies)
- `--dry-run`: Test without uploading

## Cookie File Locations

The script auto-detects cookies in this order:

1. `--cookies` argument (if provided)
2. `RUTUBE_COOKIES` environment variable
3. `cookies.txt` in project folder
4. `studio.rutube.ru_cookies.txt` in project folder
5. `artifacts/studio.rutube.ru_cookies on upload.txt`
6. `~/.rutube_cookies.txt` (home directory)

## Category IDs

Common category IDs:

- `1` - News & Politics
- `63` - Religion
- (More can be found in Rutube Studio interface)

## How It Works

The uploader implements a 4-step workflow (reverse-engineered from network requests):

1. **Create Upload Session**: POST to `/api/uploader/upload_session/`

   - Returns session ID and video ID

2. **Initialize TUS Upload**: POST to `/upload/{session_id}` with TUS headers

   - Uses TUS (Tus Resumable Upload Protocol) standard
   - Sends metadata about the upload

3. **Upload Video Data**: PATCH to `/upload/{session_id}`

   - Uploads the actual video file binary data
   - Shows progress bar with upload speed

4. **Publish Video**: PATCH to `/api/v2/video/{video_id}/`
   - Sets video metadata (title, description, category, etc.)
   - Makes the video visible on Rutube

## Troubleshooting

### "CSRF token not found in cookie file"

- Make sure you exported cookies from **studio.rutube.ru** (not just rutube.ru)
- Verify you're logged in when exporting cookies
- Check cookie file has `csrftoken` entry: `grep csrftoken cookies.txt`

### "401 Unauthorized" or "403 Forbidden"

- Your cookies have expired
- Export fresh cookies from browser

### "Cookie file not found"

- Check the file exists at the path you specified
- Verify file is readable
- Check you're in the right directory

### Upload fails or is slow

- Check your internet connection
- Verify the video file exists and is readable
- Large files take time - be patient (progress bar shows speed)
- Ensure video format is supported by Rutube

### Verify Cookie File

```bash
# Check if cookie file exists
ls -la cookies.txt

# Check if it has required cookies
grep -E "csrftoken|jwt|visitorID" cookies.txt
```

## Cookie Expiration

Cookies expire when you:

- Log out of Rutube
- Session times out
- Browser clears cookies

**Solution**: Just export fresh cookies and replace `cookies.txt`

## Security Notes

- ⚠️ **Never commit `cookies.txt` to git!** (already in `.gitignore`)
- ⚠️ Cookies contain your session tokens
- ⚠️ Anyone with your cookies can access your account
- ⚠️ Delete old cookie files when done

## Technical Details

- **Python 3.8+** required
- Uses **TUS Protocol** (Tus Resumable Upload Protocol) for reliable uploads
- Implements the same API calls as Rutube Studio web interface
- Session management via cookies
- Supports large file uploads with progress tracking

## Limitations

- Requires cookies (no official API)
- Cookies expire with browser session
- No support for resumable uploads if interrupted (yet)
- No batch upload support (yet)

## Example: Upload Test Video

```bash
# Using cookies (auto-detected)
python3 rutube.py \
  ".local/Медитация_Адвента_Неделя_2__Иисус_—_полностью_Бог_и_полностью_человек.mp4" \
  "Размышления над Адвентом. Неделя 2" \
  --description "Медитация на тему Адвента" \
  --category 63
```

## License

MIT

## Disclaimer

This tool is for educational purposes and personal use. It reverse-engineers Rutube's web interface API. Use at your own risk and in accordance with Rutube's Terms of Service.
