import os
import re
import argparse
import asyncio
from typing import Set
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

class WebsiteScreenshotter:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        parsed_url = urlparse(self.base_url)
        self.domain = parsed_url.netloc
        
        # Use domain as output directory (removing www. if present)
        folder_name = self.domain.replace("www.", "")
        if not folder_name:
            folder_name = "website_screenshots"
            
        self.output_dir = folder_name
        self.visited_urls: Set[str] = set()
        
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            print(f"Created directory: {self.output_dir}")

    def is_internal_link(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.netloc == "" or parsed.netloc == self.domain

    def clean_filename(self, url: str) -> str:
        path = urlparse(url).path
        if not path or path == "/":
            return "index"
        # Remove leading/trailing slashes and replace others with underscores
        name = path.strip("/").replace("/", "_")
        # Remove any non-alphanumeric characters except underscores and dots
        name = re.sub(r'[^\w\-_.]', '', name)
        return name if name else "page"

    async def crawl_and_screenshot(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
            page = await context.new_page()

            print(f"Opening base URL: {self.base_url}")
            await page.goto(self.base_url, wait_until="networkidle")

            # Extract links from header and footer
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            links_to_visit = set()
            links_to_visit.add(self.base_url)

            # Look for header and footer tags
            for container_tag in ['header', 'footer']:
                containers = soup.find_all(container_tag)
                for container in containers:
                    for a in container.find_all('a', href=True):
                        full_url = urljoin(self.base_url, a['href']).split('#')[0].rstrip("/")
                        if self.is_internal_link(full_url):
                            links_to_visit.add(full_url)

            # Manual fallback for common header/footer classes/IDs if no tags found
            if len(links_to_visit) <= 1:
                classes_ids = ['header', 'footer', 'nav', 'menu', 'topbar', 'bottombar']
                for selector in classes_ids:
                    containers = soup.find_all(attrs={"id": re.compile(selector, re.I)}) + \
                                soup.find_all(attrs={"class": re.compile(selector, re.I)})
                    for container in containers:
                        for a in container.find_all('a', href=True):
                            full_url = urljoin(self.base_url, a['href']).split('#')[0].rstrip("/")
                            if self.is_internal_link(full_url):
                                links_to_visit.add(full_url)

            print(f"Found {len(links_to_visit)} internal links in header/footer.")

            for i, url in enumerate(sorted(links_to_visit)):
                if url in self.visited_urls:
                    continue
                
                print(f"[{i+1}/{len(links_to_visit)}] Taking screenshot of: {url}")
                try:
                    await page.goto(url, wait_until="networkidle", timeout=60000)
                    # Add a small delay for any animations/lazy loading
                    await asyncio.sleep(2)
                    
                    filename = f"{self.clean_filename(url)}.png"
                    filepath = os.path.join(self.output_dir, filename)
                    
                    # Take full page screenshot
                    await page.screenshot(path=filepath, full_page=True)
                    print(f"  Saved to: {filepath}")
                    self.visited_urls.add(url)
                except Exception as e:
                    print(f"  Failed to capture {url}: {e}")

            await browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Website Full-Page Screenshot Crawler")
    parser.add_argument("--url", help="Target website URL")
    args = parser.parse_args()
    
    if args.url:
        target_url = args.url
    else:
        target_url = input("Enter the website URL to crawl: ")

    screenshotter = WebsiteScreenshotter(target_url)
    asyncio.run(screenshotter.crawl_and_screenshot())
