# Website Full-Page Screenshot Crawler

A Python tool that crawls a website and takes full-page screenshots of all internal links found in the header and footer.

## Features
- Headless browsing using Playwright
- Concurrent crawling
- Automatic directory creation based on domain name
- Full-page capture

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

### 1. Interactive Mode
Run the script without arguments to be prompted for a URL:
```bash
python scraper.py
```

### 2. Argument Mode
Pass the target URL directly as a command-line argument:
```bash
python scraper.py --url https://example.com
```

### How it works
- The script uses **Playwright** to navigate to the base URL in a headless browser.
- It identifies internal links located in the **header** and **footer** of the page.
- For each unique link found, it captures a **full-page screenshot**.
- Screenshots are automatically saved to a directory named after the website's domain (e.g., `example.com/`).
- Filenames are generated based on the URL path (e.g., `contact-us.png`).
