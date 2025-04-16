# Domain Status Checker

## Overview
Domain Status Checker is a Python-based tool that automates the process of checking the availability of domains retrieved from an API. It identifies unreachable domains and sends SMS notifications to the admin's phone. The tool also maintains a record of domain statuses for future reference.

## Features
- Fetches a list of domains from a JSON API.
- Checks the availability of each domain (HTTP status code < 400).
- Logs unreachable domains (HTTP status code >= 400).
- Sends SMS notifications to the admin for unreachable domains.
- Periodically runs the checks and updates the status records.

## Requirements
- Python 3.8 or higher
- `requests` library
- `asyncio` library
- Access to an SMS API (e.g., Melipayamak)

## Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/domain-status-checker.git
   cd domain-status-checker
   ```
   
2. Install the required packages:
   ```bash
   
    pip install -r requirements.txt
    ```
3. Configure the .config file:
    Add the admin's phone number under phone_numbers.
    Leave unavailable_domains empty (it will be updated automatically).
    Update the DOMAINS_API variable in run.py with the API endpoint that provides the list of domains.

4. Run the script:
    python run.py

5. The script will:
   Fetch the list of domains from the API.
   Check the availability of each domain.
   Log unreachable domains in the .config file.
   Send SMS notifications for unreachable domains.
   Configuration
   The .config file is used to store:
       Admin phone numbers for SMS notifications.
       A list of domains that are currently unreachable.

Project Structure
main.py: Contains the Checker class, which handles domain checking, configuration management, and SMS notifications.
run.py: The entry point of the application. It initializes the Checker class and runs the periodic checks.
.config: A JSON file used to store admin phone numbers and unreachable domains.
License
This project is licensed under the MIT License. See the LICENSE file for details.


Contributing
Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.


Contact
For any questions or issues, please contact the repository owner.