# Copyright (c) 2025 Karthick Ramakrishnan
# This file is part of Google Takeout Automation and is licensed under the MIT License.
# See the LICENSE file in the project root for more information.
import os
import re
import time
from collections.abc import Collection
from pathlib import Path
from typing import Any, Final, Set, TypeVar, Union

import pyjson5
import selenium
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service as EdgeService

PathLike = Union[str, Path]

# Load environment variables from .env file
load_dotenv()

# Path to your WebDriver
WEBDRIVER_PATH = Path(__path) if (__path := os.getenv("WEBDRIVER_PATH")) is not None else None

if not WEBDRIVER_PATH:
    raise ValueError("WEBDRIVER_PATH environment variable not set. Please set it to the path of your WebDriver executable.")
elif not WEBDRIVER_PATH.is_file():
    raise FileNotFoundError(f"WebDriver executable not found at {WEBDRIVER_PATH.resolve()}. Please set the WEBDRIVER_PATH environment variable correctly.")

# Folder to save downloads
if (__path := os.getenv("DOWNLOAD_FOLDER")) is None:
    raise ValueError("DOWNLOAD_FOLDER environment variable not set. Please set it to the path of your download folder.")
DOWNLOAD_FOLDER:Final[Path] = Path(__path)

# Browser type
BROWSER_TYPE = os.getenv("BROWSER_TYPE", "edge").lower().strip()

REAUTH_PASSWORD = os.getenv("REAUTH_PW_INSECURE", "")
if REAUTH_PASSWORD.lower().strip() in ["none", "null"]:
    REAUTH_PASSWORD = "" # pyright: ignore[reportConstantRedefinition]


## Setup common browser options ##
standardOptionsArgs = [
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36", # cSpell: disable-line
    "--disable-blink-features=AutomationControlled"
]
if not DOWNLOAD_FOLDER.is_dir():
    try:
        DOWNLOAD_FOLDER.mkdir(parents=True)
    except Exception as e:
        raise NotADirectoryError(f"Download folder is not a directory, and couldn't be created: `{DOWNLOAD_FOLDER.resolve()}`") from e
prefs = {"download.default_directory": str(DOWNLOAD_FOLDER.resolve())}

runtimeConfigPath = Path("config.json5")
if not runtimeConfigPath.is_file():
    raise FileNotFoundError("config.json5 file not found. Please create one -- see the repository for examples.")
runtimeConfig:dict[str, Any] = pyjson5.loads(runtimeConfigPath.read_text("utf-8"))
if not isinstance(runtimeConfig, dict):
    raise TypeError("config.json5 file is not a valid JSON object.")

VALID_TAKEOUT_DL_URLS:Final[Collection[str]] = runtimeConfig["takeoutDownloadPageURLFragments"]

OptionsType = TypeVar("OptionsType", bound=webdriver.ChromeOptions | webdriver.EdgeOptions)
def initOptions(_options:OptionsType) -> OptionsType:
    """Common options initialization for Chrome and Edge"""
    if prefs:
        # If we were provided a download folder, set it,
        # otherwise leave it to the browser default
        _options.add_experimental_option("prefs", prefs)
    for _arg in standardOptionsArgs:
        _options.add_argument(_arg)
    return _options
## End setup common browser options ##


# Initialize the WebDriver based on the selected browser type
match BROWSER_TYPE:
    case "edge":
        options = webdriver.EdgeOptions()
        service = EdgeService(WEBDRIVER_PATH.resolve().as_posix())
        driver = webdriver.Edge(service= service, options= initOptions(options))
    case "chrome":
        options = webdriver.ChromeOptions()
        service = ChromeService(WEBDRIVER_PATH.resolve().as_posix())
        driver = webdriver.Chrome(service= service, options= initOptions(options))
    case _:
        raise ValueError(f"Unsupported browser type `{BROWSER_TYPE}`. Please use 'edge' or 'chrome'.")

RETRY_HOURS:Final[int] = int(runtimeConfig["waitForUserInputHours"]) * 60
RETRY_DOWNLOAD_MINUTES:Final[float] = float(runtimeConfig.get("retryDownloadTimeoutMinutes", 30))
TAKEOUT_SELECTOR:Final[str] = runtimeConfig.get("downloadButtonCSSSelector", "i.material-icons-extended + span + a")
INCOMPLETE_DOWNLOAD_SUFFIX:Final[str] = ".crdownload"

def isOnTakeoutPage() -> bool:
    for url in VALID_TAKEOUT_DL_URLS:
        if url in driver.current_url:
            return True
    return False

def hasIncompleteDownloads(download_folder:PathLike) -> bool:
    _downloads = Path(download_folder)
    if not _downloads.is_dir():
        raise NotADirectoryError(f"Download folder is not a directory: `{_downloads.resolve()}`")
    return any(filename.name.endswith(INCOMPLETE_DOWNLOAD_SUFFIX) for filename in _downloads.iterdir())

def wait_for_downloads(download_folder:PathLike):
    elapsed = 0
    _retrySeconds = RETRY_DOWNLOAD_MINUTES * 60
    while hasIncompleteDownloads(download_folder):
        time.sleep(1)
        elapsed += 1
        if elapsed >= _retrySeconds:
            raise TimeoutError(f"Download did not complete within {RETRY_DOWNLOAD_MINUTES} minutes.")

def get_downloaded_serials(download_folder:PathLike) -> Set[str]:
    serials:Set[str] = set()
    _downloads = Path(download_folder)
    if not _downloads.is_dir():
        raise NotADirectoryError(f"Download folder is not a directory: `{_downloads.resolve()}`")
    for filename in _downloads.iterdir():
        match = re.search(r"takeout-\d{8}T\d{6}Z-(?:\d-)?(\d{3}|[\da-e\-]+)\.zip", filename.name)
        if match:
            serials.add(match.group(1))
    return serials

def wait_for_reauthentication():
    sleepDuration = 60 # seconds
    minuteMultiplier = 60 / sleepDuration
    _retries = int(RETRY_HOURS * 60 * minuteMultiplier)
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
        print(f"Reauthentication required. Please log in again. Attempt {attempt + 1} of {_retries}.")
        time.sleep(sleepDuration)
        if isOnTakeoutPage():
            return True
    return False

def wait_for_stale_element_retry():
    sleepDuration = 5 # seconds
    minuteMultiplier = 60 / sleepDuration
    _retries = int(3 * minuteMultiplier)
    for attempt in range(_retries):
        print(f"Stale element reference exception caught. Retrying... Attempt {attempt + 1} of {_retries}.")
        time.sleep(sleepDuration)
        if isOnTakeoutPage():
            return True
        print("Invalid URL:", driver.current_url)
    return False

# Function to download files
def download_files(_downloaded_serials) -> None:
    # Locate all download elements with the download icon using XPath
    download_elements = driver.find_elements(By.CSS_SELECTOR, TAKEOUT_SELECTOR)
    print(f"Found {len(download_elements)} files to download.")

    if not download_elements:
        return

    SKIP_FILE = Path(__file__).parent / "SKIPPED_DOWNLOADS.txt"
    _ok = True
    for i, element in enumerate(download_elements):
        _retryCount = 0
        while True:
            if not _ok:
                # use alternate re-crawl method
                element = driver.find_elements(By.CSS_SELECTOR, TAKEOUT_SELECTOR)[i]
            try:
                # Get the parent element which contains the download link
                parent_element = element.find_element(By.XPATH, "..")
                download_link = parent_element.find_element(By.CSS_SELECTOR, "a[href*='takeout/download']")
                download_url = download_link.get_attribute("href")
                if not download_url:
                    print("No download URL found, skipping...")
                    break

                # Get the serial from the download URL (if applicable)
                # TODO append the J to the download file as a serial match
                serial_match = re.search(r"i=(\d+)", download_url)
                if not serial_match:
                    serial_match = re.search(r"j=([\da-e\-]+)", download_url)
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
                try:
                    wait_for_downloads(DOWNLOAD_FOLDER)
                except TimeoutError as e:
                    print(e)
                    # Remove the incomplete download file if it exists
                    for _incomplete in DOWNLOAD_FOLDER.glob(f"*{INCOMPLETE_DOWNLOAD_SUFFIX}"):
                        print(f"\tRemoving incomplete download: {_incomplete.name}")
                        _incomplete.unlink()
                    time.sleep(2)  # Wait a bit before retrying
                    _ok = False
                    _retryCount += 1
                    if _retryCount >= 5:
                        print("Maximum retry attempts reached. Skipping this file.")
                        if serial:
                            _skipped = []
                            if SKIP_FILE.is_file():
                                _skipped = SKIP_FILE.read_text("utf-8").splitlines()
                            _skipped.append(serial)
                            SKIP_FILE.write_text("\n".join(_skipped), encoding="utf-8")
                        break
                    print("Retrying download...")
                    continue

                # Update the downloaded serials set
                if serial:
                    downloaded_serials.add(serial)
                    # TODO rename downloaded file
                    # if it doesn't have a serial
                    # on the name

            except selenium.common.exceptions.StaleElementReferenceException as e: # type: ignore
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
    return

if __name__ == "__main__":
    def isTruthy(resp) -> bool:
        return str(resp).lower().strip() in ["t", "true", "yes", "y", "1"]
    # Find duplicate downloads, eg, big images that downloaded directly
    # but couldn't be serial checked
    files = list(DOWNLOAD_FOLDER.glob("* (*).*"))
    if files:
        if isTruthy(input(f"Remove duplicate files? \n{files}\n(y/n): ")):
            for duplicate in files:
                duplicate.unlink()
    if hasIncompleteDownloads(DOWNLOAD_FOLDER):
        # If we aborted for some reason, we may have dangling incomplete downloads
        # which means the download complete check will never succeed
        print("Cleaning up incomplete downloads...")
        for _incomplete in DOWNLOAD_FOLDER.glob(f"*{INCOMPLETE_DOWNLOAD_SUFFIX}"):
            print(f"\tRemoving incomplete download: {_incomplete.name}")
            _incomplete.unlink()
    # Get already downloaded serials
    downloaded_serials = get_downloaded_serials(DOWNLOAD_FOLDER)
    if downloaded_serials:
        print("Already got", downloaded_serials)
        serialInts = set([int(s) for s in downloaded_serials if s.isdigit()])
        maxSerial = max(serialInts)
        if len(missing := serialInts.symmetric_difference(set(range(1, maxSerial)))) != 0:
            print(f"Warning: There are gaps in the downloaded serials: {missing}. If you don't assume intermediates are skipped, they will be re-downloaded.")
        if isTruthy(input("Assume all intermediate files are downloaded? (y/n): ")):
            # If we are resuming a download, assume all intermediate files are downloaded
            # This is not always true, but it's better than re-downloading everything
            # if the user is sure they have them all
            for s in range(1, maxSerial):
                downloaded_serials.add(str(s).zfill(3))
            print("Assuming all serials up to", str(maxSerial).zfill(3), "are downloaded.")
    else:
        print("Fresh download")
    print("Navigating to Google Takeout downloads page...")
    try:
        # Open the Google Takeout downloads page
        driver.get("https://takeout.google.com/settings/takeout/downloads")
        input("\n\nLog in to your Google account & choose the takeout export to download. Then press Enter to continue...\n\n")


        # Download files
        download_files(downloaded_serials)

        print("Downloads finished. Check your download folder.")

    finally:
        # Find duplicate downloads, eg, big images that downloaded directly
        # but couldn't be serial checked
        for duplicate in DOWNLOAD_FOLDER.glob("* (*).*"):
            duplicate.unlink()
        driver.quit()
