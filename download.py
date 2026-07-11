import os
import re
import json
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
        "stop_year": "2025"
    }
    if os.path.exists("config.json"):
        try:
            with open("config.json", "r") as f:
                return json.load(f)
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
    """Scrolls the viewport container to lazy-load and extract all image URLs."""
    os.makedirs(folder_path, exist_ok=True)
    
    # Try to focus on photo galleries if elements exist to clear modal issues
    photo_locator = page.locator('img[src*="procareconnect"], div[class*="gallery"], div[class*="scroll"]').first
    if photo_locator.count() > 0:
        try:
            photo_locator.hover(timeout=1000)
            page.mouse.click(photo_locator.bounding_box()['x'] + 10, photo_locator.bounding_box()['y'] + 10)
        except Exception:
            pass
    
    all_found_urls = set()
    target_prefix = "https://private.cdn.procareconnect.com/photos/files"
    no_new_links_count = 0
    
    # Scroll page iteratively to capture lazy-loading images
    for _ in range(15):
        urls = page.locator(f'img[src^="{target_prefix}"]').evaluate_all("elements => elements.map(el => el.getAttribute('src'))")
        if not urls:
            urls = page.locator(f'a[href^="{target_prefix}"]').evaluate_all("elements => elements.map(el => el.getAttribute('href'))")
            
        previous_total = len(all_found_urls)
        all_found_urls.update(urls)
        
        if len(all_found_urls) > previous_total:
            no_new_links_count = 0
        else:
            no_new_links_count += 1
            
        if no_new_links_count >= 4:
            break
            
        page.mouse.wheel(0, 800)
        page.wait_for_timeout(600)

    unique_urls = list(all_found_urls)
    if not unique_urls:
        print("   -> No photos found for this block.")
        return
        
    print(f"   -> Found {len(unique_urls)} images. Archiving data streams...")
    for index, url in enumerate(unique_urls, start=1):
        try:
            response = page.request.get(url)
            if response.status == 200:
                ext = ".png" if ".png" in url.lower() else ".jpg"
                file_name = f"photo_{index}{ext}"
                with open(os.path.join(folder_path, file_name), "wb") as f:
                    f.write(response.body())
        except Exception:
            pass

def run():
    config = load_config()
    view_mode = config.get("view_mode", "Weekly")
    stop_month = config.get("stop_month", "October")[:3] # Shorten to 3 letters (e.g. 'Oct')
    stop_year = config.get("stop_year", "2025")

    if not PROCARE_EMAIL or not PROCARE_PASSWORD:
        print("Error: Credentials missing from environment variables.")
        return

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

        target_gallery = "https://schools.procareconnect.com/dashboard/gallery/dfff226e-4fb6-4f8c-ba6f-f0ec8f362282/photos"
        page.goto(target_gallery)
        page.wait_for_timeout(3000)

        print(f"Configuring layout view mode to: '{view_mode}'...")
        page.get_by_text("Daily").first.click()
        page.wait_for_timeout(500)
        page.get_by_text(view_mode, exact=True).click()
        page.wait_for_timeout(3000)

        print(f"\n🚀 Starting engine. Rewinding back until {stop_month} {stop_year} is completed...")
        
        step = 1
        while True:
            # 1. Capture the localized date string banner
            date_text_locator = page.get_by_text(re.compile(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+")).first
            current_date_text = date_text_locator.text_content().strip()
            
            print(f"\nStep {step}: Currently processing: '{current_date_text}'")
            
            # 2. Dynamic check to see if we have stepped past our user-configured cutoff date
            if stop_month in current_date_text and stop_year in current_date_text:
                # We process the week context matching our stop targets first
                folder = get_clean_folder_path(current_date_text)
                scrape_visible_photos(page, folder)
                
                # Check ahead: If we click back one more time, we drop past our target. Stop now!
                print(f"🎉 Successfully reached stop target boundary ({stop_month} {stop_year}). Archive finalization complete!")
                break
                
            # 3. Create folder structural pathways and trigger lazy-load scraper downloads
            folder = get_clean_folder_path(current_date_text)
            scrape_visible_photos(page, folder)
            
            # 4. Safely apply coordinate shift clicks to advance the calendar backward 1 week
            box = date_text_locator.bounding_box()
            if box:
                click_x = box['x'] - 30
                click_y = box['y'] + (box['height'] / 2)
                page.mouse.click(click_x, click_y)
            else:
                print(" -> Error: Bounding box missed alignment layout tracks.")
                break
                
            page.wait_for_timeout(2500)
            step += 1

        print(f"\n✨ Operation Finished. Target folders structured inside '{BASE_DOWNLOAD_DIR}/'")
        browser.close()

if __name__ == "__main__":
    run()