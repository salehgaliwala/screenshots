# Website Full-Page Screenshot Crawler & Comparer

A Python tool that crawls a website, takes full-page screenshots of all internal links, and compares snapshots taken at different points in time.

## Features
- Headless browsing using Playwright
- Automatic directory creation based on domain name and timestamp
- **Full-page capture**: High-resolution screenshots of any page.
- **Offline Site Generation**: Download all HTML, CSS, JS, and images to create a fully browsable offline version.
- **Recursive Crawling**: Configurable crawl depth to capture entire site sections.
- **Image Comparison**: Compare two screenshot sessions to highlight visual changes.
- **Visual Diffs**: Automatically generates diff images highlighting differences in red.

## Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/salehgaliwala/screenshots.git
   cd screenshots
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   playwright install
   ```

## Usage

### 1. Capturing Screenshots
Run the script to crawl a website and save screenshots in a timestamped folder:
```bash
python scraper.py --url https://example.com
### 2. Generating Offline Site
Run with the `--offline` flag and specify depth to download the entire site for offline use:
```bash
python scraper.py --url https://example.com --offline --depth 2
```
This will save HTML files and assets (CSS, JS, Images) in a structured format in the output directory.

### 3. Comparing Snapshots
To compare two sets of screenshots and generate visual diffs:
```bash
python scraper.py --compare --dir1 example.com/DIR_TIMESTAMP_1 --dir2 example.com/DIR_TIMESTAMP_2
```
Differences will be saved in a new directory prefixed with `diff_`.

### 3. Interactive Mode
Run without arguments to be prompted for a URL:
```bash
python scraper.py
```

## How it works
- **Crawling**: Uses **Playwright** to navigate and **BeautifulSoup** to find internal links.
  - **Comprehensive Discovery**: Searches semantic tags (`<header>`, `<footer>`, `<nav>`) and common navigation selectors (e.g., `menu`, `sidebar`, `topbar`, `navigation`) to ensure no links are missed.
  - **Smart Filtering**: Automatically excludes non-HTTP protocols (`tel:`, `mailto:`, `javascript:`) and common social media domains.
- **Versioning**: Each run creates a new timestamped folder under the domain name.
- **Comparison**: Uses **Pillow** to perform pixel-by-pixel comparison. It handles potential size differences by padding and creates a 3-pane comparison image (Original 1, Original 2, and Highlighted Diff).
