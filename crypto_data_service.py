from datetime import datetime
import requests
import json
from pathlib import Path
import time

class CryptoDataService:
    def __init__(self):
        self.cache_file = Path("cache/crypto_data.json")
        self.cache_file.parent.mkdir(exist_ok=True)
        
        # Free API endpoints
        self.endpoints = {
            'coinmarketcap': 'https://api.coinmarketcap.com/data-api/v3/cryptocurrency/listing',
            'coingecko': 'https://api.coingecko.com/api/v3',
        }

    def get_latest_data(self, force_refresh=False):
        """Fetch latest crypto data from multiple sources"""
        if not force_refresh and self._is_cache_valid():
            return self._load_cache()

        data = {
            'new_tokens': self._get_new_tokens(),
            'airdrops': self._get_airdrops(),
            'new_projects': self._get_new_projects(),
            'last_updated': datetime.now().isoformat()
        }

        self._save_cache(data)
        return data

    def _get_new_tokens(self):
        """Get newly listed tokens from CoinGecko"""
        try:
            response = requests.get(
                f"{self.endpoints['coingecko']}/coins/markets",
                params={
                    'vs_currency': 'usd',
                    'order': 'id_desc',
                    'per_page': 50,
                    'sparkline': 'false',
                    'price_change_percentage': '24h'
                }
            )
            
            if response.status_code == 200:
                tokens = response.json()
                return [{
                    'name': token['name'],
                    'symbol': token['symbol'].upper(),
                    'price': token['current_price'],
                    'image': token['image'],
                    'launch_date': token.get('genesis_date', 'N/A'),
                    'market_cap': token['market_cap'],
                    'volume': token['total_volume']
                } for token in tokens if self._is_recent(token.get('genesis_date'))]
            
            return []
        except Exception as e:
            print(f"Error fetching new tokens: {e}")
            return []

    def _get_airdrops(self):
        """Get active airdrops from CoinGecko and other sources"""
        try:
            # Using CoinGecko's events API
            response = requests.get(
                f"{self.endpoints['coingecko']}/events"
            )
            
            if response.status_code == 200:
                events = response.json()['data']
                airdrops = []
                
                for event in events:
                    if 'airdrop' in event['type'].lower():
                        airdrops.append({
                            'name': event['title'],
                            'description': event['description'],
                            'start_date': event['start_date'],
                            'end_date': event['end_date'],
                            'website': event.get('website', ''),
                            'proof': event.get('proof', '')
                        })
                
                return airdrops
            
            return []
        except Exception as e:
            print(f"Error fetching airdrops: {e}")
            return []

    def _get_new_projects(self):
        """Get new blockchain projects and protocols"""
        try:
            # Using CoinGecko's exchanges API to find new DEXes and protocols
            response = requests.get(
                f"{self.endpoints['coingecko']}/exchanges/decentralized"
            )
            
            if response.status_code == 200:
                dexes = response.json()
                return [{
                    'name': dex['name'],
                    'description': dex.get('description', ''),
                    'url': dex.get('url', ''),
                    'image': dex.get('image', ''),
                    'trade_volume_24h': dex.get('trade_volume_24h_btc', 0)
                } for dex in dexes[:10]]  # Get top 10 new DEXes
            
            return []
        except Exception as e:
            print(f"Error fetching new projects: {e}")
            return []

    def _is_recent(self, date_str):
        """Check if a date is within the last 7 days"""
        if not date_str:
            return False
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d')
            days_old = (datetime.now() - date).days
            return days_old <= 7
        except:
            return False

    def _save_cache(self, data):
        """Save data to cache file"""
        with open(self.cache_file, 'w') as f:
            json.dump(data, f)

    def _load_cache(self):
        """Load data from cache file"""
        try:
            with open(self.cache_file, 'r') as f:
                return json.load(f)
        except:
            return None

    def _is_cache_valid(self):
        """Check if cache is less than 24 hours old"""
        if not self.cache_file.exists():
            return False
        
        cache_age = time.time() - self.cache_file.stat().st_mtime
        return cache_age < 86400  # 24 hours