#!/usr/bin/env python3
import requests
import json
import time
from datetime import datetime
import threading
from dataclasses import dataclass
from typing import List, Dict, Optional
import logging
import random
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urljoin
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
class MultiJobScraper:
    def __init__(self, use_selenium=False):
        self.use_selenium = use_selenium
        self.driver = None
        if use_selenium:
            self.setup_selenium()
        else:
            self.session = requests.Session()
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            })
    def setup_selenium(self):
        try:
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.get('about:blank')
            logger.info("Selenium WebDriver initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize Selenium: {e}. Falling back to requests.")
            self.use_selenium = False
            self.driver = None
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
    def get_page(self, url, retries=3, wait_for_element=None, scroll=False):
        if self.use_selenium and self.driver:
            return self.get_page_selenium(url, wait_for_element, retries, scroll)
        else:
            return self.get_page_requests(url, retries)
    def get_page_selenium(self, url, wait_for_element=None, retries=3, scroll=False):
        for attempt in range(retries):
            try:
                self.driver.get(url)
                if wait_for_element:
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_element))
                    )
                else:
                    time.sleep(3)
                if scroll:
                    for i in range(3):
                        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(2)
                return self.driver.page_source
            except Exception as e:
                logger.warning(f"Selenium attempt {attempt + 1} failed for {url}: {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    logger.error(f"Failed to fetch {url} with Selenium after {retries} attempts")
                    return None
    def get_page_requests(self, url, retries=3):
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=10)
                response.raise_for_status()
                return response.text
            except requests.RequestException as e:
                logger.warning(f"Requests attempt {attempt + 1} failed for {url}: {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    logger.error(f"Failed to fetch {url} with requests after {retries} attempts")
                    return None
    def __del__(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
class Web3CareerScraper(MultiJobScraper):
    def __init__(self, use_selenium=False):
        super().__init__(use_selenium)
        self.base_url = "https://web3.career"
    def extract_job_data(self, job_row):
        job_data = {'source': 'web3.career'}
        try:
            is_sponsored = 'table-paid' in job_row.get('class', [])
            job_data['is_sponsored'] = is_sponsored
            job_id = job_row.get('data-jobid')
            job_data['job_id'] = job_id
            onclick = job_row.get('onclick', '')
            if onclick and 'tableTurboRowClick' in onclick:
                start = onclick.find("'") + 1
                end = onclick.find("'", start)
                if start > 0 and end > start:
                    job_url = onclick[start:end]
                    job_data['job_url'] = urljoin(self.base_url, job_url)
            row_text = job_row.get_text(strip=True)
            text_parts = [part.strip() for part in row_text.split('\n') if part.strip()]
            logo_img = job_row.find('img')
            if logo_img:
                logo_src = logo_img.get('src')
                if logo_src:
                    job_data['company_logo'] = urljoin(self.base_url, logo_src)
            cells = job_row.find_all('td')
            for cell in cells:
                cell_text = cell.get_text(strip=True)
                title_links = cell.find_all('a', href=True)
                for link in title_links:
                    link_text = link.get_text(strip=True)
                    if len(link_text) > 10 and not any(word in link_text.lower() for word in ['apply', 'company', 'more']):
                        job_data['title'] = link_text
                        break
                company_elements = cell.find_all(['span', 'div', 'strong'], class_=lambda x: x and 'company' in x.lower() if x else False)
                if company_elements:
                    job_data['company'] = company_elements[0].get_text(strip=True)
                if any(keyword in cell_text.lower() for keyword in ['remote', 'usa', 'europe', 'asia', 'worldwide']):
                    job_data['location'] = cell_text
                if any(symbol in cell_text for symbol in ['$', '€', '£', 'k', 'K']) and any(word in cell_text.lower() for word in ['year', 'month', 'hour', 'salary']):
                    job_data['salary'] = cell_text
            if not job_data.get('title') and text_parts:
                for part in text_parts:
                    if len(part) > 5 and not any(skip in part.lower() for skip in ['apply', 'posted', 'ago', 'remote', 'full-time']):
                        job_data['title'] = part
                        break
            if not job_data.get('company') and text_parts and len(text_parts) > 1:
                job_data['company'] = text_parts[1] if len(text_parts[1]) > 2 else text_parts[0]
        except Exception as e:
            logger.error(f"Error extracting web3.career job data: {e}")
        return job_data
    def scrape_jobs_page(self, max_jobs=10):
        all_jobs = []
        page = 1
        while len(all_jobs) < max_jobs:
            page_url = f"{self.base_url}?page={page}" if page > 1 else self.base_url
            logger.info(f"Scraping web3.career page {page}: {page_url}")
            page_content = self.get_page(page_url)
            if not page_content:
                break
            soup = BeautifulSoup(page_content, 'html.parser')
            job_table = soup.find('table', class_='table')
            if not job_table:
                logger.warning(f"No job table found on page {page}")
                break
            job_rows = job_table.find_all('tr', class_='table_row')
            if not job_rows:
                logger.info(f"No more jobs found on page {page}")
                break
            logger.info(f"Found {len(job_rows)} job rows on page {page}")
            page_jobs = []
            for row in job_rows:
                if len(all_jobs) >= max_jobs:
                    break
                job_data = self.extract_job_data(row)
                if job_data and (job_data.get('title') or job_data.get('company')):
                    page_jobs.append(job_data)
                    all_jobs.append(job_data)
                    logger.info(f"Extracted job {len(all_jobs)}: {job_data.get('title', 'Unknown')} at {job_data.get('company', 'Unknown')}")
            if not page_jobs:
                logger.info("No valid jobs found on this page, stopping pagination")
                break
            page += 1
            time.sleep(1)
        return all_jobs[:max_jobs]
class CryptocurrencyJobsScraper(MultiJobScraper):
    def __init__(self, use_selenium=True):
        super().__init__(use_selenium)
        self.base_url = "https://cryptocurrencyjobs.co"
    def extract_job_data(self, job_element):
        job_data = {'source': 'cryptocurrencyjobs.co'}
        try:
            title_links = job_element.find_all('a', href=True)
            for link in title_links:
                link_text = link.get_text(strip=True)
                href = link.get('href', '')
                if len(link_text) > 5 and ('/' in href) and not any(skip in link_text.lower() for skip in ['more', 'apply', 'company']):
                    job_data['title'] = link_text
                    job_data['job_url'] = urljoin(self.base_url, href)
                    break
            company_links = job_element.find_all('a', href=lambda x: x and '/startups/' in x)
            if company_links:
                company_link = company_links[0]
                job_data['company'] = company_link.get_text(strip=True)
                job_data['company_url'] = urljoin(self.base_url, company_link.get('href', ''))
            logo_imgs = job_element.find_all('img')
            for img in logo_imgs:
                src = img.get('src', '')
                if 'logo' in src.lower() or 'company' in src.lower():
                    job_data['company_logo'] = urljoin(self.base_url, src)
                    if not job_data.get('company'):
                        alt_text = img.get('alt', '')
                        if alt_text:
                            job_data['company'] = alt_text.replace(' logo', '').replace(' Logo', '')
                    break
            category_links = job_element.find_all('a', href=lambda x: x and x.startswith('/'))
            categories = []
            for link in category_links:
                link_text = link.get_text(strip=True)
                href = link.get('href', '')
                if (not '/startups/' in href and 
                    not href == job_data.get('job_url', '').replace(self.base_url, '') and 
                    len(link_text) < 20 and len(link_text) > 2):
                    categories.append(link_text)
            if categories:
                job_data['categories'] = categories
                job_data['primary_category'] = categories[0] if categories else None
            text_content = job_element.get_text()
            location_keywords = ['Remote', 'USA', 'Europe', 'Asia', 'Worldwide', 'Global', 'NY', 'SF', 'London']
            for keyword in location_keywords:
                if keyword in text_content:
                    job_data['location'] = keyword
                    break
            salary_pattern = r'\$[\d,]+[\w\s]*(?:K|k|year|month|hour)'
            salary_match = re.search(salary_pattern, text_content)
            if salary_match:
                job_data['salary'] = salary_match.group()
            job_types = ['Full-time', 'Part-time', 'Contract', 'Freelance', 'Internship']
            for job_type in job_types:
                if job_type.lower() in text_content.lower():
                    job_data['job_type'] = job_type
                    break
            date_pattern = r'(\d+d|\d+\s*day|\d+\s*hour|\d+h)'
            date_match = re.search(date_pattern, text_content)
            if date_match:
                job_data['posted_date'] = date_match.group()
        except Exception as e:
            logger.error(f"Error extracting cryptocurrencyjobs.co job data: {e}")
        return job_data
    def scrape_jobs_page(self, max_jobs=10):
        logger.info(f"Scraping jobs from: {self.base_url}")
        page_content = self.get_page(self.base_url, 
                                   wait_for_element='.ais-Hits-item, [data-testid="job-item"], .job-item',
                                   scroll=True)
        if not page_content:
            return []
        soup = BeautifulSoup(page_content, 'html.parser')
        jobs = []
        job_selectors = [
            '.ais-Hits-item',
            '[data-testid="job-item"]',
            '.job-item',
            '.job-listing',
            'article',
            'div[class*="job"]'
        ]
        job_items = []
        for selector in job_selectors:
            items = soup.select(selector)
            if items:
                job_items = items
                logger.info(f"Found {len(job_items)} job items using selector: {selector}")
                break
        if not job_items:
            all_divs = soup.find_all('div')
            for div in all_divs:
                text = div.get_text()
                if (len(text) > 50 and 
                    any(keyword in text.lower() for keyword in ['engineer', 'developer', 'manager', 'analyst', 'designer']) and
                    any(keyword in text.lower() for keyword in ['blockchain', 'crypto', 'web3', 'defi', 'nft'])):
                    job_items.append(div)
            logger.info(f"Fallback found {len(job_items)} potential job items")
        for item in job_items[:max_jobs]:
            if not item.get_text(strip=True):
                continue
            job_data = self.extract_job_data(item)
            if job_data and (job_data.get('title') or job_data.get('company')):
                jobs.append(job_data)
                logger.info(f"Extracted job {len(jobs)}: {job_data.get('title', 'Unknown')} at {job_data.get('company', 'Unknown')}")
        return jobs[:max_jobs]
class CryptoJobsScraper:
    def __init__(self):
        self.web3_scraper = Web3CareerScraper(use_selenium=False)
        self.crypto_scraper = CryptocurrencyJobsScraper(use_selenium=True)
        self.latest_data = {'jobs': [], 'last_update': None}
    def fetch_all_jobs(self):
        logger.info("Fetching all crypto jobs...")
        jobs = []
        try:
            web3_jobs = self.web3_scraper.scrape_jobs_page(max_jobs=10)
            jobs.extend(web3_jobs)
        except Exception as e:
            logger.error(f"Error scraping web3.career: {e}")
        try:
            crypto_jobs = self.crypto_scraper.scrape_jobs_page(max_jobs=10)
            jobs.extend(crypto_jobs)
        except Exception as e:
            logger.error(f"Error scraping cryptocurrencyjobs.co: {e}")
        self.latest_data['jobs'] = jobs
        self.latest_data['last_update'] = datetime.now()
    def save_to_json(self, filename='crypto_jobs.json'):
        def default_serializer(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            return str(obj)
        data_dict = {
            'jobs': self.latest_data['jobs'],
            'last_update': self.latest_data['last_update']
        }
        with open(filename, 'w') as f:
            json.dump(data_dict, f, indent=2, default=default_serializer)
        logger.info(f"Jobs data saved to {filename}")
        return filename
if __name__ == "__main__":
    print("🔄 Starting Crypto Jobs Scraper...")
    scraper = CryptoJobsScraper()
    scraper.fetch_all_jobs()
    filename = scraper.save_to_json()
    print(f"\n✅ Crypto jobs saved to {filename}")
    print(f"Total jobs: {len(scraper.latest_data['jobs'])}")
    print("Script completed successfully!")