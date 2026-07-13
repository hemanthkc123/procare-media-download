import os
import re
import json
from datetime import datetime, timedelta
import csv  # Added for CSV tracking
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# Load secret account variables from the .env file
load_dotenv()
PROCARE_EMAIL = os.getenv("PROCARE_EMAIL")
PROCARE_PASSWORD = os.getenv("PROCARE_PASSWORD")

BASE_DOWNLOAD_DIR = "procare_archive"

def load_config():
    """Loads runtime definitions from local config file."""
    default_config = {
        "view_mode": "Weekly",
        "stop_month": "October",
        "stop_year": "2025",
        "target_gallery": "https://schools.procareconnect.com/dashboard/gallery/dfff226e-4fb6-4f8c-ba6f-f0ec8f362282/photos"
    }
    if os.path.exists("config.json"):
        try:
            with open("config.json", "r") as f:
                # Merge defaults with local config so missing keys don't crash it
                user_config = json.load(f)
                default_config.update(user_config)
                return default_config
        except Exception as e:
            print(f"Warning: Failed to read config.json ({e}). Using defaults.")
    return default_config

def get_clean_folder_path(date_range_text):
    """Parses date strings into Year/Month/Week_Range folder hierarchy."""
    date_clean = date_range_text.strip().replace("\n", " ").replace("–", "-")
    
    # Identify a 4-digit year, default to 2026 if not found in the current string
    year_match = re.search(r'\b(202\d)\b', date_clean)
    year = year_match.group(1) if year_match else "2026"
    
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    found_month = "Unknown_Month"
    for m in months:
        if m in date_clean:
            found_month = m
            break
            
    clean_range = re.sub(r'[^\w\s-]', '', date_clean).strip().replace(' ', '_')
    return os.path.join(BASE_DOWNLOAD_DIR, year, found_month, clean_range)

def scrape_visible_photos(page, folder_path):
    """Scrolls the viewport container using browser-level execution to unpack lazy-loaded images, 

    including standard HTML tags and CSS background-image style layers.
    """
    os.makedirs(folder_path, exist_ok=True)
    
    all_found_urls = set()
    no_new_links_count = 0
    
    # FIX: Targets both domains and accepts any valid URL characters immediately following '/photos/'
    procare_url_pattern = re.compile(r'https://(?:private|mobile)\.cdn\.procareconnect\.com/photos/[^\s"\'\)]+')
    
    print("   -> Running unified smooth-scrolling engine (Tags + CSS Backgrounds)...")
    
    for scroll_step in range(40):
        # JavaScript asset-hunter: looks at every element's attributes and computed inline styles
        raw_strings = page.locator('*').evaluate_all("""
            elements => {
                let found = [];
                elements.forEach(el => {
                    // Pull standard asset strings
                    if (el.src) found.push(el.src);
                    if (el.href) found.push(el.href);
                    
                    // Pull custom attributes
                    let dataSrc = el.getAttribute('data-src') || el.getAttribute('data-srcset') || el.getAttribute('srcset');
                    if (dataSrc) found.push(dataSrc);
                    
                    // Pull inline styles (looking for background-image parameters)
                    let style = el.getAttribute('style');
                    if (style) found.push(style);
                });
                return found;
            }
        """)
        
        # Parse and extract raw URLs matching Procare CDN architecture out of the captured attributes/styles
        valid_urls = []
        for item in raw_strings:
            matches = procare_url_pattern.findall(item)
            for match in matches:
                # Clean up any trailing characters like query params, structural quotes, or closing parenthesis
                clean_url = match.split(')')[0].split('"')[0].split("'")[0]
                valid_urls.append(clean_url)
            
        previous_total = len(all_found_urls)
        all_found_urls.update(valid_urls)
        
        # Increment our stop metric ONLY if no actual new target assets appear
        if len(all_found_urls) > previous_total:
            no_new_links_count = 0
        else:
            no_new_links_count += 1
            
        # Break only if we've scrolled 6 consecutive times with zero true photos loading
        if no_new_links_count >= 6:
            break
            
        # Shift container viewport downward
        try:
            page.evaluate("window.scrollBy(0, 900);")
            page.evaluate("""
                document.querySelectorAll('div, section, main').forEach(el => {
                    if (el.scrollHeight > el.clientHeight) {
                        el.scrollBy(0, 900);
                    }
                });
            """)
        except Exception:
            pass
            
        page.wait_for_timeout(900)

    unique_urls = list(all_found_urls)
    if not unique_urls:
        print("   -> No photos found for this block.")
        return
        
    # --- CSV Tracking Logic Implementation ---
    tracker_path = os.path.join(folder_path, "download_tracker.csv")
    downloaded_urls = set()
    max_existing_index = 0

    if os.path.exists(tracker_path):
        try:
            with open(tracker_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)  # Skip CSV header
                for row in reader:
                    if row:
                        downloaded_urls.add(row[0])
                        if len(row) > 1:
                            match = re.search(r'photo_(\d+)', row[1])
                            if match:
                                max_existing_index = max(max_existing_index, int(match.group(1)))
        except Exception as e:
            print(f"   -> Warning: Failed to parse tracker file ({e})")

    new_urls = [url for url in unique_urls if url not in downloaded_urls]
    
    if not new_urls:
        print(f"   -> All {len(unique_urls)} images already archived. Skipping download sequence.")
        return

    print(f"   -> Found {len(unique_urls)} images ({len(new_urls)} are new). Archiving data streams...")
    
    current_index = max_existing_index + 1
    tracker_exists = os.path.exists(tracker_path)

    try:
        with open(tracker_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not tracker_exists:
                writer.writerow(["url", "filename"])

            for url in new_urls:
                try:
                    response = page.request.get(url)
                    if response.status == 200:
                        ext = ".png" if ".png" in url.lower() else ".jpg"
                        file_name = f"photo_{current_index}{ext}"
                        
                        while os.path.exists(os.path.join(folder_path, file_name)):
                            current_index += 1
                            file_name = f"photo_{current_index}{ext}"

                        with open(os.path.join(folder_path, file_name), "wb") as img_file:
                            img_file.write(response.body())
                        
                        writer.writerow([url, file_name])
                        current_index += 1
                except Exception as e:
                    print(f"   -> Error pulling media file content: {e}")
    except Exception as e:
        print(f"   -> Error updating tracker pipeline: {e}")

def run():
    config = load_config()
    view_mode = config.get("view_mode", "Weekly")
    stop_month_str = config.get("stop_month", "September")
    stop_year_str = config.get("stop_year", "2025")
    target_gallery = config.get("target_gallery")

    if not PROCARE_EMAIL or not PROCARE_PASSWORD:
        print("Error: Credentials missing from environment variables.")
        return

    if not target_gallery:
        print("Error: 'target_gallery' is missing from the configuration data.")
        return

    # Convert config targets into an absolute chronological cutoff object
    try:
        cutoff_date = datetime.strptime(f"1 {stop_month_str} {stop_year_str}", "%d %B %Y")
    except ValueError:
        cutoff_date = datetime.strptime(f"1 {stop_month_str[:3]} {stop_year_str}", "%d %b %Y")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        print("Logging in...")
        page.goto("https://schools.procareconnect.com/login")
        page.get_by_text("PARENT", exact=True).click()
        page.wait_for_timeout(500) 
        page.locator('input[type="email"]').first.fill(PROCARE_EMAIL)
        page.locator('input[type="password"]').fill(PROCARE_PASSWORD)
        page.locator('input[type="password"]').press("Enter")
        page.wait_for_timeout(5000) 

        print(f"Navigating to gallery: {target_gallery}")
        page.goto(target_gallery)
        page.wait_for_timeout(3000)

        print(f"Configuring layout view mode to: '{view_mode}'...")
        page.get_by_text("Daily").first.click()
        page.wait_for_timeout(500)
        page.get_by_text(view_mode, exact=True).click()
        page.wait_for_timeout(3000)

        print(f"\n🚀 Starting engine. Rewinding back until {stop_month_str} {stop_year_str} is completed...")
        
        step = 1
        last_seen_date = ""
        current_inferred_year = datetime.now().year # Dynamically anchors context
        
        while True:
            # 1. Capture the localized date string banner
            date_text_locator = page.get_by_text(re.compile(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+")).first
            current_date_text = date_text_locator.text_content().strip()
            
            normalized_banner = " ".join(current_date_text.split())
            
            print(f"\nStep {step}: Currently processing: '{normalized_banner}'")
            
            if normalized_banner == last_seen_date:
                print("🚨 Detect Loop Error: The calendar date failed to flip backward. Breaking navigation.")
                break
            last_seen_date = normalized_banner
            
            # Check if Procare explicitly specifies a year change inside the text banner layout
            year_match = re.search(r'\b(202\d)\b', normalized_banner)
            if year_match:
                current_inferred_year = int(year_match.group(1))
            elif "Jan" in normalized_banner and step > 1 and last_seen_date.startswith("Dec"):
                # Handle tracking adjustments across holiday boundaries
                current_inferred_year -= 1
            
            # Parse the start boundary of the current week chunk (e.g., "Aug 25 – Aug 31" -> "Aug 25")
            start_date_part = normalized_banner.split("–")[0].strip() 
            try:
                current_week_start = datetime.strptime(f"{start_date_part} {current_inferred_year}", "%b %d %Y")
            except ValueError:
                current_week_start = datetime.strptime(f"{start_date_part} {current_inferred_year}", "%b %e %Y")

            # --- CHRONOLOGICAL CONFIG CUTOFF CHECK ---
            if current_week_start < cutoff_date:
                print(f"🎉 Current position ({current_week_start.strftime('%B %Y')}) is past your config stop target boundary ({stop_month_str} {stop_year_str}). Archive complete!")
                break
                
            # 3. Create folder structural pathways and trigger lazy-load scraper downloads
            folder = get_clean_folder_path(normalized_banner)
            scrape_visible_photos(page, folder)
            
            # --- JAVASCRIPT REVERSE SCROLL TO TOP ---
            print("   -> Resetting layout container positions to top...")
            try:
                page.evaluate("window.scrollTo(0, 0);")
                page.evaluate("""
                    document.querySelectorAll('div, section, main').forEach(el => {
                        if (el.scrollHeight > el.clientHeight) {
                            el.scrollTop = 0;
                        }
                    });
                """)
            except Exception:
                pass
            
            page.wait_for_timeout(1500)
            
            # 4. Target the arrow using position matching relative to the date text banner
            prev_button = page.locator(f'button:left-of(:text("{current_date_text}"))').first

            if prev_button.count() > 0 and prev_button.is_visible():
                print("   -> Navigation button found. Executing date flip...")
                prev_button.click()
            else:
                print("   -> Element selector hidden. Applying bounding box mouse track...")
                box = date_text_locator.bounding_box()
                if box:
                    page.mouse.click(box['x'] - 40, box['y'] + (box['height'] / 2))
                else:
                    print(" -> Error: Bounding box missed alignment layout tracks.")
                    break
                
            try:
                page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass
                
            page.wait_for_timeout(2000)
            step += 1

        print(f"\n✨ Operation Finished. Target folders structured inside '{BASE_DOWNLOAD_DIR}/'")
        browser.close()

if __name__ == "__main__":
    run()