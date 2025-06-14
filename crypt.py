import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import time
import re
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
        self.api_url = "https://coinhunt.cc/api"  # Try to find API endpoint
        self.use_selenium = use_selenium
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Referer': 'https://coinhunt.cc/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def setup_selenium_driver(self):
        """Setup Selenium WebDriver with Chrome"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')  # Run in background
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument(f'--user-agent={self.headers["User-Agent"]}')
            
            # Install ChromeDriver automatically
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            return driver
        except Exception as e:
            print(f"Error setting up Selenium driver: {e}")
            print("Please install ChromeDriver or try the API method")
            return None

    def extract_image_url(self, element):
        """Extract image URL from various sources"""
        image_url = ""
        
        if element:
            # Try different ways to find image URLs
            img_tags = element.find_all('img')
            for img in img_tags:
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if src:
                    # Convert relative URLs to absolute
                    if src.startswith('//'):
                        image_url = 'https:' + src
                    elif src.startswith('/'):
                        image_url = urljoin('https://coinhunt.cc', src)
                    elif src.startswith('http'):
                        image_url = src
                    else:
                        image_url = urljoin('https://coinhunt.cc/', src)
                    break
            
            # Also check for background images in style attributes
            if not image_url:
                style_elements = element.find_all(attrs={'style': re.compile(r'background.*image')})
                for elem in style_elements:
                    style = elem.get('style', '')
                    match = re.search(r'url\(["\']?([^"\']+)["\']?\)', style)
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

    def try_api_approach(self):
        """Try to find and use API endpoints"""
        print("Trying API approach...")
        
        # Common API endpoints to try
        api_endpoints = [
            "https://coinhunt.cc/api/tokens",
            "https://coinhunt.cc/api/listings",
            "https://coinhunt.cc/api/new-listings",
            "https://api.coinhunt.cc/tokens",
            "https://api.coinhunt.cc/listings"
        ]
        
        for endpoint in api_endpoints:
            try:
                print(f"Trying endpoint: {endpoint}")
                response = self.session.get(endpoint, timeout=10)
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if data and isinstance(data, (list, dict)):
                            print(f"Found working API endpoint: {endpoint}")
                            return self.parse_api_response(data)
                    except json.JSONDecodeError:
                        continue
                        
            except requests.RequestException:
                continue
        
        print("No working API endpoints found")
        return []

    def parse_api_response(self, data):
        """Parse API response data"""
        tokens = []
        
        try:
            # Handle different response structures
            if isinstance(data, dict):
                if 'data' in data:
                    token_list = data['data']
                elif 'tokens' in data:
                    token_list = data['tokens']
                elif 'listings' in data:
                    token_list = data['listings']
                else:
                    token_list = [data]  # Single token
            else:
                token_list = data  # Already a list
            
            for item in token_list:
                if isinstance(item, dict):
                    # Extract image URL from various possible fields
                    image_url = (
                        item.get('image') or 
                        item.get('logo') or 
                        item.get('icon') or 
                        item.get('avatar') or 
                        item.get('thumbnail') or 
                        item.get('image_url') or 
                        item.get('logo_url') or 
                        item.get('icon_url') or
                        ""
                    )
                    
                    # Ensure full URL
                    if image_url and not image_url.startswith('http'):
                        if image_url.startswith('//'):
                            image_url = 'https:' + image_url
                        elif image_url.startswith('/'):
                            image_url = urljoin('https://coinhunt.cc', image_url)
                        else:
                            image_url = urljoin('https://coinhunt.cc/', image_url)
                    
                    token_data = {
                        'name': item.get('name', ''),
                        'symbol': item.get('symbol', item.get('ticker', '')),
                        'category': item.get('category', item.get('type', '')),
                        'chain': item.get('chain', item.get('blockchain', '')),
                        'price': item.get('price', item.get('current_price', '')),
                        'market_cap': item.get('market_cap', item.get('marketCap', '')),
                        'change_24h': item.get('change_24h', item.get('price_change_24h', '')),
                        'launch_time': item.get('launch_time', item.get('created_at', '')),
                        'votes': item.get('votes', item.get('vote_count', 0)),
                        'rank': item.get('rank', len(tokens) + 1),
                        'image_url': image_url,
                        'scraped_at': datetime.now().isoformat()
                    }
                    tokens.append(token_data)
                    
        except Exception as e:
            print(f"Error parsing API response: {e}")
            
        return tokens

    def scrape_with_selenium(self):
        """Scrape using Selenium for JavaScript-rendered content"""
        driver = self.setup_selenium_driver()
        if not driver:
            return []
        
        try:
            print("Loading page with Selenium...")
            driver.get(self.base_url)
            
            # Wait for the table to load
            wait = WebDriverWait(driver, 20)
            
            # Try different selectors for the token table
            table_selectors = [
                'table',
                '[class*="table"]',
                '[class*="listing"]',
                'tbody tr',
                '.token-row',
                '[data-testid*="token"]'
            ]
            
            table_found = False
            for selector in table_selectors:
                try:
                    elements = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector)))
                    if elements:
                        print(f"Found elements with selector: {selector}")
                        table_found = True
                        break
                except:
                    continue
            
            if not table_found:
                print("Waiting for content to load...")
                time.sleep(5)
            
            # Get page source after JavaScript execution
            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract tokens from rendered HTML
            tokens = self.extract_tokens_from_html(soup)
            
            return tokens
            
        except Exception as e:
            print(f"Error with Selenium scraping: {e}")
            return []
        finally:
            if driver:
                driver.quit()

    def extract_tokens_from_html(self, soup):
        """Extract token data from HTML soup"""
        tokens = []
        
        # Try multiple approaches to find token data
        approaches = [
            self.extract_from_table_rows,
            self.extract_from_divs,
            self.extract_from_scripts
        ]
        
        for approach in approaches:
            try:
                tokens = approach(soup)
                if tokens:
                    print(f"Successfully extracted {len(tokens)} tokens")
                    break
            except Exception as e:
                print(f"Approach failed: {e}")
                continue
        
        return tokens

    def extract_from_table_rows(self, soup):
        """Extract from table rows"""
        tokens = []
        
        # Find table rows
        rows = soup.find_all('tr')
        print(f"Found {len(rows)} table rows")
        
        for i, row in enumerate(rows):
            if i == 0:  # Skip header
                continue
                
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 6:  # Minimum expected columns
                try:
                    # Extract image URL from the first few cells (usually contains logo)
                    image_url = ""
                    for cell in cells[:3]:  # Check first 3 cells for images
                        img_url = self.extract_image_url(cell)
                        if img_url:
                            image_url = img_url
                            break
                    
                    token_data = {
                        'rank': i,
                        'name': self.clean_text(cells[1].get_text()) if len(cells) > 1 else '',
                        'symbol': '',
                        'category': self.clean_text(cells[2].get_text()) if len(cells) > 2 else '',
                        'chain': self.clean_text(cells[3].get_text()) if len(cells) > 3 else '',
                        'change_24h': self.clean_text(cells[4].get_text()) if len(cells) > 4 else '',
                        'market_cap': self.clean_text(cells[5].get_text()) if len(cells) > 5 else '',
                        'price': self.clean_text(cells[6].get_text()) if len(cells) > 6 else '',
                        'launch_time': self.clean_text(cells[7].get_text()) if len(cells) > 7 else '',
                        'votes': self.clean_text(cells[-1].get_text()),
                        'image_url': image_url,
                        'scraped_at': datetime.now().isoformat()
                    }
                    
                    if token_data['name']:  # Only add if we have a name
                        tokens.append(token_data)
                        
                except Exception as e:
                    print(f"Error extracting row {i}: {e}")
                    continue
        
        return tokens

    def extract_from_divs(self, soup):
        """Extract from div elements (in case of custom layout)"""
        tokens = []
        
        # Look for common patterns in crypto listing sites
        selectors = [
            '[class*="token"]',
            '[class*="coin"]',
            '[class*="listing"]',
            '[class*="row"]'
        ]
        
        for selector in selectors:
            elements = soup.select(selector)
            if elements:
                print(f"Found {len(elements)} elements with selector: {selector}")
                
                for i, element in enumerate(elements[:50]):  # Limit to first 50
                    try:
                        # Extract text content
                        text_content = element.get_text().strip()
                        
                        # Extract image URL
                        image_url = self.extract_image_url(element)
                        
                        # Try to parse token info from the element
                        token_data = {
                            'rank': i + 1,
                            'name': '',
                            'symbol': '',
                            'category': '',
                            'chain': '',
                            'change_24h': '',
                            'market_cap': '',
                            'price': '',
                            'launch_time': '',
                            'votes': '',
                            'image_url': image_url,
                            'raw_text': text_content[:200],  # Store raw text for debugging
                            'scraped_at': datetime.now().isoformat()
                        }
                        
                        # Try to extract structured data from sub-elements
                        name_elem = element.find(['h1', 'h2', 'h3', 'h4', 'strong', '[class*="name"]'])
                        if name_elem:
                            token_data['name'] = self.clean_text(name_elem.get_text())
                        
                        symbol_elem = element.find('[class*="symbol"]') or element.find('[class*="ticker"]')
                        if symbol_elem:
                            token_data['symbol'] = self.clean_text(symbol_elem.get_text())
                        
                        if token_data['name'] or token_data['symbol']:
                            tokens.append(token_data)
                            
                    except Exception as e:
                        print(f"Error processing element {i}: {e}")
                        continue
                
                if tokens:
                    break
        
        return tokens

    def extract_from_scripts(self, soup):
        """Extract data from JavaScript variables in script tags"""
        tokens = []
        
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                # Look for JSON data in scripts
                if 'tokens' in script.string.lower() or 'listings' in script.string.lower():
                    try:
                        # Try to extract JSON data
                        text = script.string
                        
                        # Common patterns for embedded data
                        patterns = [
                            r'tokens\s*[:=]\s*(\[.*?\])',
                            r'listings\s*[:=]\s*(\[.*?\])',
                            r'data\s*[:=]\s*(\[.*?\])',
                            r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
                            r'window\.__APP_DATA__\s*=\s*({.*?});'
                        ]
                        
                        for pattern in patterns:
                            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
                            if match:
                                try:
                                    data = json.loads(match.group(1))
                                    tokens = self.parse_api_response(data)
                                    if tokens:
                                        return tokens
                                except:
                                    continue
                                    
                    except Exception as e:
                        continue
        
        return tokens

    def clean_text(self, text):
        """Clean and normalize text"""
        if not text:
            return ""
        return text.strip().replace('\n', ' ').replace('\t', ' ')

    def scrape_new_listings(self):
        """Main scraping method with fallback approaches"""
        tokens = []
        
        # Approach 1: Try API endpoints
        print("Step 1: Trying API approach...")
        tokens = self.try_api_approach()
        
        if tokens:
            print(f"Successfully got {len(tokens)} tokens from API")
            return tokens
        
        # Approach 2: Use Selenium if enabled
        if self.use_selenium:
            print("Step 2: Trying Selenium approach...")
            tokens = self.scrape_with_selenium()
            
            if tokens:
                return tokens
        
        # Approach 3: Regular requests (fallback)
        print("Step 3: Trying regular requests approach...")
        try:
            response = self.session.get(self.base_url, timeout=15)
            soup = BeautifulSoup(response.content, 'html.parser')
            tokens = self.extract_tokens_from_html(soup)
        except Exception as e:
            print(f"Regular requests failed: {e}")
        
        return tokens

    def validate_image_urls(self, tokens):
        """Validate and check if image URLs are accessible"""
        print("Validating image URLs...")
        
        for token in tokens:
            if token.get('image_url'):
                try:
                    # Quick check if URL is accessible
                    response = self.session.head(token['image_url'], timeout=5)
                    token['image_url_valid'] = response.status_code == 200
                except:
                    token['image_url_valid'] = False
            else:
                token['image_url_valid'] = False
        
        valid_images = sum(1 for token in tokens if token.get('image_url_valid', False))
        print(f"Found {valid_images} tokens with valid image URLs out of {len(tokens)} total")
        
        return tokens

    def save_to_json(self, data, filename='coinhunt_tokens.json'):
        """Save scraped data to JSON file"""
        try:
            # Count tokens with images
            tokens_with_images = sum(1 for token in data if token.get('image_url'))
            
            output_data = {
                'scraped_at': datetime.now().isoformat(),
                'source': self.base_url,
                'total_tokens': len(data),
                'tokens_with_images': tokens_with_images,
                'tokens': data
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            
            print(f"Data saved to {filename}")
            print(f"Tokens with images: {tokens_with_images}/{len(data)}")
            return True
            
        except Exception as e:
            print(f"Error saving to JSON: {e}")
            return False

    def run_scraper(self, output_file='coinhunt_tokens.json', validate_images=False):
        """Main method to run the scraper"""
        print("Starting CoinHunt token scraper...")
        print("This may take a moment as we try different approaches...")
        
        tokens = self.scrape_new_listings()
        
        if tokens:
            # Optionally validate image URLs
            if validate_images:
                tokens = self.validate_image_urls(tokens)
            
            success = self.save_to_json(tokens, output_file)
            if success:
                print(f"Successfully scraped {len(tokens)} tokens!")
                
                # Show sample data
                if tokens:
                    print("\nSample token data:")
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
            print("No tokens found. The website might be using advanced protection.")
            print("Try installing Selenium dependencies:")
            print("pip install selenium webdriver-manager")
            return None


def main():
    """Main function"""
    print("CoinHunt Token Scraper with Image URLs")
    print("======================================")
    
    # You can disable Selenium if you don't want to install it
    use_selenium = True
    validate_images = True  # Set to True if you want to validate image URLs
    
    try:
        scraper = CoinHuntScraper(use_selenium=use_selenium)
        tokens = scraper.run_scraper('coinhunt_new_listings.json', validate_images=validate_images)
        
        if not tokens:
            print("\nTroubleshooting tips:")
            print("1. Install Selenium: pip install selenium webdriver-manager")
            print("2. Check if the website structure has changed")
            print("3. Try running with different network settings")
            print("4. The website might have anti-bot protection")
            
    except Exception as e:
        print(f"Error running scraper: {e}")


if __name__ == "__main__":
    main()