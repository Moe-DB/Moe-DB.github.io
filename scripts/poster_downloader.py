import os
import requests
import csv
import time
import urllib3
import random
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Configuration ---
INPUT_CSV = 'anilist_data_with_img_status.csv'
OUTPUT_CSV = 'full_data_with_all_img_status.csv'
PROXY_FILE = 'proxy_list.txt'  # <-- New file for your list of proxies
PARENT_DIR = 'img'
TMDB_DIR = os.path.join(PARENT_DIR, 'tmdbimg')

# ---!! BE GENTLE !!---
MAX_WORKERS = 3  # Keep this low!
MAX_RETRIES = 5
WAIT_ON_ERROR = 30  # Reduced this to 30s before trying the next proxy
# --- End Configuration ---

# Disable SSL warnings (can be common with proxies)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
os.makedirs(TMDB_DIR, exist_ok=True)


class ProxyRotator:
    """Manages the list of proxies and rotates to the next one on failure."""

    def __init__(self, proxy_file):
        self.proxies = self._load_proxies(proxy_file)
        self.current_proxy_index = 0
        if self.proxies:
            print(f"Loaded {len(self.proxies)} valid proxies from {proxy_file}")
            self.current_proxy = self._get_proxies_dict(self.proxies[0])
            print(f"Starting with proxy: {self.proxies[0]}")
        else:
            self.current_proxy = None
            print("WARNING: No valid proxies loaded. Will attempt direct connection (if allowed).")

    def _load_proxies(self, proxy_file):
        try:
            with open(proxy_file, 'r', encoding='utf-8') as f:
                raw_proxies = []
                for line in f:
                    # 1. Strip leading/trailing whitespace (CRITICAL FIX)
                    line = line.strip()

                    # 2. Ignore empty lines or lines starting with '#'
                    if line and not line.startswith('#'):
                        # 3. Only take the part of the line BEFORE the first '#'
                        # This handles proxies that have comments on the same line
                        if '#' in line:
                            line = line.split('#')[0].strip()

                        if line:  # Check again if the line is not empty after stripping the comment
                            raw_proxies.append(line)

            # Shuffling the list helps ensure we don't always hit the same bad proxies first
            random.shuffle(raw_proxies)
            return raw_proxies
        except FileNotFoundError:
            print(f"Error: Proxy file '{proxy_file}' not found.")
            return []

    def _get_proxies_dict(self, proxy_url):
        # The requests library requires this format for its 'proxies' argument
        return {
            'http': proxy_url,
            'https': proxy_url,
        }

    def get_current_proxy(self):
        """Returns the proxy dictionary for the requests call."""
        return self.current_proxy

    def rotate(self):
        """Switches to the next proxy in the list."""
        if not self.proxies:
            return False  # No proxies to rotate

        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxies)

        # Check if we looped back to the start (proxy_index 0)
        if self.current_proxy_index == 0:
            print("--- Rotated back to the start of the proxy list. Trying again... ---")

        next_proxy_url = self.proxies[self.current_proxy_index]
        self.current_proxy = self._get_proxies_dict(next_proxy_url)
        print(f"\n--- SWITCHING PROXY ---")
        print(f"Trying new proxy ({self.current_proxy_index + 1}/{len(self.proxies)}): {next_proxy_url}")
        print(f"-----------------------\n")
        return True  # Successfully rotated

    def is_proxy_available(self):
        return bool(self.proxies)


# Initialize the Proxy Rotator
proxy_manager = ProxyRotator(PROXY_FILE)


def is_tmdb(url):
    return url and 'tmdb' in url.lower()


def get_filename_from_url(url):
    path = urlparse(url).path
    return os.path.basename(path)


def download_with_retries(url, img_path, max_retries=MAX_RETRIES, wait_on_fail=WAIT_ON_ERROR):
    retries = 0
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    while retries <= max_retries:
        try:
            current_proxies = proxy_manager.get_current_proxy()

            # Use the current proxy set by the manager
            r = requests.get(
                url,
                timeout=20,
                headers=headers,
                proxies=current_proxies,
                verify=False
            )

            if r.ok:
                with open(img_path, 'wb') as imgfile:
                    imgfile.write(r.content)
                print(f"Downloaded {os.path.basename(img_path)}")
                return True

            elif r.status_code == 429:
                retry_after = int(r.headers.get("Retry-After", 30))
                print(f"Rate limited (429) for {url}. Waiting {retry_after} seconds...")
                time.sleep(retry_after)
                continue

            # TMDb block (403 Forbidden) or Proxy Authentication required (407)
            elif r.status_code in [403, 407]:
                print(f"Status Code {r.status_code} for {url}. Proxy is likely blocked or needs auth. Rotating...")
                if proxy_manager.rotate():
                    retries = 0  # Reset retries for the new proxy
                    time.sleep(1)
                    continue
                else:
                    return False  # No more proxies

            else:
                print(f"Failed to download {url} (status {r.status_code}).")
                time.sleep(5)  # Short wait for non-critical errors

        # --- Catch Proxy/Connection Errors and ROTATE ---
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError) as ex:
            # Check for BadStatusLine errors which mean SSH/SOCKS confusion or other major connection issues
            if "BadStatusLine" in str(ex):
                print(
                    f"Protocol Error for {url}. Proxy type is likely wrong (e.g., SSH or missing SOCKS install). Rotating...")
            elif "10061" in str(ex):
                print(f"Connection actively refused for {url}. Proxy is banned or dead. Rotating...")
            else:
                print(f"Connection/Proxy Error for {url}: {ex}. Rotating...")

            if proxy_manager.rotate():
                retries = 0  # Reset retries for the new proxy
                time.sleep(1)
                continue
            else:
                return False  # No more proxies

        except requests.exceptions.RequestException as ex:
            print(f"General Error downloading {url}: {ex}. Retrying with same proxy...")
            time.sleep(5)

        retries += 1

    print(f"Gave up on {url} after {max_retries} retries on multiple proxies.")
    return False


def main():
    if not proxy_manager.is_proxy_available() and not proxy_manager.current_proxy:
        print("\n**!!! WARNING !!!**\nNo proxies loaded and no direct connection attempted. Script cannot proceed.")
        return

    print(f"Reading data from {INPUT_CSV}...")

    try:
        with open(INPUT_CSV, newline='', encoding='utf-8') as infile:
            reader = csv.DictReader(infile)
            rows = list(reader)
    except FileNotFoundError:
        print(f"Error: Input file not found at {INPUT_CSV}")
        return
    except Exception as e:
        print(f"Error reading {INPUT_CSV}: {e}")
        return

    print(f"Found {len(rows)} rows. Checking for TMDb images to download...")

    # 1. Prepare data and identify 'pending' jobs
    jobs = []
    pending_jobs = 0
    for row in rows:
        url = row.get('poster_url', '').strip()

        if is_tmdb(url):
            img_filename = get_filename_from_url(url)
            img_path = os.path.join(TMDB_DIR, img_filename)
            row['tmdb_img_filename'] = img_filename

            if os.path.exists(img_path):
                row['tmdb_status'] = 'downloaded'
            else:
                row['tmdb_status'] = 'pending'
                # Prepare job for executor
                jobs.append((row, url, img_path))
                pending_jobs += 1
        else:
            row.setdefault('tmdb_img_filename', '')
            row.setdefault('tmdb_status', 'not_tmdb')

    print(f"Submitting {pending_jobs} new TMDb images for download (Max {MAX_WORKERS} at a time)...")

    # 2. Execute download jobs
    futures = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for row, url, img_path in jobs:
            # The future result will be True/False for download success
            futures.append(executor.submit(download_with_retries, url, img_path))

        completed = 0
        failed = 0

        # Use a secondary list to map results back to rows after completion
        job_map = {future: (row, url) for future, (row, url, img_path) in zip(futures, jobs)}

        for fut in as_completed(futures):
            row, url = job_map[fut]
            try:
                success = fut.result()
                if success:
                    row['tmdb_status'] = 'downloaded'
                    completed += 1
                else:
                    row['tmdb_status'] = 'not_downloaded'
                    row['tmdb_img_filename'] = ''
                    failed += 1
            except Exception as e:
                print(f"A job for {url} failed with an unhandled exception: {e}")
                row['tmdb_status'] = 'error'
                row['tmdb_img_filename'] = ''
                failed += 1

    print("-" * 20)
    print(f"TMDb Image Download Complete: Downloaded {completed}, Failed {failed}.")
    print("-" * 20)

    # 3. Save result to NEW CSV file
    if not rows:
        print("No data to write. Exiting.")
        return

    # Ensure all rows have the expected new fields before writing
    out_fields = list(rows[0].keys())
    out_fields.extend(['tmdb_img_filename', 'tmdb_status'])
    out_fields = sorted(list(set(out_fields)), key=lambda x: x.split('_')[0])  # Simple sort

    try:
        with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=out_fields)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Successfully wrote all data to {OUTPUT_CSV}.")
    except Exception as e:
        print(f"Error writing to {OUTPUT_CSV}: {e}")


if __name__ == '__main__':
    # Make sure you've run 'pip install requests[socks]' if you use SOCKS proxies!
    main()