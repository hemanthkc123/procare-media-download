import os
import re
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()
PROCARE_EMAIL = os.getenv("PROCARE_EMAIL")
PROCARE_PASSWORD = os.getenv("PROCARE_PASSWORD")

BASE_DOWNLOAD_DIR = "procare_archive"

def get_clean_folder_path(date_range_text):
    """
    Parses date strings like 'Jul 6 - Jul 12' or 'Dec 29 - Jan 4, 2026'
    and structures them cleanly into Year/Month/Week_Range.
    """
    date_clean = date_range_text.strip().replace("\n", " ").replace("–", "-")
    
    # Check if a 4-digit year is explicitly inside the text (common around late Dec / early Jan)
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

def run():
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

        print("Switching layout context to 'Weekly'...")
        page.get_by_text("Daily").first.click()
        page.wait_for_timeout(500)
        page.get_by_text("Weekly", exact=True).click()
        page.wait_for_timeout(3000)

        print("\n=== STARTING FOLDER CREATION & NAVIGATION ENGINE ===")
        
        # We will loop backward up to 45 times to watch it cross into 2025
        for step in range(1, 46):
            # 1. Target the date text element specifically
            date_text_locator = page.get_by_text(re.compile(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+")).first
            current_date_text = date_text_locator.text_content().strip()
            
            print(f"\nStep {step}: Found Text: '{current_date_text}'")
            
            # Stop condition if we run past our goal month into September 2025
            if "Sep" in current_date_text and "2025" in current_date_text:
                print("-> Target October 2025 limit fully surpassed! Stopping loop.")
                break
            
            # 2. Build the directory path and physically create the empty folder
            folder_path = get_clean_folder_path(current_date_text)
            os.makedirs(folder_path, exist_ok=True)
            print(f" -> Successfully mapped/created folder: {folder_path}")
            
            # 3. Use coordinate math to click the left arrow icon cleanly
            box = date_text_locator.bounding_box()
            if box:
                click_x = box['x'] - 30
                click_y = box['y'] + (box['height'] / 2)
                
                page.mouse.click(click_x, click_y)
                print(" -> Left chevron clicked.")
            else:
                print(" -> Error: Bounding box missing.")
                break
                
            page.wait_for_timeout(2000)

        print(f"\n=== TEST COMPLETE ===")
        print(f"Check your local directory structure inside the '{BASE_DOWNLOAD_DIR}' folder!")
        browser.close()

if __name__ == "__main__":
    run()