try:
    from newsapi import NewsApiClient
except ImportError:
    import sys
    print("Error: newsapi-python package is not installed")
    print("Please run: pip install newsapi-python==0.2.7")
    sys.exit(1)

import os
import requests  # built-in
import feedparser  # feedparser==6.0.10
from datetime import datetime, timedelta
import requests_cache  # requests-cache==1.1.0
from dateutil import parser  # python-dateutil==2.8.2
import json
from pathlib import Path

# Initialize cache with specific settings
requests_cache.install_cache(
    'news_cache',
    expire_after=1800,
    allowable_methods=('GET', 'POST'),
    backend='sqlite'
)

class NewsService:
    def __init__(self, db_connection):
        self.newsapi = NewsApiClient(api_key='6da8a6b4a99e442fb21a503642ff4f45')
        self.db = db_connection
        self.news_file = Path('static/data/news.json')
        self.news_file.parent.mkdir(parents=True, exist_ok=True)

    def fetch_and_store_news(self):
        print("Starting news fetch...")
        articles = []
        
        # Fetch from NewsAPI
        newsapi_articles = self._fetch_from_newsapi()
        print(f"NewsAPI articles fetched: {len(newsapi_articles)}")
        articles.extend(newsapi_articles)
        
        # Fetch from CryptoPanic
        cryptopanic_articles = self._fetch_from_cryptopanic()
        print(f"CryptoPanic articles fetched: {len(cryptopanic_articles)}")
        articles.extend(cryptopanic_articles)
        
        print(f"Total articles to store: {len(articles)}")
        
        # Store articles in database and JSON file
        self._store_articles(articles)
        self._store_articles_json(articles)

    def _fetch_from_newsapi(self):
        try:
            response = self.newsapi.get_everything(
                q='cryptocurrency OR bitcoin OR ethereum',
                language='en',
                sort_by='publishedAt',
                page_size=5
            )
            return response['articles']
        except Exception as e:
            print(f"NewsAPI Error: {e}")
            return []
            
    def _fetch_from_cryptopanic(self):
        try:
            url = "https://cryptopanic.com/api/v1/posts/"
            params = {
                "auth_token": "92a4cfc4fa857bf2760e9f3a7bb7b65569e5b8f0",
                "kind": "news",
                "filter": "hot",
                "limit": 5
            }
            response = requests.get(url, params=params)
            data = response.json()
            return data['results'][:5]
        except Exception as e:
            print(f"CryptoPanic Error: {e}")
            return []

    def _normalize_article(self, article):
        # Handle different API formats
        if 'publishedAt' in article:  # NewsAPI format
            return {
                'title': article.get('title'),
                'description': article.get('description'),
                'url': article.get('url'),
                'image_url': article.get('urlToImage'),
                'source': article.get('source', {}).get('name'),
                'published_at': parser.parse(article.get('publishedAt'))
            }
        else:  # CryptoPanic format
            return {
                'title': article.get('title'),
                'description': article.get('metadata', {}).get('description'),
                'url': article.get('url'),
                'image_url': article.get('metadata', {}).get('image'),
                'source': article.get('source', {}).get('title'),
                'published_at': parser.parse(article.get('created_at'))
            }