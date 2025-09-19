# Copyright (c) 2025 Karthick Ramakrishnan
# This file is part of Google Takeout Automation and is licensed under the MIT License.
# See the LICENSE file in the project root for more information.
import os
import re
import time
from collections.abc import Collection
from pathlib import Path
from typing import Final

import pyjson5
import selenium
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service as EdgeService

# Load environment variables from .env file
load_dotenv()

# Path to your WebDriver
WEBDRIVER_PATH = os.getenv("WEBDRIVER_PATH")

# Folder to save downloads
DOWNLOAD_FOLDER = os.getenv("DOWNLOAD_FOLDER")

# Browser type
BROWSER_TYPE = os.getenv("BROWSER_TYPE", "edge").lower().strip()

REAUTH_PASSWORD = os.getenv("REAUTH_PW_INSECURE", "")
if REAUTH_PASSWORD.lower().strip() in ["none", "null"]:
    REAUTH_PASSWORD = "" # pyright: ignore[reportConstantRedefinition]

standardOptionsArgs = [
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36", # cSpell: disable-line
    "--disable-blink-features=AutomationControlled"
]
prefs = {"download.default_directory": DOWNLOAD_FOLDER}

runtimeConfigPath = Path("config.json5")
if not runtimeConfigPath.is_file():
    raise FileNotFoundError("config.json5 file not found. Please create one -- see the repository for examples.")
runtimeConfig = pyjson5.loads(runtimeConfigPath.read_text("utf-8"))
VALID_TAKEOUT_DL_URLS:Final[Collection[str]] = runtimeConfig["takeoutDownloadPageURLFragments"]

# Configure browser options and
# initialize the WebDriver based on the selected browser type
match BROWSER_TYPE:
    case "edge":
        options = webdriver.EdgeOptions()
        service = EdgeService(WEBDRIVER_PATH)
        options.add_experimental_option("prefs", prefs)
        for _arg in standardOptionsArgs:
            options.add_argument(_arg)
        driver = webdriver.Edge(service= service, options= options)
    case "chrome":
        options = webdriver.ChromeOptions()
        service = ChromeService(WEBDRIVER_PATH)
        options.add_experimental_option("prefs", prefs)
        for _arg in standardOptionsArgs:
            options.add_argument(_arg)
        driver = webdriver.Chrome(service= service, options= options)
    case _:
        raise ValueError(f"Unsupported browser type `{BROWSER_TYPE}`. Please use 'edge' or 'chrome'.")

RETRIES:Final[int] = int(runtimeConfig["waitForUserInputHours"]) * 60

def isOnTakeoutPage() -> bool:
    for url in VALID_TAKEOUT_DL_URLS:
        if url in driver.current_url:
            return True
    return False

def wait_for_downloads(download_folder):
    while any(filename.endswith('.crdownload') for filename in os.listdir(download_folder)):
        time.sleep(1)

def get_downloaded_serials(download_folder):
    serials = set()
    for filename in os.listdir(download_folder):
        match = re.search(r'takeout-\d{8}T\d{6}Z-(?:\d-)?(\d{3}|[\da-e\-]+)\.zip', filename)
        if match:
            serials.add(match.group(1))
    return serials

def wait_for_reauthentication():
    sleepDuration = 60 # seconds
    minuteMultiplier = 60 / sleepDuration
    _retries = int(RETRIES * 60 * minuteMultiplier)
    for attempt in range(_retries):
        if len(REAUTH_PASSWORD) > 0:
            print("Trying automatic login")
            try:
                # Try filling the form
                time.sleep(1)
                _pwField = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
                _pwField.send_keys(REAUTH_PASSWORD)
                time.sleep(1)
                nextButton = driver.find_element(By.CSS_SELECTOR, "#passwordNext button")
                nextButton.click()
                time.sleep(sleepDuration // 3)  # Wait a bit for the page to load
                if isOnTakeoutPage():
                    print("*" * 20, "\n", "Automatic login success\n", "*" * 20, "\n")
                    return True
            except Exception:
                pass
        print(f"Reauthentication required. Please log in again. Attempt {attempt + 1} of {RETRIES}.")
        time.sleep(60)  # Wait for 1 minute
        if isOnTakeoutPage():
            return True
    return False

def wait_for_stale_element_retry():
    for attempt in range(36):
        print(f"Stale element reference exception caught. Retrying... Attempt {attempt + 1} of 36.")
        time.sleep(5)  # Wait for 1 minute
        if isOnTakeoutPage():
            return True
        print("Invalid URL:", driver.current_url)
    return False

# Function to download files
def download_files(_downloaded_serials):
    TAKEOUT_SELECTOR = "i.material-icons-extended + span + a"
    # Locate all download elements with the download icon using XPath
    download_elements = driver.find_elements(By.CSS_SELECTOR, TAKEOUT_SELECTOR)
    print(f"Found {len(download_elements)} files to download.")

    if not download_elements:
        return

    _ok = True
    for i, element in enumerate(download_elements):
        while True:
            if not _ok:
                # use alternate re-crawl method
                element = driver.find_elements(By.CSS_SELECTOR, TAKEOUT_SELECTOR)[i]
            try:
                # Get the parent element which contains the download link
                parent_element = element.find_element(By.XPATH, "..")
                download_link = parent_element.find_element(By.CSS_SELECTOR, "a[href*='takeout/download']")
                download_url = download_link.get_attribute("href")

                # Get the serial from the download URL (if applicable)
                # TODO append the J to the download file as a serial match
                serial_match = re.search(r'i=(\d+)', download_url)
                if not serial_match:
                    serial_match = re.search(r'j=([\da-e\-]+)', download_url)
                serial = str(int(serial_match.group(1)) + 1).zfill(3) if serial_match else None

                if serial and serial in _downloaded_serials:
                    print(f"File with serial {serial} already downloaded locally, skipping...")
                    break

                # Download the file
                print(f"Downloading file (serial: {serial}): {download_url}")
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
                    # TODO rename downloaded file

            except selenium.common.exceptions.StaleElementReferenceException as e:
                if len(download_elements) > 1:
                    if not wait_for_stale_element_retry():
                        print("Failed to resolve stale element reference. Exiting...")
                        return
                else:
                    print(e)
                    print("Stale element reference exception caught. Retrying...")
                    time.sleep(2)  # Wait before retrying
                # Retry the selector search
                _ok = False
                continue
            else:
                # _ok = True
                break

    # Final check to ensure all downloads are complete
    wait_for_downloads(DOWNLOAD_FOLDER)

try:
    # Open the Google Takeout downloads page
    driver.get("https://takeout.google.com/settings/takeout/downloads")
    input("Log in to your Google account & choose the takeout export to download. Then press Enter to continue...")

    # Get already downloaded serials
    downloaded_serials = get_downloaded_serials(DOWNLOAD_FOLDER)
    if downloaded_serials:
        print("Already got", downloaded_serials)
    else:
        print("Fresh download")

    # Download files
    download_files(downloaded_serials)

    print("Downloads finished. Check your download folder.")

finally:
    # Find duplicate downloads, eg, big images that downloaded directly
    # but couldn't be serial checked
    downloadDir = Path(DOWNLOAD_FOLDER)
    for duplicate in downloadDir.glob("* (*).*"):
        duplicate.unlink()
    driver.quit()
