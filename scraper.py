import os
import re
import argparse
import asyncio
from datetime import datetime
from typing import Set, List
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from PIL import Image, ImageChops, ImageDraw

class WebsiteScreenshotter:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        parsed_url = urlparse(self.base_url)
        self.domain = parsed_url.netloc
        
        # Use domain as output root directory (removing www. if present)
        domain_name = self.domain.replace("www.", "")
        if not domain_name:
            domain_name = "website_screenshots"
            
        # Create a timestamped subdirectory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_dir = os.path.join(domain_name, timestamp)
        self.visited_urls: Set[str] = set()
        
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)
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
            try:
                await page.goto(self.base_url, wait_until="networkidle")
            except Exception as e:
                print(f"Failed to load base URL: {e}")
                await browser.close()
                return

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

def compare_folders(dir1: str, dir2: str):
    """Compare screenshots in two directories and highlight differences."""
    if not os.path.exists(dir1) or not os.path.exists(dir2):
        print(f"Error: One or both directories do not exist: {dir1}, {dir2}")
        return

    print(f"Comparing screenshots in:\n  1: {dir1}\n  2: {dir2}")
    
    files1 = {f for f in os.listdir(dir1) if f.endswith('.png')}
    files2 = {f for f in os.listdir(dir2) if f.endswith('.png')}
    
    common_files = sorted(list(files1.intersection(files2)))
    only_in_1 = sorted(list(files1 - files2))
    only_in_2 = sorted(list(files2 - files1))

    if only_in_1:
        print(f"Files only in {dir1}: {', '.join(only_in_1)}")
    if only_in_2:
        print(f"Files only in {dir2}: {', '.join(only_in_2)}")

    diff_dir = f"diff_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    differences_found = 0

    for filename in common_files:
        path1 = os.path.join(dir1, filename)
        path2 = os.path.join(dir2, filename)
        
        try:
            img1 = Image.open(path1).convert('RGB')
            img2 = Image.open(path2).convert('RGB')
            
            # Ensure images are the same size for comparison
            if img1.size != img2.size:
                # Resize smaller image to match larger one (or vice versa)
                # For simplicity, we'll just note the size difference and skip pixel-by-pixel for now
                # or we can pad them. Let's pad them to the max dimensions.
                max_w = max(img1.size[0], img2.size[0])
                max_h = max(img1.size[1], img2.size[1])
                
                new_img1 = Image.new('RGB', (max_w, max_h), (0,0,0))
                new_img2 = Image.new('RGB', (max_w, max_h), (0,0,0))
                new_img1.paste(img1, (0,0))
                new_img2.paste(img2, (0,0))
                img1, img2 = new_img1, new_img2

            diff = ImageChops.difference(img1, img2)
            
            if diff.getbbox():
                if not os.path.exists(diff_dir):
                    os.makedirs(diff_dir)
                    print(f"Differences found. Saving diff images to: {diff_dir}")
                
                differences_found += 1
                # Create a visual diff: original image with red highlights
                diff_mask = diff.convert('L').point(lambda x: 255 if x > 10 else 0)
                highlight = Image.new('RGB', img1.size, (255, 0, 0))
                img_with_diff = Image.composite(highlight, img1, diff_mask)
                
                # Combine original1, original2, and diff for easy viewing
                total_width = img1.size[0] * 3
                max_height = img1.size[1]
                combined = Image.new('RGB', (total_width, max_height))
                combined.paste(img1, (0, 0))
                combined.paste(img2, (img1.size[0], 0))
                combined.paste(img_with_diff, (img1.size[0] * 2, 0))
                
                diff_path = os.path.join(diff_dir, f"diff_{filename}")
                combined.save(diff_path)
                print(f"  Difference in {filename} -> Saved diff to {diff_path}")
            else:
                print(f"  No difference in {filename}")
                
        except Exception as e:
            print(f"  Error comparing {filename}: {e}")

    if differences_found == 0:
        print("No differences found in common screenshots.")
    else:
        print(f"Total differences found: {differences_found}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Website Screenshot Crawler and Comparer")
    parser.add_argument("--url", help="Target website URL to crawl")
    parser.add_argument("--compare", action="store_true", help="Compare two directories of screenshots")
    parser.add_argument("--dir1", help="First directory for comparison")
    parser.add_argument("--dir2", help="Second directory for comparison")
    
    args = parser.parse_args()
    
    if args.compare:
        if not args.dir1 or not args.dir2:
            print("Error: --dir1 and --dir2 are required for comparison.")
            # Try to list directories to help the user
            subdirs = [d for d in os.listdir('.') if os.path.isdir(d) and not d.startswith('.')]
            if subdirs:
                print("Available directories:")
                for d in subdirs:
                    pts = [sd for sd in os.listdir(d) if os.path.isdir(os.path.join(d, sd))]
                    for p in pts:
                        print(f"  {os.path.join(d, p)}")
        else:
            compare_folders(args.dir1, args.dir2)
    else:
        if args.url:
            target_url = args.url
        else:
            target_url = input("Enter the website URL to crawl: ")

        screenshotter = WebsiteScreenshotter(target_url)
        asyncio.run(screenshotter.crawl_and_screenshot())
