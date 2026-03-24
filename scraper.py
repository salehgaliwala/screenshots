import os
import re
import argparse
import asyncio
from datetime import datetime
from typing import Set, List, Dict
from urllib.parse import urljoin, urlparse, unquote
from playwright.async_api import async_playwright, Page, APIRequestContext
from bs4 import BeautifulSoup
from PIL import Image, ImageChops, ImageDraw

class WebsiteCloner:
    def __init__(self, base_url: str, output_dir: str = None, offline: bool = False):
        self.base_url = base_url.rstrip("/")
        parsed_url = urlparse(self.base_url)
        self.domain = parsed_url.netloc
        
        # Use domain as output root directory (removing www. if present)
        domain_name = self.domain.replace("www.", "")
        if not domain_name:
            domain_name = "website_out"
            
        # Create a timestamped subdirectory if output_dir is not provided
        if not output_dir:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.output_dir = os.path.join(domain_name, timestamp)
        else:
            self.output_dir = output_dir

        self.offline = offline
        self.visited_urls: Set[str] = set()
        self.assets_dir = os.path.join(self.output_dir, "assets")
        self.downloaded_assets: Dict[str, str] = {} # remote_url -> local_path
        
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)
            print(f"Created directory: {self.output_dir}")
        
        if self.offline and not os.path.exists(self.assets_dir):
            os.makedirs(self.assets_dir, exist_ok=True)

    def is_internal_link(self, url: str) -> bool:
        if not url:
            return False
            
        parsed = urlparse(url)
        # Only consider http/https or empty scheme (relative)
        if parsed.scheme and parsed.scheme not in ['http', 'https']:
            return False
            
        # Check if it's a social media or other known external service
        external_domains = ['facebook.com', 'instagram.com', 'linkedin.com', 'twitter.com', 'youtube.com']
        if any(domain in parsed.netloc.lower() for domain in external_domains):
            return False
            
        return parsed.netloc == "" or parsed.netloc == self.domain or \
               parsed.netloc == self.domain.replace("www.", "") or \
               f"www.{parsed.netloc}" == self.domain

    def clean_filename(self, url: str, is_page: bool = False) -> str:
        parsed = urlparse(url)
        path = parsed.path
        if not path or path == "/":
            return "index.html" if is_page else "index"
        
        # Remove leading/trailing slashes and replace others with underscores
        name = path.strip("/").replace("/", "_")
        # Remove any non-alphanumeric characters except underscores and dots
        name = re.sub(r'[^\w\-_.]', '', name)
        
        if is_page and not name.endswith(".html"):
            name += ".html"
            
        return name if name else ("index.html" if is_page else "page")

    def get_local_asset_path(self, url: str) -> str:
        """Determines the local path for a given asset URL."""
        if url in self.downloaded_assets:
            return self.downloaded_assets[url]
            
        parsed = urlparse(url)
        # Extract filename from path
        filename = os.path.basename(parsed.path)
        if not filename:
            filename = f"asset_{hash(url) % 10000}"
            
        # Determine subdirectory based on extension
        ext = os.path.splitext(filename)[1].lower()
        if ext in ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp']:
            subdir = "images"
        elif ext in ['.css']:
            subdir = "css"
        elif ext in ['.js']:
            subdir = "js"
        elif ext in ['.woff', '.woff2', '.ttf', '.otf', '.eot']:
            subdir = "fonts"
        else:
            subdir = "misc"
            
        target_dir = os.path.join(self.assets_dir, subdir)
        os.makedirs(target_dir, exist_ok=True)
        
        # Ensure unique filename
        local_filename = filename
        counter = 1
        while os.path.exists(os.path.join(target_dir, local_filename)):
            name, ext = os.path.splitext(filename)
            local_filename = f"{name}_{counter}{ext}"
            counter += 1
            
        rel_path = os.path.join("assets", subdir, local_filename).replace("\\", "/")
        return rel_path

    async def download_asset(self, url: str, request_context: APIRequestContext) -> str:
        """Downloads an asset and returns its relative local path."""
        if url in self.downloaded_assets:
            return self.downloaded_assets[url]
            
        # Skip data URLs
        if url.startswith('data:'):
            return url
            
        try:
            rel_path = self.get_local_asset_path(url)
            abs_path = os.path.join(self.output_dir, rel_path)
            
            response = await request_context.get(url)
            if response.status == 200:
                with open(abs_path, "wb") as f:
                    f.write(await response.body())
                self.downloaded_assets[url] = rel_path
                return rel_path
            else:
                print(f"  Failed to download asset {url}: status {response.status}")
        except Exception as e:
            print(f"  Error downloading asset {url}: {e}")
            
        return url # Return original URL if download fails

    async def rewrite_urls(self, soup: BeautifulSoup, page_url: str, request_context: APIRequestContext):
        """Rewrites all internal links and asset sources to be relative."""
        # 1. Update internal links (<a> tags)
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            if not href or href.startswith(('#', 'javascript:', 'tel:', 'mailto:','data:')):
                continue
                
            full_url = urljoin(page_url, href).split('#')[0].rstrip("/")
            if self.is_internal_link(full_url):
                local_name = self.clean_filename(full_url, is_page=True)
                # If we are in index.html, the link to about.html is just about.html
                a['href'] = local_name

        # 2. Update images
        for img in soup.find_all(['img', 'source'], src=True):
            src = img['src'].strip()
            full_src = urljoin(page_url, src)
            local_src = await self.download_asset(full_src, request_context)
            img['src'] = local_src
            
        # Also check srcset
        for tag in soup.find_all(srcset=True):
            srcset = tag['srcset']
            parts = srcset.split(',')
            new_parts = []
            for part in parts:
                subparts = part.strip().split(' ')
                if subparts:
                    asset_url = urljoin(page_url, subparts[0])
                    local_asset = await self.download_asset(asset_url, request_context)
                    subparts[0] = local_asset
                    new_parts.append(' '.join(subparts))
            tag['srcset'] = ', '.join(new_parts)

        # 3. Update scripts
        for script in soup.find_all('script', src=True):
            src = script['src'].strip()
            full_src = urljoin(page_url, src)
            local_src = await self.download_asset(full_src, request_context)
            script['src'] = local_src

        # 4. Update stylesheets
        for link in soup.find_all('link', rel='stylesheet', href=True):
            href = link['href'].strip()
            full_href = urljoin(page_url, href)
            local_href = await self.download_asset(full_href, request_context)
            link['href'] = local_href
            
        # 5. Update other links (icons, etc)
        for link in soup.find_all('link', rel=re.compile(r'icon|shortcut|apple-touch-icon'), href=True):
            href = link['href'].strip()
            full_href = urljoin(page_url, href)
            local_href = await self.download_asset(full_href, request_context)
            link['href'] = local_href

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

            # 1. Look for semantic navigation tags
            for container_tag in ['header', 'footer', 'nav']:
                containers = soup.find_all(container_tag)
                for container in containers:
                    for a in container.find_all('a', href=True):
                        href = a['href'].strip()
                        if not href or href.startswith(('#', 'javascript:', 'tel:', 'mailto:')):
                            continue
                        full_url = urljoin(self.base_url, href).split('#')[0].rstrip("/")
                        if self.is_internal_link(full_url):
                            links_to_visit.add(full_url)

            # 2. Search for common navigation classes/IDs
            # This is important because many sites use <div> for menus even if <header> exists
            nav_selectors = ['header', 'footer', 'nav', 'menu', 'sidebar', 'topbar', 'bottombar', 'navigation']
            for selector in nav_selectors:
                # Use regex to find partial matches like "main-menu" or "site-footer"
                pattern = re.compile(selector, re.I)
                containers = soup.find_all(attrs={"id": pattern}) + \
                            soup.find_all(attrs={"class": pattern})
                for container in containers:
                    # Avoid redundant searches if we already processed this container via tag
                    if container.name in ['header', 'footer', 'nav']:
                        continue
                    for a in container.find_all('a', href=True):
                        href = a['href'].strip()
                        if not href or href.startswith(('#', 'javascript:', 'tel:', 'mailto:')):
                            continue
                        full_url = urljoin(self.base_url, href).split('#')[0].rstrip("/")
                        if self.is_internal_link(full_url):
                            links_to_visit.add(full_url)

            # Filter out any lingering non-http links just in case
            links_to_visit = {url for url in links_to_visit if url.startswith('http')}

    async def crawl(self, depth: int = 1):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
            request_context = context.request
            page = await context.new_page()

            print(f"Starting crawl of: {self.base_url} (depth={depth})")
            
            queue = [(self.base_url, 0)]
            to_visit = {self.base_url}
            
            while queue:
                current_url, current_depth = queue.pop(0)
                if current_url in self.visited_urls:
                    continue
                
                print(f"[{len(self.visited_urls)+1}/?] Processing: {current_url} (depth {current_depth})")
                try:
                    await page.goto(current_url, wait_until="networkidle", timeout=60000)
                    await asyncio.sleep(1) # Small delay
                    
                    # 1. Take Screenshot if requested (default to True if not explicitly offline-only)
                    # For now, let's always take screenshots if it's the base behavior
                    filename = f"{self.clean_filename(current_url)}.png"
                    filepath = os.path.join(self.output_dir, filename)
                    await page.screenshot(path=filepath, full_page=True)
                    print(f"  Screenshot saved: {filename}")

                    # 2. Generate Offline Site if enabled
                    content = await page.content()
                    soup = BeautifulSoup(content, 'html.parser')

                    if self.offline:
                        print(f"  Generating offline version...")
                        await self.rewrite_urls(soup, current_url, request_context)
                        
                        local_html_name = self.clean_filename(current_url, is_page=True)
                        local_html_path = os.path.join(self.output_dir, local_html_name)
                        
                        with open(local_html_path, "w", encoding="utf-8") as f:
                            f.write(soup.prettify())
                        print(f"  Offline page saved: {local_html_name}")

                    self.visited_urls.add(current_url)

                    # 3. Discover more links if we haven't reached depth limit
                    if current_depth < depth:
                        new_links = self.discover_links(soup, current_url)
                        for link in new_links:
                            if link not in to_visit:
                                to_visit.add(link)
                                queue.append((link, current_depth + 1))
                                
                except Exception as e:
                    print(f"  Failed to process {current_url}: {e}")

            await browser.close()
            print(f"Crawl complete. Total pages visited: {len(self.visited_urls)}")

    def discover_links(self, soup: BeautifulSoup, current_url: str) -> Set[str]:
        """Extracts internal links from a page."""
        links = set()
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            if not href or href.startswith(('#', 'javascript:', 'tel:', 'mailto:', 'data:')):
                continue
            full_url = urljoin(current_url, href).split('#')[0].rstrip("/")
            if self.is_internal_link(full_url):
                links.add(full_url)
        return links

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
    parser = argparse.ArgumentParser(description="Website Cloner and Screenshot Tool")
    parser.add_argument("--url", help="Target website URL to crawl")
    parser.add_argument("--offline", action="store_true", help="Generate an offline version of the site")
    parser.add_argument("--depth", type=int, default=1, help="Crawl depth (0 for base URL only)")
    parser.add_argument("--output", help="Output directory name")
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
                    if os.path.isdir(d):
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

        cloner = WebsiteCloner(target_url, output_dir=args.output, offline=args.offline)
        asyncio.run(cloner.crawl(depth=args.depth))
