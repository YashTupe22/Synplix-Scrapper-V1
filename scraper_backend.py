import argparse
import csv
from datetime import datetime
import os
import random
import re
import time
import urllib.parse

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


DEFAULT_OUTPUT_FILE = "google_maps_leads.csv"
DEFAULT_HEADLESS = False


def setup_driver(headless=False):
    """Initialize Chrome WebDriver."""
    if os.getenv("FORCE_HEADLESS", "false").strip().lower() in {"1", "true", "yes", "on"}:
        headless = True

    service = Service(ChromeDriverManager().install())
    options = webdriver.ChromeOptions()
    chrome_bin = os.getenv("CHROME_BIN", "").strip()
    if chrome_bin and os.path.exists(chrome_bin):
        options.binary_location = chrome_bin

    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1400,1000")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    return webdriver.Chrome(service=service, options=options)


def safe_find_text(driver, css_selector=None, xpath=None):
    try:
        if css_selector:
            return driver.find_element(By.CSS_SELECTOR, css_selector).text.strip()
        if xpath:
            return driver.find_element(By.XPATH, xpath).text.strip()
    except Exception:
        return ""
    return ""


def safe_find_attr(driver, css_selector, attribute):
    try:
        value = driver.find_element(By.CSS_SELECTOR, css_selector).get_attribute(attribute)
        return value.strip() if value else ""
    except Exception:
        return ""


def extract_phone(driver):
    """Extract phone using multiple selectors and a regex fallback."""
    selectors = [
        "button[data-item-id^='phone']",
        "button[aria-label*='Phone']",
        "button[data-tooltip*='phone']",
        "a[href^='tel:']",
    ]

    for selector in selectors:
        text_value = safe_find_text(driver, selector)
        if text_value:
            match = re.search(r"\+?\d[\d\s().-]{6,}\d", text_value)
            if match:
                return match.group(0).strip()

        aria_value = safe_find_attr(driver, selector, "aria-label")
        if aria_value:
            match = re.search(r"\+?\d[\d\s().-]{6,}\d", aria_value)
            if match:
                return match.group(0).strip()

        href_value = safe_find_attr(driver, selector, "href")
        if href_value and href_value.startswith("tel:"):
            return href_value.replace("tel:", "", 1).strip()

    source_match = re.search(r"\+?\d[\d\s().-]{8,}\d", driver.page_source)
    return source_match.group(0).strip() if source_match else ""


def extract_email(driver, website_url=""):
    """Extract email from Maps page first, then optionally from business website."""
    email_pattern = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

    for anchor in driver.find_elements(By.CSS_SELECTOR, "a[href^='mailto:']"):
        href = anchor.get_attribute("href") or ""
        if href.lower().startswith("mailto:"):
            candidate = href[7:].split("?")[0].strip()
            if email_pattern.fullmatch(candidate):
                return candidate

    map_source_match = email_pattern.search(driver.page_source)
    if map_source_match:
        return map_source_match.group(0)

    if not website_url:
        return ""

    try:
        driver.set_page_load_timeout(12)
        driver.get(website_url)
        WebDriverWait(driver, 8).until(
            lambda d: d.execute_script("return document.readyState") in ["interactive", "complete"]
        )
        website_source_match = email_pattern.search(driver.page_source)
        if website_source_match:
            return website_source_match.group(0)
    except Exception:
        return ""

    return ""


def collect_place_links(driver, query, max_results):
    encoded_query = urllib.parse.quote_plus(query)
    google_maps_url = f"https://www.google.com/maps/search/{encoded_query}"
    driver.get(google_maps_url)

    try:
        feed = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='feed']"))
        )
    except TimeoutException:
        return []

    collected = []
    seen = set()
    stable_scroll_count = 0
    previous_count = 0

    while len(collected) < max_results and stable_scroll_count < 8:
        anchors = feed.find_elements(By.CSS_SELECTOR, "a[href*='/maps/place/']")
        for anchor in anchors:
            href = anchor.get_attribute("href")
            if href and "/maps/place/" in href:
                normalized = href.split("&")[0]
                if normalized not in seen:
                    seen.add(normalized)
                    collected.append(normalized)
                if len(collected) >= max_results:
                    break

        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", feed)
        time.sleep(random.uniform(1.2, 2.2))

        if len(collected) == previous_count:
            stable_scroll_count += 1
        else:
            stable_scroll_count = 0
        previous_count = len(collected)

    return collected[:max_results]


def extract_place_details(driver, url, query):
    driver.get(url)
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1.DUwDvf, h1"))
        )
    except TimeoutException:
        return None

    name = safe_find_text(driver, "h1.DUwDvf") or safe_find_text(driver, "h1")
    address = safe_find_text(driver, "button[data-item-id='address']")
    phone = extract_phone(driver)
    website = safe_find_attr(driver, "a[data-item-id='authority']", "href")
    if not website:
        website = safe_find_attr(driver, "a[data-tooltip='Open website']", "href")
    email = extract_email(driver, website)
    rating = safe_find_text(driver, "div.F7nice span[aria-hidden='true']")
    category = safe_find_text(driver, "button[jsaction*='pane.rating.category']")

    if not name:
        return None

    return {
        "Name": name,
        "Category": category,
        "Rating": rating,
        "Phone": phone,
        "Email": email,
        "Website": website,
        "Address": address,
        "Google Maps URL": url,
        "Search Query": query,
    }


def scrape_google_maps(driver, query, max_results):
    leads = []
    place_links = collect_place_links(driver, query, max_results)

    for idx, place_url in enumerate(place_links, start=1):
        details = None
        for attempt in range(2):
            details = extract_place_details(driver, place_url, query)
            if details:
                break
            if attempt == 0:
                time.sleep(1.0)

        if details:
            leads.append(details)
            print(f"[{idx}/{len(place_links)}] Scraped: {details['Name']}")
        else:
            print(f"[{idx}/{len(place_links)}] Skipped (details not found).")
        time.sleep(random.uniform(0.8, 1.8))

    return leads


def write_to_csv(data, filename):
    if not data:
        return ""

    def fallback_path(base_path):
        directory = os.path.dirname(base_path) or os.getcwd()
        base_name = os.path.basename(base_path)
        name, ext = os.path.splitext(base_name)
        ext = ext or ".csv"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(directory, f"{name}_{stamp}{ext}")

    keys = data[0].keys()
    output_path = os.path.abspath(filename)

    try:
        with open(output_path, "w", newline="", encoding="utf-8") as output_file:
            dict_writer = csv.DictWriter(output_file, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(data)
        return output_path
    except PermissionError:
        alt_path = fallback_path(output_path)
        with open(alt_path, "w", newline="", encoding="utf-8") as output_file:
            dict_writer = csv.DictWriter(output_file, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(data)
        return alt_path


def run_scrape(query, max_results, output_file=DEFAULT_OUTPUT_FILE, headless=DEFAULT_HEADLESS):
    """Run full scrape flow and save CSV. Returns (leads, csv_path)."""
    if not query.strip():
        raise ValueError("Search query is required.")
    if max_results < 1:
        raise ValueError("max_results must be at least 1.")

    driver = None
    leads = []

    try:
        driver = setup_driver(headless=headless)
        leads = scrape_google_maps(driver, query, max_results)
    finally:
        if driver:
            driver.quit()

    saved_path = write_to_csv(leads, output_file)
    return leads, saved_path


def parse_args():
    parser = argparse.ArgumentParser(description="Scrape Google Maps leads and save to CSV.")
    parser.add_argument("--query", default="", help="Google Maps search query.")
    parser.add_argument("--max-results", type=int, default=20, help="Maximum leads.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_FILE, help="CSV output file path.")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode.")
    return parser.parse_args()


def main():
    args = parse_args()

    if not args.query.strip():
        args.query = input("Enter the search query: ").strip()

    if not args.query:
        raise SystemExit("Search query is required. Pass --query or type one when prompted.")

    if args.max_results < 1:
        raise SystemExit("--max-results must be at least 1.")

    try:
        leads, saved_path = run_scrape(
            query=args.query,
            max_results=args.max_results,
            output_file=args.output,
            headless=args.headless,
        )
    except Exception as exc:
        raise SystemExit(f"An error occurred during scraping: {exc}") from exc

    if saved_path:
        print(f"Saved {len(leads)} leads to: {saved_path}")
    else:
        print("No data was collected to write to CSV.")


if __name__ == "__main__":
    main()
