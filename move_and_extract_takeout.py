# Copyright (c) 2025 Karthick Ramakrishnan
# This file is part of Google Takeout Automation and is licensed under the MIT License.
# See the LICENSE file in the project root for more information.import os
import shutil
import zipfile
import json
import subprocess
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Source and destination directories
DOWNLOADS_DIR = os.getenv("DOWNLOADS_DIR", os.path.expanduser("~/Downloads"))
DESTINATION_DIR = os.getenv("DESTINATION_DIR")
EXTRACTION_DIR = os.path.join(DESTINATION_DIR, "contents")

# Ensure destination and extraction directories exist
os.makedirs(DESTINATION_DIR, exist_ok=True)
os.makedirs(EXTRACTION_DIR, exist_ok=True)

# Function to identify Takeout files
def get_takeout_files(directory, subset_size=None):
    takeout_files = sorted(
        [os.path.join(directory, f) for f in os.listdir(directory) if f.startswith("takeout-") and f.endswith(".zip")]
    )
    if subset_size:
        return takeout_files[:subset_size]  # For testing with a subset
    return takeout_files

# Function to extract files
def extract_takeout_files(takeout_files, extraction_dir):
    for file_path in takeout_files:
        try:
            # Extract the contents to the extraction folder
            file_name = os.path.basename(file_path)
            print(f"Extracting {file_name} to {extraction_dir}...")
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(extraction_dir)
        except Exception as e:
            print(f"Error processing {file_path}: {e}")

# Function to convert JSON metadata to EXIF data
def convert_metadata_to_exif(extraction_dir):
    for root, dirs, files in os.walk(extraction_dir):
        for file_name in files:
            if file_name.endswith(".json"):
                json_path = os.path.join(root, file_name)
                image_path = os.path.join(root, file_name.replace(".json", ""))
                if os.path.exists(image_path):
                    try:
                        with open(json_path, 'r', errors='ignore') as json_file:
                            metadata = json.load(json_file)
                            if 'photoTakenTime' in metadata:
                                date_time = metadata['photoTakenTime']['formatted']
                                try:
                                    exif_date_time = date_time.replace('-', ':').replace('T', ' ')
                                    subprocess.run(["exiftool", f"-DateTimeOriginal={exif_date_time}", image_path])
                                except ValueError:
                                    print(f"Invalid date format in {json_path}: {date_time}")
                            if 'title' in metadata:
                                title = metadata['title']
                                subprocess.run(["exiftool", f"-XPTitle={title}", image_path])
                            if 'album' in metadata:
                                album = metadata['album']
                                subprocess.run(["exiftool", f"-XPComment={album}", image_path])
                    except json.JSONDecodeError as e:
                        print(f"Error decoding JSON in {json_path}: {e}")

# Function to organize extracted contents
def organize_extracted_contents(extraction_dir, destination_dir):
    takeout_dir = os.path.join(extraction_dir, "Takeout", "Google Photos")
    if not os.path.exists(takeout_dir):
        print(f"Takeout directory not found: {takeout_dir}")
        return

    for root, dirs, files in os.walk(takeout_dir):
        for dir_name in dirs:
            src_dir = os.path.join(root, dir_name)
            dest_dir = os.path.join(destination_dir, dir_name)
            if not os.path.exists(dest_dir):
                os.makedirs(dest_dir)
            for file_name in os.listdir(src_dir):
                src_file = os.path.join(src_dir, file_name)
                dest_file = os.path.join(dest_dir, file_name)
                print(f"Moving {src_file} to {dest_file}...")
                shutil.move(src_file, dest_file)

    # Move metadata files
    metadata_files = ["print-subscriptions.json", "shared_album_comments.json", "user-generated-memory-titles.json"]
    for metadata_file in metadata_files:
        src_file = os.path.join(extraction_dir, metadata_file)
        if os.path.exists(src_file):
            dest_file = os.path.join(destination_dir, metadata_file)
            print(f"Moving {src_file} to {dest_file}...")
            shutil.move(src_file, dest_file)

# Main function
def main():
    print("Scanning for Takeout files in the Downloads folder...")
    takeout_files = get_takeout_files(DESTINATION_DIR)

    if not takeout_files:
        print("No Takeout files found.")
        return

    print(f"Found {len(takeout_files)} Takeout files.")

    # Get user input for stages to run
    run_extraction = os.getenv("RUN_EXTRACTION", "yes").strip().lower() == "yes"
    run_metadata_conversion = os.getenv("RUN_METADATA_CONVERSION", "yes").strip().lower() == "yes"
    run_organization = os.getenv("RUN_ORGANIZATION", "yes").strip().lower() == "yes"

    if run_extraction:
        extract_takeout_files(takeout_files, EXTRACTION_DIR)
    if run_metadata_conversion:
        convert_metadata_to_exif(EXTRACTION_DIR)
    if run_organization:
        organize_extracted_contents(EXTRACTION_DIR, DESTINATION_DIR)

    print("Selected stages have been completed successfully.")

# Entry point
if __name__ == "__main__":
    main()
