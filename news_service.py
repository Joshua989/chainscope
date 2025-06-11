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
        self.last_fetch_time = None
        self.cache_duration = timedelta(minutes=30)  # Cache for 30 minutes

    def should_fetch_news(self):
        """Check if we should fetch new news based on last fetch time"""
        if not self.last_fetch_time:
            return True
        return datetime.now() - self.last_fetch_time > self.cache_duration

    def fetch_and_store_news(self, force=False):
        """Fetch and store news, with optional force refresh"""
        if not force and not self.should_fetch_news():
            return self.get_cached_news()

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
        
        # Store articles and update last fetch time
        self._store_articles(articles)
        self._store_articles_json(articles)
        self.last_fetch_time = datetime.now()
        
        return articles

    def get_cached_news(self):
        """Get news from cache"""
        try:
            if self.news_file.exists():
                with open(self.news_file, 'r') as f:
                    return json.load(f)
            return []
        except Exception as e:
            print(f"Error reading cached news: {e}")
            return []

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

    def _store_articles(self, articles):
        """Store articles in database with cleanup"""
        try:
            cursor = self.db.cursor()
            
            # Delete old articles (keep last 7 days)
            cursor.execute('''
                DELETE FROM news_articles 
                WHERE created_at < datetime('now', '-7 days')
            ''')
            
            # Insert new articles
            for article in articles:
                normalized = self._normalize_article(article)
                cursor.execute('''
                    INSERT OR REPLACE INTO news_articles 
                    (title, description, url, image_url, source_name, published_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    normalized['title'],
                    normalized['description'],
                    normalized['url'],
                    normalized['image_url'],
                    normalized['source'],
                    normalized['published_at']
                ))
            
            self.db.commit()
        except Exception as e:
            print(f"Error storing articles: {e}")
            self.db.rollback()

    def _store_articles_json(self, articles):
        """Store articles in JSON file"""
        try:
            normalized_articles = [self._normalize_article(a) for a in articles]
            with open(self.news_file, 'w') as f:
                json.dump(normalized_articles, f, default=str)
        except Exception as e:
            print(f"Error storing articles to JSON: {e}")