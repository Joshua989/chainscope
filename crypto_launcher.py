from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import json
import os
from pycoingecko import CoinGeckoAPI

class CryptoLauncher:
    def __init__(self, cache_duration=1800):  # 30 minutes cache by default
        self.cache_duration = cache_duration
        self.cache_file = 'static/data/token_launches_cache.json'
        self.cg = CoinGeckoAPI()
        
        # Create cache directory if it doesn't exist
        os.makedirs('static/data', exist_ok=True)

    def _load_cache(self):
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    cache_data = json.load(f)
                if datetime.now().timestamp() - cache_data['timestamp'] < self.cache_duration:
                    return cache_data['data']
        except Exception as e:
            print(f"Error loading cache: {e}")
        return None

    def _save_cache(self, data):
        try:
            cache_data = {
                'timestamp': datetime.now().timestamp(),
                'data': data
            }
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f)
        except Exception as e:
            print(f"Error saving cache: {e}")

    def get_new_launches(self, force_refresh=True):  # Changed default to True
        """Get new launches with forced refresh option"""
        if not force_refresh:
            cached_data = self._load_cache()
            if cached_data:
                return cached_data

        launches = {
            'new_listings': self._get_coingecko_listings(),
            'upcoming_idos': self._get_upcoming_idos(),
            'presales': self._get_presales(),
            'airdrops': self._get_airdrops(),
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        self._save_cache(launches)
        return launches

    def _get_coingecko_listings(self):
        try:
            listings = self.cg.get_coins_markets(
                vs_currency='usd',
                order='id_desc',
                per_page=20,
                sparkline=False
            )
            
            week_ago = datetime.now() - timedelta(days=7)
            new_tokens = []
            
            for token in listings:
                # Check if last_updated exists and is not None
                if token.get('last_updated'):
                    try:
                        update_time = datetime.strptime(
                            token['last_updated'].split('.')[0],
                            '%Y-%m-%dT%H:%M:%S'
                        )
                        if update_time > week_ago:
                            new_tokens.append({
                                'name': token['name'],
                                'symbol': token['symbol'].upper(),
                                'image': token.get('image', ''),
                                'launch_date': update_time.strftime('%Y-%m-%d'),
                                'price': token.get('current_price', 0),
                                'market_cap': token.get('market_cap', 0),
                                'volume': token.get('total_volume', 0),
                                'price_change_24h': token.get('price_change_percentage_24h', 0),
                                'url': f"https://www.coingecko.com/en/coins/{token['id']}"
                            })
                    except (ValueError, TypeError) as e:
                        print(f"Error parsing date for token {token.get('name')}: {e}")
                        continue
                    
            return new_tokens[:10]
        except Exception as e:
            print(f"Error fetching CoinGecko listings: {e}")
            return []

    def _get_upcoming_idos(self):
        try:
            urls = [
                "https://cryptorank.io/upcoming-ico",
                "https://www.pinksale.finance/launchpad"
            ]
            idos = []
            
            for url in urls:
                headers = {'User-Agent': 'Mozilla/5.0'}
                response = requests.get(url, headers=headers)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    if 'cryptorank' in url:
                        idos.extend(self._parse_cryptorank_idos(soup))
                    elif 'pinksale' in url:
                        idos.extend(self._parse_pinksale_idos(soup))
                        
            return idos[:10]
        except Exception as e:
            print(f"Error fetching upcoming IDOs: {e}")
            return []

    def _get_presales(self):
        try:
            urls = [
                "https://dxsale.app/dxsale",
                "https://www.unicrypt.network/presale"
            ]
            presales = []
            
            for url in urls:
                headers = {'User-Agent': 'Mozilla/5.0'}
                response = requests.get(url, headers=headers)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    if 'dxsale' in url:
                        presales.extend(self._parse_dxsale_presales(soup))
                    elif 'unicrypt' in url:
                        presales.extend(self._parse_unicrypt_presales(soup))
                        
            return presales[:10]
        except Exception as e:
            print(f"Error fetching presales: {e}")
            return []

    def _get_airdrops(self):
        try:
            cmc_url = "https://coinmarketcap.com/airdrop/"
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(cmc_url, headers=headers)
            airdrops = []
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                items = soup.find_all('div', class_='sc-1a736df3-0')
                
                for item in items[:10]:
                    try:
                        airdrop = {
                            'name': item.find('h3').text,
                            'image': item.find('img')['src'],
                            'end_date': item.find('div', class_='end-date').text,
                            'url': f"https://coinmarketcap.com{item.find('a')['href']}"
                        }
                        airdrops.append(airdrop)
                    except:
                        continue
                        
            return airdrops
        except Exception as e:
            print(f"Error fetching airdrops: {e}")
            return []

    def _parse_cryptorank_idos(self, soup):
        idos = []
        try:
            items = soup.find_all('div', class_='upcoming-ico-item')
            for item in items[:5]:
                try:
                    idos.append({
                        'name': item.find('h3').text,
                        'image': item.find('img')['src'],
                        'start_date': item.find('div', class_='start-date').text,
                        'url': f"https://cryptorank.io{item.find('a')['href']}"
                    })
                except:
                    continue
        except Exception as e:
            print(f"Error parsing Cryptorank IDOs: {e}")
        return idos

    def _parse_pinksale_idos(self, soup):
        idos = []
        try:
            items = soup.find_all('div', class_='presale-item')
            for item in items[:5]:
                try:
                    idos.append({
                        'name': item.find('h4').text,
                        'image': item.find('img')['src'],
                        'start_date': item.find('div', class_='start-time').text,
                        'url': f"https://www.pinksale.finance{item.find('a')['href']}"
                    })
                except:
                    continue
        except Exception as e:
            print(f"Error parsing PinkSale IDOs: {e}")
        return idos

    def _parse_dxsale_presales(self, soup):
        presales = []
        try:
            # Look for presale containers
            items = soup.find_all('div', {'class': ['presale-card', 'sale-card', 'dx-card']})
            
            for item in items[:5]:
                try:
                    # Extract data with multiple possible class names
                    name_elem = item.find(['h3', 'h4', 'div'], {'class': ['sale-title', 'presale-title']})
                    image_elem = item.find('img')
                    date_elem = item.find(['span', 'div'], {'class': ['sale-date', 'presale-date', 'launch-date']})
                    link_elem = item.find('a')

                    if name_elem:
                        presale = {
                            'name': name_elem.text.strip(),
                            'image': image_elem.get('src', '') if image_elem else '',
                            'start_date': date_elem.text.strip() if date_elem else 'TBA',
                            'url': f"https://dx.app{link_elem['href']}" if link_elem and link_elem.get('href') else ''
                        }
                        presales.append(presale)
                except Exception as e:
                    print(f"Error parsing individual presale: {e}")
                    continue
                    
        except Exception as e:
            print(f"Error parsing DxSale presales: {e}")
        return presales

    def _parse_unicrypt_presales(self, soup):
        presales = []
        try:
            items = soup.find_all('div', {'class': ['presale-item', 'presale-card']})
            
            for item in items[:5]:
                try:
                    name = item.find(['h3', 'h4']).text.strip() if item.find(['h3', 'h4']) else 'Unknown'
                    image = item.find('img')['src'] if item.find('img') else ''
                    date = item.find(['div', 'span'], {'class': ['date', 'time']})
                    date = date.text.strip() if date else 'TBA'
                    url = item.find('a')['href'] if item.find('a') else ''
                    
                    presales.append({
                        'name': name,
                        'image': image,
                        'start_date': date,
                        'url': f"https://unicrypt.network{url}" if url else ''
                    })
                except Exception as e:
                    print(f"Error parsing individual Unicrypt presale: {e}")
                    continue
                    
        except Exception as e:
            print(f"Error parsing Unicrypt presales: {e}")
        return presales