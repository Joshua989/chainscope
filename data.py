import requests,json,time,re
from bs4 import BeautifulSoup
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import urljoin, urlparse
class CoinHuntScraper:
    def __init__(self, use_selenium=True):
        self.base_url = "https://coinhunt.cc/new-listings"
        self.use_selenium = use_selenium
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36','Accept': 'application/json, text/plain, */*','Accept-Language': 'en-US,en;q=0.9','Accept-Encoding': 'gzip, deflate, br','Connection': 'keep-alive','Referer': 'https://coinhunt.cc/'}
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    def setup_selenium_driver(self):
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument(f'--user-agent={self.headers["User-Agent"]}')
            service = Service(ChromeDriverManager().install())
            return webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            print(f"Error setting up Selenium driver: {e}")
            return None
    def extract_image_url(self, element):
        image_url = ""
        if element:
            for img in element.find_all('img'):
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if src:
                    if src.startswith('//'):
                        image_url = 'https:' + src
                    elif src.startswith('/'):
                        image_url = urljoin('https://coinhunt.cc', src)
                    elif src.startswith('http'):
                        image_url = src
                    else:
                        image_url = urljoin('https://coinhunt.cc/', src)
                    break
            if not image_url:
                for elem in element.find_all(attrs={'style': re.compile(r'background.*image')}):
                    match = re.search(r'url\(["\']?([^"\']+)["\']?\)', elem.get('style', ''))
                    if match:
                        url = match.group(1)
                        if url.startswith('//'):
                            image_url = 'https:' + url
                        elif url.startswith('/'):
                            image_url = urljoin('https://coinhunt.cc', url)
                        elif url.startswith('http'):
                            image_url = url
                        else:
                            image_url = urljoin('https://coinhunt.cc/', url)
                        break
        return image_url
    def scrape_with_selenium(self):
        driver = self.setup_selenium_driver()
        if not driver:
            return []
        try:
            print("Loading page with Selenium...")
            driver.get(self.base_url)
            wait = WebDriverWait(driver, 20)
            for selector in ['table','[class*="table"]','[class*="listing"]','tbody tr','.token-row','[data-testid*="token"]']:
                try:
                    elements = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector)))
                    if elements:
                        break
                except:
                    continue
            else:
                time.sleep(5)
            return self.extract_tokens_from_html(BeautifulSoup(driver.page_source, 'html.parser'))
        except Exception as e:
            print(f"Error with Selenium scraping: {e}")
            return []
        finally:
            if driver:
                driver.quit()
    def extract_tokens_from_html(self, soup):
        for approach in [self.extract_from_table_rows, self.extract_from_divs, self.extract_from_scripts]:
            try:
                tokens = approach(soup)
                if tokens:
                    print(f"Successfully extracted {len(tokens)} tokens")
                    return tokens
            except Exception as e:
                continue
        return []
    def extract_from_table_rows(self, soup):
        tokens = []
        rows = soup.find_all('tr')
        for i, row in enumerate(rows[1:], 1):
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 6:
                try:
                    image_url = ""
                    for cell in cells[:3]:
                        img_url = self.extract_image_url(cell)
                        if img_url:
                            image_url = img_url
                            break
                    token_data = {'rank': i,'name': self.clean_text(cells[1].get_text()) if len(cells) > 1 else '','symbol': '','category': self.clean_text(cells[2].get_text()) if len(cells) > 2 else '','chain': self.clean_text(cells[3].get_text()) if len(cells) > 3 else '','change_24h': self.clean_text(cells[4].get_text()) if len(cells) > 4 else '','market_cap': self.clean_text(cells[5].get_text()) if len(cells) > 5 else '','price': self.clean_text(cells[6].get_text()) if len(cells) > 6 else '','launch_time': self.clean_text(cells[7].get_text()) if len(cells) > 7 else '','votes': self.clean_text(cells[-1].get_text()),'image_url': image_url,'scraped_at': datetime.now().isoformat()}
                    if token_data['name']:
                        tokens.append(token_data)
                except:
                    continue
        return tokens
    def extract_from_divs(self, soup):
        for selector in ['[class*="token"]','[class*="coin"]','[class*="listing"]','[class*="row"]']:
            elements = soup.select(selector)
            if elements:
                tokens = []
                for i, element in enumerate(elements[:50]):
                    try:
                        image_url = self.extract_image_url(element)
                        token_data = {'rank': i + 1,'name': '','symbol': '','category': '','chain': '','change_24h': '','market_cap': '','price': '','launch_time': '','votes': '','image_url': image_url,'raw_text': element.get_text().strip()[:200],'scraped_at': datetime.now().isoformat()}
                        name_elem = element.find(['h1', 'h2', 'h3', 'h4', 'strong', '[class*="name"]'])
                        if name_elem:
                            token_data['name'] = self.clean_text(name_elem.get_text())
                        symbol_elem = element.find('[class*="symbol"]') or element.find('[class*="ticker"]')
                        if symbol_elem:
                            token_data['symbol'] = self.clean_text(symbol_elem.get_text())
                        if token_data['name'] or token_data['symbol']:
                            tokens.append(token_data)
                    except:
                        continue
                if tokens:
                    return tokens
        return []
    def extract_from_scripts(self, soup):
        for script in soup.find_all('script'):
            if script.string and ('tokens' in script.string.lower() or 'listings' in script.string.lower()):
                try:
                    for pattern in [r'tokens\s*[:=]\s*(\[.*?\])',r'listings\s*[:=]\s*(\[.*?\])',r'data\s*[:=]\s*(\[.*?\])',r'window\.__INITIAL_STATE__\s*=\s*({.*?});',r'window\.__APP_DATA__\s*=\s*({.*?});']:
                        match = re.search(pattern, script.string, re.DOTALL | re.IGNORECASE)
                        if match:
                            try:
                                data = json.loads(match.group(1))
                                tokens = self.parse_json_data(data)
                                if tokens:
                                    return tokens
                            except:
                                continue
                except:
                    continue
        return []
    def parse_json_data(self, data):
        tokens = []
        try:
            if isinstance(data, dict):
                token_list = data.get('data') or data.get('tokens') or data.get('listings') or [data]
            else:
                token_list = data
            for item in token_list:
                if isinstance(item, dict):
                    image_url = item.get('image') or item.get('logo') or item.get('icon') or item.get('avatar') or item.get('thumbnail') or item.get('image_url') or item.get('logo_url') or item.get('icon_url') or ""
                    if image_url and not image_url.startswith('http'):
                        if image_url.startswith('//'):
                            image_url = 'https:' + image_url
                        elif image_url.startswith('/'):
                            image_url = urljoin('https://coinhunt.cc', image_url)
                        else:
                            image_url = urljoin('https://coinhunt.cc/', image_url)
                    tokens.append({'name': item.get('name', ''),'symbol': item.get('symbol', item.get('ticker', '')),'category': item.get('category', item.get('type', '')),'chain': item.get('chain', item.get('blockchain', '')),'price': item.get('price', item.get('current_price', '')),'market_cap': item.get('market_cap', item.get('marketCap', '')),'change_24h': item.get('change_24h', item.get('price_change_24h', '')),'launch_time': item.get('launch_time', item.get('created_at', '')),'votes': item.get('votes', item.get('vote_count', 0)),'rank': item.get('rank', len(tokens) + 1),'image_url': image_url,'scraped_at': datetime.now().isoformat()})
        except Exception as e:
            print(f"Error parsing JSON data: {e}")
        return tokens
    def clean_text(self, text):
        return text.strip().replace('\n', ' ').replace('\t', ' ') if text else ""
    def scrape_new_listings(self):
        if self.use_selenium:
            tokens = self.scrape_with_selenium()
            if tokens:
                return tokens
        try:
            response = self.session.get(self.base_url, timeout=15)
            return self.extract_tokens_from_html(BeautifulSoup(response.content, 'html.parser'))
        except Exception as e:
            print(f"Regular requests failed: {e}")
            return []
    def validate_image_urls(self, tokens):
        print("Validating image URLs...")
        for token in tokens:
            try:
                token['image_url_valid'] = self.session.head(token['image_url'], timeout=5).status_code == 200 if token.get('image_url') else False
            except:
                token['image_url_valid'] = False
        valid_images = sum(1 for token in tokens if token.get('image_url_valid', False))
        print(f"Found {valid_images} tokens with valid image URLs out of {len(tokens)} total")
        return tokens
    def save_to_json(self, data, filename='coinhunt_tokens.json'):
        try:
            tokens_with_images = sum(1 for token in data if token.get('image_url'))
            output_data = {'scraped_at': datetime.now().isoformat(),'source': self.base_url,'total_tokens': len(data),'tokens_with_images': tokens_with_images,'tokens': data}
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            print(f"Data saved to {filename}")
            print(f"Tokens with images: {tokens_with_images}/{len(data)}")
            return True
        except Exception as e:
            print(f"Error saving to JSON: {e}")
            return False
    def run_scraper(self, output_file='coinhunt_tokens.json', validate_images=False):
        print("Starting CoinHunt token scraper...")
        tokens = self.scrape_new_listings()
        if tokens:
            if validate_images:
                tokens = self.validate_image_urls(tokens)
            if self.save_to_json(tokens, output_file):
                print(f"Successfully scraped {len(tokens)} tokens!")
                for i, token in enumerate(tokens[:3]):
                    print(f"{i+1}. {token.get('name', 'N/A')} ({token.get('symbol', 'N/A')})")
                    print(f"   Chain: {token.get('chain', 'N/A')}")
                    print(f"   Category: {token.get('category', 'N/A')}")
                    if token.get('image_url'):
                        print(f"   Image: {token['image_url']}")
                    print()
                return tokens
            else:
                print("Failed to save data")
                return None
        else:
            print("No tokens found. Try: pip install selenium webdriver-manager")
            return None
def main():
    print("CoinHunt Token Scraper")
    print("=====================")
    try:
        scraper = CoinHuntScraper(use_selenium=True)
        scraper.run_scraper('coinhunt_new_listings.json', validate_images=True)
    except Exception as e:
        print(f"Error: {e}")
if __name__ == "__main__":
    main()