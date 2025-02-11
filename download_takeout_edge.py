# Copyright (c) 2025 Karthick Ramakrishnan
# This file is part of Google Takeout Automation and is licensed under the MIT License.
# See the LICENSE file in the project root for more information.
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.chrome.service import Service as ChromeService
import time
import os
import re
import selenium
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Path to your WebDriver
WEBDRIVER_PATH = os.getenv("WEBDRIVER_PATH")

# Folder to save downloads
DOWNLOAD_FOLDER = os.getenv("DOWNLOAD_FOLDER")

# Browser type
BROWSER_TYPE = os.getenv("BROWSER_TYPE", "edge").lower()

# Configure browser options
if BROWSER_TYPE == "edge":
    options = webdriver.EdgeOptions()
    service = EdgeService(WEBDRIVER_PATH)
elif BROWSER_TYPE == "chrome":
    options = webdriver.ChromeOptions()
    service = ChromeService(WEBDRIVER_PATH)
else:
    raise ValueError("Unsupported browser type. Please use 'edge' or 'chrome'.")

prefs = {"download.default_directory": DOWNLOAD_FOLDER}
options.add_experimental_option("prefs", prefs)
options.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
)
options.add_argument("--disable-blink-features=AutomationControlled")

# Set up the Selenium WebDriver
if BROWSER_TYPE == "edge":
    driver = webdriver.Edge(service=service, options=options)
elif BROWSER_TYPE == "chrome":
    driver = webdriver.Chrome(service=service, options=options)

def wait_for_downloads(download_folder):
    while any(filename.endswith('.crdownload') for filename in os.listdir(download_folder)):
        time.sleep(1)

def get_downloaded_serials(download_folder):
    serials = set()
    for filename in os.listdir(download_folder):
        match = re.search(r'takeout-\d{8}T\d{6}Z-(\d{3})\.zip', filename)
        if match:
            serials.add(match.group(1))
    return serials

def wait_for_reauthentication():
    for attempt in range(3):
        print(f"Reauthentication required. Please log in again. Attempt {attempt + 1} of 3.")
        time.sleep(60)  # Wait for 1 minute
        if "takeout.google.com/settings/takeout/downloads" in driver.current_url:
            return True
    return False

def wait_for_stale_element_retry():
    for attempt in range(3):
        print(f"Stale element reference exception caught. Retrying... Attempt {attempt + 1} of 3.")
        time.sleep(60)  # Wait for 1 minute
        if "takeout.google.com/settings/takeout/downloads" in driver.current_url:
            return True
    return False

try:
    # Open the Google Takeout downloads page
    driver.get("https://takeout.google.com/settings/takeout/downloads")
    input("Log in to your Google account & choose the takeout export to dowload. Then press Enter to continue...")

    # Get already downloaded serials
    downloaded_serials = get_downloaded_serials(DOWNLOAD_FOLDER)

    # Function to download files
    def download_files():
        while True:
            # Locate all download elements with the download icon using XPath
            download_elements = driver.find_elements(By.XPATH, "//tr[@class='p06IYb']//td[last()]//div[@jsname='Rfwdsf']//i[contains(text(), 'file_download')]")
            print(f"Found {len(download_elements)} files to download.")

            if not download_elements:
                break

            while download_elements:
                try:
                    # Get the first element from the list
                    element = download_elements.pop(0)

                    # Get the parent element which contains the download link
                    parent_element = element.find_element(By.XPATH, "..")
                    download_link = parent_element.find_element(By.CSS_SELECTOR, "a[href*='takeout/download']")
                    download_url = download_link.get_attribute("href")

                    # Get the serial from the download URL (if applicable)
                    serial_match = re.search(r'i=(\d+)', download_url)
                    serial = str(int(serial_match.group(1)) + 1).zfill(3) if serial_match else None

                    if serial and serial in downloaded_serials:
                        print(f"File with serial {serial} already downloaded locally, skipping...")
                        continue

                    # Download the file
                    print(f"Downloading file: {download_url}")
                    driver.get(download_url)
                    time.sleep(7)  # Allow time for download to begin

                    # Check if reauthentication is required
                    if "accounts.google.com" in driver.current_url:
                        if not wait_for_reauthentication():
                            print("Failed to reauthenticate. Exiting...")
                            return

                    wait_for_downloads(DOWNLOAD_FOLDER)

                    # Update the downloaded serials set
                    if serial:
                        downloaded_serials.add(serial)

                except selenium.common.exceptions.StaleElementReferenceException:
                    if len(download_elements) > 1:
                        if not wait_for_stale_element_retry():
                            print("Failed to resolve stale element reference. Exiting...")
                            return
                    else:
                        print("Stale element reference exception caught. Retrying...")
                        time.sleep(2)  # Wait before retrying
                    break  # Break the inner loop to re-fetch elements

            # Final check to ensure all downloads are complete
            wait_for_downloads(DOWNLOAD_FOLDER)

    # Download files
    download_files()

    print("Downloads finished. Check your download folder.")

finally:
    driver.quit()
