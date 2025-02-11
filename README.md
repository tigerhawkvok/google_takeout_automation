# Google Takeout Automation

This project automates the process of downloading, extracting, and organizing Google Takeout data using Selenium and Python. It supports multiple browsers (Edge and Chrome) and allows users to configure the process through environment variables.

## Features

- Automates the download of Google Takeout data.
- Extracts the downloaded ZIP files.
- Converts JSON metadata to EXIF data for images.
- Organizes the extracted contents into a specified directory.

## Prerequisites

- Python 3.x
- WebDriver for your browser (Edge or Chrome)
- [ExifTool](https://exiftool.org/) for metadata conversion

## Installation

1. Clone the repository:
    ```bash
    git clone https://github.com/yourusername/google-takeout-automation.git
    cd google-takeout-automation
    ```

2. Create and activate a virtual environment:
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
    ```

3. Install the required dependencies:
    ```bash
    pip install -r requirements.txt
    ```

4. Copy the `.env.example` file to `.env` and update the variables as needed:
    ```bash
    cp .env.example .env
    ```

## Configuration

Edit the `.env` file to configure the paths and options for the scripts:

```dotenv
# WebDriver configuration
WEBDRIVER_PATH=path/to/your/webdriver
DOWNLOAD_FOLDER=/path/to/your/download/folder
BROWSER_TYPE=edge  # Change to 'chrome' for using Chrome browser

# Move and extract Takeout configuration
DOWNLOADS_DIR=/path/to/your/download/folder
DESTINATION_DIR=/path/to/your/destination/folder
RUN_EXTRACTION=yes
RUN_METADATA_CONVERSION=yes
RUN_ORGANIZATION=yes
```

## Usage

### Download Google Takeout Data

1. Run the `download_takeout_edge.py` script to start the download process:
    ```bash
    python download_takeout_edge.py
    ```

2. Follow the prompts to log in to your Google account and select the Takeout export to download.

### Extract and Organize Takeout Data

1. Run the `move_and_extract_takeout.py` script to extract and organize the downloaded data:
    ```bash
    python move_and_extract_takeout.py
    ```

2. The script will prompt you to run specific stages (extraction, metadata conversion, organization). You can configure these stages in the `.env` file.

## License

This project is licensed under the MIT License. See the [LICENSE](./LICENSE) file for details.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.

## Acknowledgements

- [Selenium](https://www.selenium.dev/)
- [ExifTool](https://exiftool.org/)
- [dotenv](https://github.com/theskumar/python-dotenv)