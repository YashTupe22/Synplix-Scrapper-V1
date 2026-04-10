import csv
from datetime import datetime
import os
import random
import re
import tempfile
import time
import urllib.parse

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.driver_cache import DriverCacheManager


DEFAULT_MAX_RESULTS = 20
DEFAULT_OUTPUT_FILE = "google_maps_leads.csv"
DEFAULT_HEADLESS = False


def setup_driver(headless=False):
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-setuid-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-zygote")
    options.add_argument("--single-process")
    options.add_argument("--remote-debugging-port=9222")
    options.add_argument("--window-size=1400,1000")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    remote_webdriver_url = (os.getenv("REMOTE_WEBDRIVER_URL") or "").strip()
    if remote_webdriver_url:
        return webdriver.Remote(command_executor=remote_webdriver_url, options=options)

    if os.getenv("VERCEL"):
        raise RuntimeError(
            "No local Chrome runtime is available in Vercel serverless. "
            "Set REMOTE_WEBDRIVER_URL to a hosted Selenium/Browserless endpoint, "
            "or deploy on Render with Chrome installed."
        )

    cache_root = os.path.join(tempfile.gettempdir(), "wdm_cache")
    os.makedirs(cache_root, exist_ok=True)
    cache_manager = DriverCacheManager(root_dir=cache_root)
    service = Service(ChromeDriverManager(cache_manager=cache_manager).install())
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


def _find_first_regex(text, pattern):
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(0).strip() if match else ""


def extract_phone(driver):
    selectors = [
        "button[data-item-id^='phone']",
        "button[aria-label*='Phone']",
        "button[data-tooltip*='phone']",
        "a[href^='tel:']",
    ]

    for selector in selectors:
        text_value = safe_find_text(driver, selector)
        phone_from_text = _find_first_regex(text_value, r"\+?\d[\d\s().-]{6,}\d")
        if phone_from_text:
            return phone_from_text

        aria_value = safe_find_attr(driver, selector, "aria-label")
        phone_from_aria = _find_first_regex(aria_value, r"\+?\d[\d\s().-]{6,}\d")
        if phone_from_aria:
            return phone_from_aria

        href_value = safe_find_attr(driver, selector, "href")
        if href_value.startswith("tel:"):
            return href_value.replace("tel:", "", 1).strip()

    return _find_first_regex(driver.page_source, r"\+?\d[\d\s().-]{8,}\d")


def extract_address(driver):
    selectors = [
        "button[data-item-id='address']",
        "button[data-item-id*='address']",
        "button[aria-label*='Address']",
        "div[data-item-id='address']",
    ]

    for selector in selectors:
        text_value = safe_find_text(driver, selector)
        if text_value:
            return text_value

        aria_value = safe_find_attr(driver, selector, "aria-label")
        if aria_value:
            parts = aria_value.split(":", 1)
            return parts[1].strip() if len(parts) > 1 else aria_value.strip()

    source_patterns = [
        r'"address":"([^\"]{10,})"',
        r'"streetAddress":"([^\"]{10,})"',
    ]
    for pattern in source_patterns:
        match = re.search(pattern, driver.page_source)
        if match:
            return match.group(1).encode("utf-8", "ignore").decode("unicode_escape", "ignore").strip()

    return ""


def extract_email(driver, website_url=""):
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

        contact_links = driver.find_elements(By.CSS_SELECTOR, "a[href]")
        candidates = []
        for link in contact_links:
            href = (link.get_attribute("href") or "").strip()
            if href and any(k in href.lower() for k in ["contact", "about", "support"]):
                candidates.append(href)
        for page_url in candidates[:2]:
            try:
                driver.get(page_url)
                WebDriverWait(driver, 6).until(
                    lambda d: d.execute_script("return document.readyState") in ["interactive", "complete"]
                )
                match = email_pattern.search(driver.page_source)
                if match:
                    return match.group(0)
            except Exception:
                continue
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
    if not name:
        return None

    website = safe_find_attr(driver, "a[data-item-id='authority']", "href")
    if not website:
        website = safe_find_attr(driver, "a[data-tooltip='Open website']", "href")

    category = safe_find_text(driver, "button[jsaction*='pane.rating.category']")
    rating = safe_find_text(driver, "div.F7nice span[aria-hidden='true']")
    phone = extract_phone(driver)
    address = extract_address(driver)
    email = extract_email(driver, website)

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


def scrape_google_maps(query, max_results=DEFAULT_MAX_RESULTS, headless=DEFAULT_HEADLESS):
    driver = None
    leads = []
    try:
        driver = setup_driver(headless=headless)
        place_links = collect_place_links(driver, query, max_results)
        for place_url in place_links:
            details = None
            for attempt in range(2):
                details = extract_place_details(driver, place_url, query)
                if details:
                    break
                if attempt == 0:
                    time.sleep(1.0)
            if details:
                leads.append(details)
            time.sleep(random.uniform(0.8, 1.8))
        return leads
    finally:
        if driver:
            driver.quit()


def write_to_csv(data, filename=DEFAULT_OUTPUT_FILE):
    if not data:
        return ""

    def fallback_path(base_path):
        directory = os.path.dirname(base_path) or os.getcwd()
        base_name = os.path.basename(base_path)
        name, ext = os.path.splitext(base_name)
        ext = ext or ".csv"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(directory, f"{name}_{stamp}{ext}")

    output_path = os.path.abspath(filename)
    fieldnames = list(data[0].keys())

    try:
        with open(output_path, "w", newline="", encoding="utf-8") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        return output_path
    except PermissionError:
        alt_path = fallback_path(output_path)
        with open(alt_path, "w", newline="", encoding="utf-8") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        return alt_path
