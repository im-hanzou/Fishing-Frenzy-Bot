import requests
import random
import string
import time
from datetime import datetime, timezone
import logging
import uuid
import json
import os
import urllib3
from colorama import init, Fore, Style

init(autoreset=True)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(level=logging.INFO, format=f'{Fore.CYAN}%(asctime)s{Style.RESET_ALL} - {Fore.YELLOW}%(levelname)s{Style.RESET_ALL} - %(message)s')

API_URL = "https://fishing-frenzy-api-0c12a800fbfe.herokuapp.com"
PRIVY_APP_ID = "cm3zblyae03ldeetu6qx3r1y2"
PRIVY_CA_ID = "client-WY5dfCTVUisABzyMUeGt8yFwLnYqXdFKBTiXFXtmmJQt3"

OUTPUT_FOLDER = "FishF-accounts"
OUTPUT_FILE = "accounts.json"
PROXIES_FILE = "proxies.txt"

def load_proxies():
    try:
        with open(PROXIES_FILE, 'r') as file:
            proxies = []
            for line in file:
                proxy = line.strip()
                if proxy:
                    if not proxy.startswith('http://'):
                        proxy = f'http://{proxy}'
                    proxies.append(proxy)
        return proxies
    except FileNotFoundError:
        logging.error(f"{Fore.RED}Proxies file not found.{Style.RESET_ALL}")
        return []

def get_random_proxy(proxy_list):
    if not proxy_list:
        logging.warning(f"{Fore.YELLOW}No proxies available. Will proceed without proxy.{Style.RESET_ALL}")
        return None
    
    random.shuffle(proxy_list)
    
    for proxy in proxy_list:
        try:
            proxies = {
                "http": proxy,
                "https": proxy
            }
            
            response = requests.get(
                "http://httpbin.org/ip", 
                proxies=proxies, 
                timeout=5
            )
            
            if response.status_code == 200:
                logging.info(f"{Fore.GREEN}Valid proxy found: {proxy}{Style.RESET_ALL}")
                return proxies
        except Exception as e:
            logging.warning(f"{Fore.YELLOW}Proxy {proxy} failed: {str(e)}{Style.RESET_ALL}")
    
    logging.error(f"{Fore.RED}No valid proxies found!{Style.RESET_ALL}")
    return None
    
def generate_device_id():
    return str(uuid.uuid4())

def generate_random_username():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))

def guest_login(device_id, proxies=None):
    url = f"{API_URL}/v1/auth/guest-login"
    headers = {"Content-Type": "application/json"}
    data = {"deviceId": device_id, "teleUserId": None, "teleName": None}
    try:
        response = requests.post(
            url, 
            json=data, 
            headers=headers, 
            proxies=proxies, 
            timeout=10,
            verify=False
        )
        response.raise_for_status()
        json_response = response.json()
        token = json_response["tokens"]["access"]["token"]
        user_id = json_response["user"]["id"]
        logging.info(f"{Fore.GREEN}Access Token and User ID obtained for Device ID: {device_id}{Style.RESET_ALL}")
        return token, user_id
    except requests.exceptions.RequestException as e:
        logging.error(f"{Fore.RED}Error during guest login: {e}{Style.RESET_ALL}")
        return None, None

def verify_reference_code(access_token, username, koderef, proxies=None):
    url = f"{API_URL}/v1/reference-code/verify?code={koderef}"
    headers = {
        "Authorization": f"Bearer {access_token}", 
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(
            url, 
            json={}, 
            headers=headers, 
            proxies=proxies, 
            timeout=10,
            verify=False
        )
        if response.status_code == 200:
            logging.info(f"{Fore.GREEN}Code {koderef} verified successfully for user {username}.{Style.RESET_ALL}")
            return True
        else:
            logging.warning(f"{Fore.YELLOW}Verification failed for user {username}. Status: {response.status_code}{Style.RESET_ALL}")
            return False
    except requests.exceptions.RequestException as e:
        logging.error(f"{Fore.RED}Error verifying user {username}: {e}{Style.RESET_ALL}")
        return False

def log_analytics_event(access_token, event_name, proxies=None):
    url = "https://auth.privy.io/api/v1/analytics_events"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Privy-Client": "react-auth:1.88.4",
        "Privy-App-Id": PRIVY_APP_ID,
        "Privy-Ca-Id": PRIVY_CA_ID,
        "Origin": "https://fishingfrenzy.co",
    }
    data = {
        "event_name": event_name,
        "client_id": PRIVY_CA_ID,
        "payload": {
            "embeddedWallets": {
                "createOnLogin": "all-users",
                "noPromptOnSignature": True,
                "waitForTransactionConfirmation": True,
                "priceDisplay": {"primary": "native-token", "secondary": None},
            },
            "supportedChains": [1, 8453],
            "defaultChain": 8453,
            "clientTimestamp": datetime.now(timezone.utc).isoformat(),
        },
    }
    try:
        response = requests.post(
            url, 
            json=data, 
            headers=headers, 
            proxies=proxies, 
            timeout=10
        )
        response.raise_for_status()
        logging.info(f"{Fore.GREEN}Event '{event_name}' logged successfully.{Style.RESET_ALL}")
    except requests.exceptions.RequestException as e:
        logging.error(f"{Fore.RED}Error logging event: {e}{Style.RESET_ALL}")

def save_user_data_to_file(token, user_id):
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    file_path = os.path.join(OUTPUT_FOLDER, OUTPUT_FILE)

    user_data = []
    if os.path.exists(file_path):
        with open(file_path, "r") as file:
            try:
                user_data = json.load(file)
            except json.JSONDecodeError:
                logging.warning(f"{Fore.YELLOW}{OUTPUT_FILE} is empty or invalid. Overwriting file.{Style.RESET_ALL}")

    user_data.append({"access_token": f"Bearer {token}", "user_id": user_id})

    with open(file_path, "w") as file:
        json.dump(user_data, file, indent=4)
    logging.info(f"{Fore.GREEN}User data saved to {file_path}{Style.RESET_ALL}")

def automate_user_creation(num_users, koderef):
    proxy_list = load_proxies()
    
    for i in range(num_users):
        current_proxies = get_random_proxy(proxy_list)
        
        device_id = generate_device_id()
        username = generate_random_username()
        logging.info(f"{Fore.BLUE}Creating user {i + 1}: {username} with Device ID: {device_id}{Style.RESET_ALL}")
        
        access_token, user_id = guest_login(device_id, current_proxies)
        if access_token and user_id:
            save_user_data_to_file(access_token, user_id)
            if verify_reference_code(access_token, username, koderef, current_proxies):
                log_analytics_event(access_token, "sdk_initialize", current_proxies)
        time.sleep(random.uniform(1, 3))

if __name__ == "__main__":
    try:
        print(f"{Fore.MAGENTA}<== Fishing Frenzy Autoreferral ==>{Style.RESET_ALL}")
        num_users_to_create = int(input(f"{Fore.CYAN}Enter the number of users to create: {Style.RESET_ALL}"))
        koderef = input(f"{Fore.CYAN}Enter the reference code: {Style.RESET_ALL}")
        automate_user_creation(num_users_to_create, koderef)
    except ValueError:
        logging.error(f"{Fore.RED}Invalid input. Please enter a valid number.{Style.RESET_ALL}")
    except Exception as e:
        logging.error(f"{Fore.RED}An error occurred: {e}{Style.RESET_ALL}")
