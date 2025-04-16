import json
import requests
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
class Checker:
    def __init__(self, domains_api, config_file='.config', timeout=30, sms=False):

        self.CONFIG_FILE = config_file
        self.DOMAINS_API = str(domains_api)
        self.TIMEOUT = timeout  # timeout in seconds
        self.ERROR_STS = False
        self.SMS = sms
        self.ignore_domains = ["example.com", "example.org"]
        self.FROM_PHONE = os.getenv("MELIPAYAMAK_PHONE")

        # this list save all data after and befor checking to show
        self.print_data = {"intro": [], "unavailable": [], "accessible_again": [], "conclusion": []}

        # load data
        self.config = self.load_config()
        self.domains = self.load_domains()

    def load_config(self):
        # load config from .config file
        try:
            with open(self.CONFIG_FILE, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            # create default config if file not found
            self.ERROR_STS = True
            default_config = {
                "phone_numbers": [],
                "unavailable_domains": []
            }
            self.save_config(default_config)
            return default_config
        except json.JSONDecodeError:
            self.ERROR_STS = True
            return False

    def save_config(self, config):
        if not self.ERROR_STS:
            # save config to .config file
            with open(self.CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=4)
        return

    def load_domains(self):
        # load domains from  api
        try:
            res = requests.get(self.DOMAINS_API)
            res = [d for d in list(res.json()) if d not in self.ignore_domains]
            if len(res) == 0:
                return False
            return list(res)
        except:
            self.ERROR_STS = True
            return False

    def send_SMS(self, messege):
        try:
            self.config = self.load_config()
            if str(messege).strip() != "" and messege != False and self.config != False:
                print(str(messege))
                # send SMS for all phone numbers in config file
                for phone in self.config["phone_numbers"]:
                    # send SMS
                    api_url = os.getenv("MELIPAYAMAK_API")

                    ## headers
                    headers = {
                        "Content-Type": "application/json"
                    }

                    ## sms data
                    payload = {
                        "from": str(self.FROM_PHONE),
                        "to": str(phone),
                        "text": str(messege)
                    }

                    ## send post request to send sms
                    response = requests.post(api_url, json=payload, headers=headers)

                    ## print response
                    print("\n")
                    print(response.status_code)
                    print(response.text)
            else:
                print("NULL")
        except:
            return False

    def check_domain(self, domain):
        if not self.ERROR_STS:
            # check domains
            for i in range(3):
                try:
                    # add http:// to domain if it doesn't start with http:// or https://
                    if not domain.startswith(('http://', 'https://')):
                        domain = 'http://' + domain

                    response = requests.get(
                        domain,
                        timeout=self.TIMEOUT,
                        allow_redirects=True,
                        headers={'User-Agent': 'Mozilla/5.0'}
                    )

                    if response.status_code < 400:
                        return True
                except:
                    continue

            return False

        return False

    async def run(self):
        if not self.ERROR_STS:
            self.print_data = {"intro": [], "unavailable": [], "accessible_again": [], "conclusion": []}

            # check all domains
            try:
                if not self.domains or not self.config:
                    return False

                changes_made = False

                # check all domains
                for domain in self.domains:
                    is_accessible = self.check_domain(domain)

                    # if domain is accessible
                    if is_accessible:
                        # if domain was previously unavailable but now is accessible
                        if domain in self.config['unavailable_domains']:
                            self.config['unavailable_domains'].remove(domain)
                            self.print_data["accessible_again"].append(str(domain).rsplit(".", 1)[0])
                            changes_made = True

                    # if domain is not accessible
                    else:
                        # add domain to unavailable list if it's not already there
                        if domain not in self.config['unavailable_domains']:
                            self.config['unavailable_domains'].append(domain)
                            self.print_data["unavailable"].append(str(domain).rsplit(".", 1)[0])
                            changes_made = True

                # save config if changes were made
                if changes_made:
                    self.save_config(self.config)

                    # summary of checking
                    self.config = self.load_config()
                    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    self.print_data["intro"].append(f"start checking domains at {current_time}")
                    self.print_data["intro"].append("-----------")
                    self.print_data["conclusion"].append("-----------")
                    self.print_data["conclusion"].append(f"number of domains: {len(self.domains)}")
                    self.print_data["conclusion"].append(
                        f"number of unavailable {len(self.config['unavailable_domains'])}")

                    if len(self.print_data["unavailable"]) > 0:
                        self.print_data["unavailable"].insert(0, "unavailable domains :")
                    if len(self.print_data["accessible_again"]) > 0:
                        self.print_data["accessible_again"].insert(0, "accessible again domains :")


            except Exception as e:
                # self.print_data.append(f"An error occurred while executing the script : {e}")
                return False

            # send sms if sms is True
            if self.SMS:
                msg = self.print_data["intro"] + self.print_data["unavailable"] + self.print_data["accessible_again"] + \
                      self.print_data["conclusion"]
                msg = str("\n".join(msg))
                self.send_SMS(msg)

            return self.print_data
        return False