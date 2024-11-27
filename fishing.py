import json
import requests
import websockets
import asyncio 
import random
import time
from datetime import datetime
import os
import urllib.parse
import logging
import uuid
from websocket import create_connection
import ssl
import colorama
from colorama import Fore, Back, Style
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import threading
import traceback
import gzip
from urllib.parse import urlparse

# Initialize colorama
colorama.init(autoreset=True)

class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors"""
    
    COLORS = {
        'DEBUG': Fore.BLUE,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Back.WHITE
    }

    def format(self, record):
        if record.levelname in self.COLORS:
            record.levelname = f"{self.COLORS[record.levelname]}{record.levelname}{Style.RESET_ALL}"
        
        if hasattr(record, 'msg'):
            if "Successfully" in str(record.msg):
                record.msg = f"{Fore.GREEN}{record.msg}{Style.RESET_ALL}"
            elif "Failed" in str(record.msg) or "Error" in str(record.msg):
                record.msg = f"{Fore.RED}{record.msg}{Style.RESET_ALL}"
            elif "Starting" in str(record.msg):
                record.msg = f"{Fore.CYAN}{record.msg}{Style.RESET_ALL}"
            elif "Completing" in str(record.msg):
                record.msg = f"{Fore.YELLOW}{record.msg}{Style.RESET_ALL}"
            
        return super().format(record)

class ThreadSafeLogger:
    def __init__(self):
        self.loggers = {}
        self.lock = Lock()
        
    def get_logger(self, username, account_index):
        logger_key = f"{username}_{account_index}"
        
        with self.lock:
            if logger_key not in self.loggers:
                formatter = ColoredFormatter(
                    fmt=f'[%(asctime)s - {Fore.CYAN}%(username)s{Style.RESET_ALL} - account %(account_index)s] %(levelname)s: %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                )

                logger = logging.getLogger(f"{__name__}.{logger_key}")
                logger.setLevel(logging.INFO)
                
                logger.handlers.clear()
                
                file_handler = logging.FileHandler('bot.log', encoding='utf-8')
                file_handler.setFormatter(formatter)
                
                console_handler = logging.StreamHandler()
                console_handler.setFormatter(formatter)
                
                logger.addHandler(file_handler)
                logger.addHandler(console_handler)
                
                logger_adapter = logging.LoggerAdapter(
                    logger,
                    {'username': username, 'account_index': account_index}
                )
                
                self.loggers[logger_key] = logger_adapter
                
            return self.loggers[logger_key]

class ProxyManager:
    def __init__(self, logger=None):
        self.proxy_file = 'proxy.txt'
        self.proxies = []
        self.current_index = 0
        self.lock = Lock()
        self.logger = logger
        self.load_proxies()

    def load_proxies(self):
        if not os.path.exists(self.proxy_file):
            if self.logger:
                self.logger.info(f"{Fore.YELLOW}No proxy file found, will run without proxies{Style.RESET_ALL}")
            return

        try:
            with open(self.proxy_file, 'r') as f:
                proxies = [line.strip() for line in f if line.strip()]
                self.proxies = [self.format_proxy(proxy) for proxy in proxies]
                if self.logger:
                    self.logger.info(f"{Fore.GREEN}Loaded {len(self.proxies)} proxies{Style.RESET_ALL}")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error loading proxies: {str(e)}")

    def format_proxy(self, proxy):
        if not proxy.startswith(('http://', 'https://')):
            return f'http://{proxy}'
        return proxy

    def get_next_proxy(self):
        if not self.proxies:
            return None
            
        with self.lock:
            proxy = self.proxies[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxies)
            return proxy

    def verify_proxy(self, proxy):
        try:
            response = requests.get('https://ipinfo.io/json', 
                                 proxies={'http': proxy, 'https': proxy},
                                 timeout=10)
            if response.status_code == 200:
                ip_info = response.json()
                if self.logger:
                    self.logger.info(f"{Fore.GREEN}Proxy verified: {ip_info.get('ip')} ({ip_info.get('country')}){Style.RESET_ALL}")
                return True
            return False
        except Exception as e:
            if self.logger:
                self.logger.error(f"Proxy verification failed: {proxy} - {str(e)}")
            return False

    def get_working_proxy(self):
        if not self.proxies:
            return None
            
        attempts = 0
        max_attempts = len(self.proxies)
        
        while attempts < max_attempts:
            proxy = self.get_next_proxy()
            if self.verify_proxy(proxy):
                return proxy
            attempts += 1
            
        if self.logger:
            self.logger.warning(f"{Fore.YELLOW}No working proxies found{Style.RESET_ALL}")
        return None

class Headers:
    @staticmethod
    def get_standard_headers(token):
        return {
            "accept": "application/json",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "en-US,en;q=0.9",
            "authorization": f"Bearer {token}",
            "cache-control": "no-cache",
            "connection": "keep-alive",
            "content-type": "application/json",
            "host": "fishing-frenzy-api-0c12a800fbfe.herokuapp.com",
            "origin": "https://fishingfrenzy.co",
            "pragma": "no-cache",
            "referer": "https://fishingfrenzy.co/",
            "sec-ch-ua": '"Chromium";v="131", "Microsoft Edge";v="131", "Not?A_Brand";v="99", "Microsoft Edge WebView2";v="131"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
        }

    @staticmethod
    def get_websocket_headers():
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
            "Origin": "https://fishingfrenzy.co",
            "Sec-WebSocket-Extensions": "permessage-deflate; client_max_window_bits",
            "Sec-WebSocket-Version": "13"
        }

class FishingGame:
    def __init__(self, token, logger, proxy=None):
        self.token = token
        self.base_ws_url = "wss://fishing-frenzy-api-0c12a800fbfe.herokuapp.com/?token="
        self.logger = logger
        self.proxy = proxy
        self.current_energy = 0
        self.reconnect_attempts = 3
        self.reconnect_delay = 5
        self.range_energy = {
            "short_range": 1,
            "mid_range": 2,
            "long_range": 3
        }
        # Rarity diambil dari quality
        self.rarity_mapping = {
            1: ("Common", Fore.WHITE),
            2: ("Rare", Fore.BLUE),
            3: ("Epic", Fore.MAGENTA),
            4: ("Legendary", Fore.YELLOW),
            5: ("Mythical", Fore.RED)
        }

    async def new_fishing_session(self, range_type="short_range"):
        required_energy = self.range_energy[range_type]
        retry_count = 0
        
        while retry_count < self.reconnect_attempts:
            try:
                ws_url = f"{self.base_ws_url}{self.token}"
                ws_options = {
                    "header": Headers.get_websocket_headers(),
                    "sslopt": {"cert_reqs": ssl.CERT_NONE}
                }
                
                if self.proxy:
                    proxy_host = self.proxy.split("://")[-1].split(":")[0]
                    proxy_port = int(self.proxy.split(":")[-1])
                    ws_options["http_proxy_host"] = proxy_host
                    ws_options["http_proxy_port"] = proxy_port
                    
                ws = create_connection(ws_url, **ws_options)

                try:
                    # Send prepare command
                    ws.send(json.dumps({"cmd": "prepare", "range": range_type}))
                    game_data = json.loads(ws.recv())
                    
                    if game_data.get("type") == "initGame":
                        fish_data = game_data['data']['randomFish']
                        user_data = game_data['data'].get('user', {})
                        
                        # Check for active bait
                        activated_items = game_data['data'].get('activatedItems', [])
                        has_bait = any('bait' in item.get('item', '').lower() for item in activated_items)
                        bait_info = " [Bait Active]" if has_bait else ""

                        # Get fish details
                        fish_name = fish_data['fishName']
                        exp_gain = fish_data['expGain']
                        
                        # Parse quality dan gunakan sebagai rarity
                        quality = 1
                        if quality_data := fish_data.get('quality'):
                            try:
                                if isinstance(quality_data, str):
                                    quality = int(quality_data.split("_")[-1]) if "_" in quality_data else int(''.join(filter(str.isdigit, quality_data)))
                                else:
                                    quality = int(quality_data)
                            except:
                                quality = 1

                        # Get rarity name and color based on quality
                        rarity_name, rarity_color = self.rarity_mapping.get(quality, ("Common", Fore.WHITE))
                        
                        # Add stars based on quality
                        quality_stars = "★" * quality
                        
                        # Create rarity display with color
                        rarity_display = f"{rarity_color}[{rarity_name}]{Style.RESET_ALL}"
                        
                        # Get fish parameters
                        speed = fish_data.get('speed', 150)
                        difficulty = fish_data.get('difficulty', 1)
                        fill_rate = fish_data.get('fillRate', 0.2)
                        drain_rate = fish_data.get('drainRate', 0.05)
                        
                        self.logger.info(
                            f"{Fore.CYAN}Started fishing for {fish_name} {quality_stars} {rarity_display} "
                            f"in {range_type}{bait_info} [Energy Cost: {required_energy}]{Style.RESET_ALL}"
                        )
                        
                        # Start fishing
                        ws.send(json.dumps({"cmd": "start"}))
                        
                        success_pattern = []
                        for frame in range(20):
                            # Calculate direction based on fish parameters
                            if frame < 7:  # Early game
                                dir_weights = [0.3, 0.4, 0.3]  # Left, Stay, Right
                            elif frame < 14:  # Mid game
                                dir_weights = [0.4, 0.2, 0.4]  # More movement
                            else:  # End game
                                dir_weights = [0.3, 0.4, 0.3]  # More stable
                                
                            direction = random.choices([-1, 0, 1], weights=dir_weights)[0]
                            success_pattern.append({"frame": frame, "dir": direction})
                            
                            # Wait for game state
                            await asyncio.sleep(0.2)
                            ws.recv()  # Receive game state
                        
                        # Send end command with actual fish parameters
                        fish_caught_data = {
                            "cmd": "end",
                            "rep": {
                                "fs": 100,
                                "ns": 200,
                                "fps": 20,
                                "frs": [[random.randint(100, 800), random.randint(100, 800)] for _ in range(90)]
                            },
                            "en": difficulty
                        }
                        
                        ws.send(json.dumps(fish_caught_data))
                        response = ws.recv()
                        game_over = json.loads(response)
                        
                        ws.close()
                        
                        success = game_over.get("success", False)
                        if success:
                            size_min = float(fish_data.get('sizeMin', 0))
                            size_max = float(fish_data.get('sizeMax', 1))
                            caught_size = round(random.uniform(size_min, size_max), 2)
                            
                            weight_unit = "kg" if caught_size >= 1 else "g"
                            display_weight = caught_size if caught_size >= 1 else caught_size * 1000
                            
                            self.logger.info(
                                f"{Fore.GREEN}Successfully caught {fish_name} {quality_stars} {rarity_display} "
                                f"[EXP +{exp_gain}] "
                                f"[{display_weight:.1f} {weight_unit}] "
                                f"[Energy Cost: {required_energy}]{Style.RESET_ALL}"
                            )
                        else:
                            self.logger.info(f"{Fore.RED}Failed to catch {fish_name} {rarity_display}{Style.RESET_ALL}")
                        return success
                    
                    ws.close()
                    return False
                    
                except json.JSONDecodeError as e:
                    self.logger.error(f"Error parsing game data: {str(e)}")
                    return False
                    
            except Exception as e:
                retry_count += 1
                if "Connection to remote host was lost" in str(e):
                    if retry_count < self.reconnect_attempts:
                        self.logger.warning(f"Connection lost, retrying in {self.reconnect_delay} seconds... ({retry_count}/{self.reconnect_attempts})")
                        await asyncio.sleep(self.reconnect_delay)
                        continue
                    else:
                        self.logger.error("Max reconnection attempts reached, stopping fishing")
                self.logger.error(f"Error in fishing session: {str(e)}")
                try:
                    ws.close()
                except:
                    pass
                return False

class FishingFrenzyBot:
    def __init__(self, config_path='config.json', token_path='token.json'):
        self.config_path = config_path
        self.token_path = token_path
        self.base_url = 'https://fishing-frenzy-api-0c12a800fbfe.herokuapp.com/v1'
        self.logger_manager = ThreadSafeLogger()
        self.config = self.load_config()
        self.tokens = self.load_tokens()
        self.proxy_manager = ProxyManager(logger=self.get_default_logger())
        self.thread_lock = Lock()
        self.account_counter = 0
        self.loggers = {}
        self.range_energy = {
            "short_range": 1,
            "mid_range": 2,
            "long_range": 3
        }

    def get_next_account_number(self):
        with self.thread_lock:
            self.account_counter += 1
            return self.account_counter

    def get_logger_for_thread(self, username, account_index):
        thread_id = threading.get_ident()
        logger_key = f"{username}_{account_index}_{thread_id}"
        
        if logger_key not in self.loggers:
            self.loggers[logger_key] = self.logger_manager.get_logger(username, account_index)
            
        return self.loggers[logger_key]

    def get_default_logger(self):
        return self.logger_manager.get_logger('BOT', 0)

    def get_user_info(self, token, proxy=None, logger=None):
        """
        Validate token by fetching user information
        Returns user data if successful, None if failed
        """
        try:
            response = self.make_request('GET', f'{self.base_url}/users/me', 
                                       token=token,
                                       proxy=proxy)
            if response.status_code == 200:
                user_data = response.json()
                if logger:
                    logger.info(f"{Fore.GREEN}Successfully retrieved user info{Style.RESET_ALL}")
                return user_data
            if logger:
                logger.error(f"Failed to get user info. Status code: {response.status_code}")
            return None
        except Exception as e:
            if logger:
                logger.error(f"Error getting user info: {str(e)}")
            return None
    def get_user_energy(self, token, proxy=None):
        try:
            response = self.make_request('GET', f'{self.base_url}/users/me', 
                                       token=token,
                                       proxy=proxy)
            if response.status_code == 200:
                data = response.json()
                return data.get('energy', 0)
            return 0
        except Exception as e:
            return 0

    def load_config(self):
        try:
            if not os.path.exists(self.config_path):
                default_config = {
                    "enable_ref_code": True,
                    "enable_tasks": True,
                    "enable_daily_claim": True,
                    "enable_auto_fishing": True,
                    "enable_tutorial": True,
                    "ref_code": "7RGW5V",
                    "fishing_energy_limit": 5,
                    "auto_fishing_ranges": ["short_range", "mid_range", "long_range"],
                    "retry_on_token_fail": True,
                    "retry_attempts": 3,
                    "delay_between_accounts": [2, 5],
                    "delay_between_fishing": [2, 4],
                    "max_threads": 3
                }
                with open(self.config_path, 'w') as f:
                    json.dump(default_config, f, indent=4)
                return default_config
            
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger = self.get_default_logger()
            logger.error(f"Error loading config: {str(e)}")
            return None

    def load_tokens(self):
        logger = self.get_default_logger()
        try:
            if not os.path.exists(self.token_path):
                with open(self.token_path, 'w') as f:
                    json.dump({}, f)
                return {}
            
            with open(self.token_path, 'r') as f:
                content = f.read().strip()
                if not content:
                    return {}
                return json.loads(content)
        except json.JSONDecodeError:
            logger.warning("Invalid token file, creating new one")
            with open(self.token_path, 'w') as f:
                json.dump({}, f)
            return {}
        except Exception as e:
            logger.error(f"Error loading tokens: {str(e)}")
            return {}

    def save_tokens(self):
        logger = self.get_default_logger()
        try:
            with open(self.token_path, 'w') as f:
                json.dump(self.tokens, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving tokens: {str(e)}")

    def make_request(self, method, url, token=None, proxy=None, **kwargs):
        if token:
            kwargs['headers'] = Headers.get_standard_headers(token)
            
        if proxy:
            kwargs['proxies'] = {
                'http': proxy,
                'https': proxy
            }
            
        try:
            response = requests.request(method, url, **kwargs)
            return response
        except requests.exceptions.RequestException as e:
            if proxy:
                kwargs.pop('proxies', None)
                return requests.request(method, url, **kwargs)
            raise

    def parse_query_file(self, query_path='query.txt'):
        logger = self.get_default_logger()
        try:
            if not os.path.exists(query_path):
                logger.error(f"Query file not found: {query_path}")
                return []
                
            accounts = []
            with open(query_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        parsed = urllib.parse.parse_qs(line.strip())
                        if 'user' not in parsed:
                            continue
                        user_data = json.loads(parsed['user'][0])
                        accounts.append({
                            'telegram_id': user_data['id'],
                            'username': user_data.get('username', ''),
                            'name': user_data.get('first_name', '')
                        })
                    except Exception as e:
                        logger.error(f"Error parsing line in query file: {str(e)}")
                        continue
            return accounts
        except Exception as e:
            logger.error(f"Error reading query file: {str(e)}")
            return []

    def guest_login(self, telegram_id, name, device_id, proxy=None, logger=None):
        try:
            payload = {
                "deviceId": device_id,
                "teleUserId": telegram_id,
                "teleName": name
            }
            
            response = self.make_request('POST', f'{self.base_url}/auth/guest-login', 
                                       json=payload, 
                                       proxy=proxy)
            if response.status_code == 200:
                data = response.json()
                if logger:
                    logger.info(f"{Fore.GREEN}Login successful!{Style.RESET_ALL}")
                return {
                    'token': data['tokens']['access']['token'],
                    'user_id': data['user']['id']
                }
            if logger:
                logger.error(f"Login failed with status code: {response.status_code}")
            return None
        except Exception as e:
            if logger:
                logger.error(f"Error during login: {str(e)}")
            return None

    def complete_tutorial(self, token, user_id, proxy=None, logger=None):
        try:
            response = self.make_request('POST', 
                f'{self.base_url}/users/{user_id}/complete-tutorial',
                token=token,
                proxy=proxy
            )
            if response.status_code == 200:
                if logger:
                    logger.info(f"{Fore.GREEN}Tutorial completed successfully{Style.RESET_ALL}")
                return True
            if logger:
                logger.error(f"Failed to complete tutorial. Status code: {response.status_code}")
            return False
        except Exception as e:
            if logger:
                logger.error(f"Error completing tutorial: {str(e)}")
            return False

    def verify_ref_code(self, token, ref_code, proxy=None, logger=None):
        try:
            response = self.make_request('POST',
                f'{self.base_url}/reference-code/verify',
                params={'code': ref_code},
                token=token,
                proxy=proxy
            )
            success = response.status_code == 200
            if success and logger:
                logger.info(f"{Fore.GREEN}Referral code verified successfully{Style.RESET_ALL}")
            elif logger:
                logger.error(f"Failed to verify referral code")
            return success
        except Exception as e:
            if logger:
                logger.error(f"Error verifying ref code: {str(e)}")
            return False

    def claim_daily_reward(self, token, proxy=None, logger=None):
        try:
            response = self.make_request('GET', 
                f'{self.base_url}/daily-rewards/claim', 
                token=token,
                proxy=proxy
            )
            success = response.status_code == 200
            if success and logger:
                logger.info(f"{Fore.GREEN}Daily reward claimed successfully{Style.RESET_ALL}")
            elif logger:
                logger.error(f"Failed to claim daily reward")
            return success
        except Exception as e:
            if logger:
                logger.error(f"Error claiming daily reward: {str(e)}")
            return False

    def complete_social_tasks(self, token, proxy=None, logger=None):
        try:
            response = self.make_request('GET', 
                f'{self.base_url}/social-quests',
                token=token,
                proxy=proxy
            )
            if response.status_code != 200:
                return False

            tasks = response.json()
            completed = 0
            
            for task in tasks:
                if task['status'] == 'UnClaimed' and task['type'] in ['Twitter', 'Telegram', 'Game']:
                    try:
                        verify_response = self.make_request('POST',
                            f'{self.base_url}/social-quests/{task["id"]}/verify',
                            token=token,
                            proxy=proxy
                        )
                        if verify_response.status_code == 200:
                            completed += 1
                            if logger:
                                logger.info(f"{Fore.GREEN}Completed task: {task['description']}{Style.RESET_ALL}")
                            time.sleep(random.uniform(1, 2))
                    except Exception as e:
                        if logger:
                            logger.error(f"Error completing task {task['id']}: {str(e)}")
                        continue

            return completed > 0
        except Exception as e:
            if logger:
                logger.error(f"Error in social tasks: {str(e)}")
            return False

    def get_user_gold(self, token, proxy=None):
        """Get current user gold"""
        try:
            response = self.make_request('GET', f'{self.base_url}/users/me', 
                                    token=token,
                                    proxy=proxy)
            if response.status_code == 200:
                data = response.json()
                return data.get('gold', 0)
            return 0
        except Exception as e:
            return 0

    async def sell_fish(self, token, fish_info_id, user_id, proxy=None, logger=None):
        """Sell fish using fishInfoId"""
        try:
            url = f'{self.base_url}/fish/sell'
            params = {
                'userId': user_id,
                'fishInfoId': fish_info_id
            }
            response = self.make_request('GET', url, token=token, proxy=proxy, params=params)
            if response.status_code == 200:
                if logger:
                    logger.info(f"{Fore.GREEN}Successfully sold fish{Style.RESET_ALL}")
                return True
            if logger:
                logger.error(f"Failed to sell fish. Status code: {response.status_code}")
            return False
        except Exception as e:
            if logger:
                logger.error(f"Error selling fish: {str(e)}")
            return False

    async def buy_sushi(self, token, user_id, proxy=None, logger=None):
        """Buy sushi from shop"""
        try:
            sushi_id = "668d070357fb368ad9e91c8a"
            url = f'{self.base_url}/items/{sushi_id}/buy'
            params = {
                'userId': user_id,
                'quantity': 1
            }
            response = self.make_request('GET', url, token=token, proxy=proxy, params=params)
            if response.status_code == 200:
                if logger:
                    logger.info(f"{Fore.GREEN}Successfully bought sushi{Style.RESET_ALL}")
                return True
            if logger:
                logger.error(f"Failed to buy sushi. Status code: {response.status_code}")
            return False
        except Exception as e:
            if logger:
                logger.error(f"Error buying sushi: {str(e)}")
            return False

    async def use_sushi(self, token, user_id, proxy=None, logger=None):
        """Use sushi to restore energy"""
        try:
            sushi_id = "668d070357fb368ad9e91c8a"
            url = f'{self.base_url}/items/{sushi_id}/use'
            params = {'userId': user_id}
            response = self.make_request('GET', url, token=token, proxy=proxy, params=params)
            if response.status_code == 200:
                if logger:
                    logger.info(f"{Fore.GREEN}Successfully used sushi (+5 energy){Style.RESET_ALL}")
                return True
            if logger:
                logger.error(f"Failed to use sushi. Status code: {response.status_code}")
            return False
        except Exception as e:
            if logger:
                logger.error(f"Error using sushi: {str(e)}")
            return False

    async def auto_sell_fish(self, token, user_id, proxy=None, logger=None):
        """Auto sell all fish in inventory"""
        if not self.config.get('enable_auto_sell', True):
            return False

        try:
            # Get updated user info to get fish inventory
            response = self.make_request('GET', f'{self.base_url}/users/me', 
                                    token=token,
                                    proxy=proxy)
            if response.status_code != 200:
                return False

            user_data = response.json()
            fish_list = user_data.get('list_fish_info', [])
            
            total_gold_before = user_data.get('gold', 0)
            sold_count = 0
            total_earned = 0
            
            for fish in fish_list:
                fish_id = fish.get('id')
                fish_name = fish.get('fishName')
                sell_price = fish.get('sellPrice', 0)
                quantity = fish.get('quantity', 0)
                
                if fish_id and quantity > 0:
                    if await self.sell_fish(token, fish_id, user_id, proxy, logger):
                        sold_count += 1
                        earned = sell_price * quantity
                        total_earned += earned
                        if logger:
                            logger.info(f"{Fore.GREEN}Sold {quantity}x {fish_name} for {earned} gold{Style.RESET_ALL}")
                        await asyncio.sleep(0.5)  # Small delay between sells
            
            if sold_count > 0:
                # Get updated gold amount
                new_gold = self.get_user_gold(token, proxy)
                if logger:
                    logger.info(f"{Fore.GREEN}Total fish sold: {sold_count} types, Earned: {total_earned} gold{Style.RESET_ALL}")
                    logger.info(f"{Fore.CYAN}Current gold balance: {new_gold}{Style.RESET_ALL}")
            
            return sold_count > 0
        except Exception as e:
            if logger:
                logger.error(f"Error in auto sell fish: {str(e)}")
            return False

    async def manage_energy(self, token, user_id, proxy=None, logger=None):
        """Manage energy by buying and using sushi when needed"""
        if not self.config.get('enable_auto_buy_sushi', True):
            return False

        try:
            current_energy = self.get_user_energy(token, proxy)
            current_gold = self.get_user_gold(token, proxy)
            min_gold_required = self.config.get('min_gold_for_sushi', 500)
            
            if current_energy <= self.config.get('fishing_energy_limit', 5) and current_gold >= min_gold_required:
                if logger:
                    logger.info(f"{Fore.YELLOW}Energy low ({current_energy}). Attempting to buy and use sushi{Style.RESET_ALL}")
                
                if await self.buy_sushi(token, user_id, proxy, logger):
                    await asyncio.sleep(1)  # Wait a bit before using
                    if await self.use_sushi(token, user_id, proxy, logger):
                        new_energy = self.get_user_energy(token, proxy)
                        if logger:
                            logger.info(f"{Fore.GREEN}Energy recharged. Current energy: {new_energy}{Style.RESET_ALL}")
                        return True
            return False
        except Exception as e:
            if logger:
                logger.error(f"Error in energy management: {str(e)}")
            return False

    async def auto_fish(self, token, fishing_game, logger):
        if not self.config.get('enable_auto_fishing', True):
            return
            
        energy_limit = self.config.get('fishing_energy_limit', 5)
        user_info = self.get_user_info(token, fishing_game.proxy, logger)
        
        if not user_info:
            logger.error("Failed to get user info")
            return
            
        user_id = user_info.get('userId')
        
        try:
            while True:
                current_energy = self.get_user_energy(token, fishing_game.proxy)
                logger.info(f"{Fore.CYAN}Current energy: {current_energy}{Style.RESET_ALL}")

                if current_energy <= energy_limit:
                    # Try to sell fish first to get gold
                    if self.config.get('enable_auto_sell', True):
                        await self.auto_sell_fish(token, user_id, fishing_game.proxy, logger)
                    
                    # Try to manage energy
                    if self.config.get('enable_auto_buy_sushi', True):
                        energy_managed = await self.manage_energy(token, user_id, fishing_game.proxy, logger)
                        if not energy_managed:
                            logger.info(f"{Fore.YELLOW}Energy too low ({current_energy}) and cannot recharge, stopping{Style.RESET_ALL}")
                            break
                    else:
                        logger.info(f"{Fore.YELLOW}Energy too low ({current_energy}), auto buy sushi disabled{Style.RESET_ALL}")
                        break
                    
                    # Recheck energy after management
                    current_energy = self.get_user_energy(token, fishing_game.proxy)

                # Proceed with fishing if we have enough energy
                if current_energy > energy_limit:
                    auto_fishing_ranges = self.config.get('auto_fishing_ranges', ["short_range"])
                    available_ranges = []
                    
                    for range_type in auto_fishing_ranges:
                        required_energy = self.range_energy[range_type]
                        if current_energy >= required_energy:
                            available_ranges.append(range_type)
                            break

                    if not available_ranges:
                        logger.info(f"{Fore.YELLOW}Not enough energy for any range ({current_energy}), stopping{Style.RESET_ALL}")
                        break

                    range_type = available_ranges[0]
                    success = await fishing_game.new_fishing_session(range_type)
                    
                    if success and self.config.get('enable_auto_sell', True):
                        # Auto sell after successful fishing
                        await self.auto_sell_fish(token, user_id, fishing_game.proxy, logger)
                    
                    await asyncio.sleep(random.uniform(
                        self.config.get('delay_between_fishing', [2, 4])[0],
                        self.config.get('delay_between_fishing', [2, 4])[1]
                    ))
                else:
                    break

        except Exception as e:
            logger.error(f"Error in auto fishing: {str(e)}")
            logger.error(f"Full error trace: {traceback.format_exc()}")

    async def process_account_async(self, account, account_index, logger):
        try:
            working_proxy = self.proxy_manager.get_working_proxy()
            if working_proxy:
                logger.info(f"{Fore.GREEN}Using proxy for account {account_index}{Style.RESET_ALL}")
            else:
                logger.info(f"{Fore.YELLOW}Running without proxy for account {account_index}{Style.RESET_ALL}")

            device_id = self.tokens.get(str(account['telegram_id']), {}).get('device_id')
            if not device_id:
                device_id = str(uuid.uuid4())

            token_data = self.tokens.get(str(account['telegram_id']), {})
            current_token = token_data.get('token')
            user_id = token_data.get('user_id')

            max_refresh_attempts = self.config.get('retry_attempts', 3)
            refresh_attempt = 0
            
            while refresh_attempt < max_refresh_attempts:
                if current_token:
                    user_info = self.get_user_info(current_token, proxy=working_proxy, logger=logger)
                    if user_info:
                        logger.info(f"{Fore.GREEN}Token validated successfully{Style.RESET_ALL}")
                        break
                    else:
                        logger.warning(f"{Fore.YELLOW}Token validation failed, attempting refresh ({refresh_attempt + 1}/{max_refresh_attempts}){Style.RESET_ALL}")
                else:
                    logger.info(f"{Fore.CYAN}No token found, performing initial login{Style.RESET_ALL}")

                login_data = self.guest_login(account['telegram_id'], account['name'], device_id, proxy=working_proxy, logger=logger)
                
                if login_data:
                    current_token = login_data['token']
                    user_id = login_data['user_id']
                    
                    self.tokens[str(account['telegram_id'])] = {
                        'device_id': device_id,
                        'token': current_token,
                        'user_id': user_id
                    }
                    self.save_tokens()
                    
                    user_info = self.get_user_info(current_token, proxy=working_proxy, logger=logger)
                    if user_info:
                        logger.info(f"{Fore.GREEN}New token obtained and validated successfully{Style.RESET_ALL}")
                        break
                
                refresh_attempt += 1
                await asyncio.sleep(2)

            if not current_token or not user_id:
                logger.error(f"{Fore.RED}Failed to obtain valid token{Style.RESET_ALL}")
                return

            if self.config.get('enable_tutorial', True):
                try:
                    self.complete_tutorial(current_token, user_id, proxy=working_proxy, logger=logger)
                except Exception as e:
                    logger.error(f"Error completing tutorial: {str(e)}")

            if self.config.get('enable_ref_code', True):
                try:
                    self.verify_ref_code(current_token, self.config['ref_code'], proxy=working_proxy, logger=logger)
                except Exception as e:
                    logger.error(f"Error verifying ref code: {str(e)}")

            if self.config.get('enable_daily_claim', True):
                try:
                    self.claim_daily_reward(current_token, proxy=working_proxy, logger=logger)
                except Exception as e:
                    logger.error(f"Error claiming daily reward: {str(e)}")

            if self.config.get('enable_tasks', True):
                try:
                    self.complete_social_tasks(current_token, proxy=working_proxy, logger=logger)
                except Exception as e:
                    logger.error(f"Error completing social tasks: {str(e)}")

            if self.config.get('enable_auto_fishing', True):
                try:
                    current_energy = self.get_user_energy(current_token, working_proxy)
                    if current_energy > self.config.get('fishing_energy_limit', 5):
                        fishing_game = FishingGame(current_token, logger, proxy=working_proxy)
                        await self.auto_fish(current_token, fishing_game, logger)
                    else:
                        logger.info(f"{Fore.YELLOW}Not enough energy to start fishing: {current_energy}{Style.RESET_ALL}")
                except Exception as e:
                    logger.error(f"Error in auto fishing: {str(e)}")

            logger.info(f"{Fore.GREEN}Account {account_index} processing completed{Style.RESET_ALL}")

        except Exception as e:
            logger.error(f"Error processing account: {str(e)}")
            logger.error(f"Full error trace: {traceback.format_exc()}")
        finally:
            # Cleanup
            thread_id = threading.get_ident()
            logger_key = f"{account['username']}_{account_index}_{thread_id}"
            self.loggers.pop(logger_key, None)

    def process_account(self, account, account_index):
        real_account_number = self.get_next_account_number()
        logger = self.get_logger_for_thread(account['username'], real_account_number)
        
        try:
            asyncio.run(self.process_account_async(account, real_account_number, logger))
        except Exception as e:
            logger.error(f"Error processing account: {str(e)}")
        finally:
            # Cleanup logger
            thread_id = threading.get_ident()
            logger_key = f"{account['username']}_{real_account_number}_{thread_id}"
            self.loggers.pop(logger_key, None)

    def run(self):
        logger = self.get_default_logger()
        accounts = self.parse_query_file()
        
        if not accounts:
            logger.error(f"{Fore.RED}No accounts found to process{Style.RESET_ALL}")
            return

        max_threads = min(self.config.get('max_threads', 3), len(accounts))
        logger.info(f"{Fore.CYAN}Starting bot with {max_threads} threads for {len(accounts)} accounts{Style.RESET_ALL}")
        
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            futures = []
            for index, account in enumerate(accounts, 1):
                future = executor.submit(self.process_account, account, index)
                futures.append(future)
                
                time.sleep(random.uniform(
                    self.config.get('delay_between_accounts', [2, 5])[0],
                    self.config.get('delay_between_accounts', [2, 5])[1]
                ))

            for future in futures:
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Thread execution failed: {str(e)}")

            logger.info(f"{Fore.GREEN}All accounts processed successfully{Style.RESET_ALL}")

if __name__ == '__main__':
    try:
        bot = FishingFrenzyBot()
        bot.run()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Bot stopped by user{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Critical error: {str(e)}{Style.RESET_ALL}")
        traceback.print_exc()
    finally:
        try:
            colorama.deinit()
        except:
            pass
