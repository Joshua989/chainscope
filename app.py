from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
from datetime import datetime, timedelta
import uuid
from news_service import NewsService
from apscheduler.schedulers.background import BackgroundScheduler
from pathlib import Path
import json
import threading
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from threading import Thread
from pycoingecko import CoinGeckoAPI
import pandas as pd
import requests
from bs4 import BeautifulSoup
from crypto_launcher import CryptoLauncher
from crypto_data_service import CryptoDataService

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Add email configuration
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME=os.getenv('MAIL_USERNAME'),
    MAIL_PASSWORD=os.getenv('MAIL_PASSWORD'),
    MAIL_DEFAULT_SENDER=('ChainScope', os.getenv('MAIL_USERNAME'))
)

mail = Mail(app)

# Initialize CoinGecko API
cg = CoinGeckoAPI()

# Initialize the CryptoLauncher
crypto_launcher = CryptoLauncher()

# Initialize CryptoDataService
crypto_data_service = CryptoDataService()

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def init_db():
    conn = sqlite3.connect('blog.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            profile_image TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            image_filename TEXT,
            author_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (author_id) REFERENCES users (id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES posts (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER,
            username TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES posts (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            description TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            url TEXT UNIQUE NOT NULL,
            image_url TEXT,
            source_name TEXT,
            category_id INTEGER,
            published_at TIMESTAMP,
            sentiment FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES news_categories (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cryptocurrencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            symbol TEXT NOT NULL,
            current_price REAL NOT NULL,
            description TEXT,
            image_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            added_by INTEGER,
            FOREIGN KEY (added_by) REFERENCES users (id)
        )
    ''')
    
    categories = [
        ('Bitcoin', 'bitcoin', 'Bitcoin related news'),
        ('Ethereum', 'ethereum', 'Ethereum and smart contract news'),
        ('DeFi', 'defi', 'Decentralized Finance news'),
        ('NFTs', 'nfts', 'Non-Fungible Tokens news'),
        ('Regulation', 'regulation', 'Crypto regulations and legal news')
    ]
    
    cursor.executemany(
        'INSERT OR IGNORE INTO news_categories (name, slug, description) VALUES (?, ?, ?)',
        categories
    )
    
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect('blog.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    conn = get_db_connection()
    try:
        # Get latest news with images from CryptoCompare
        news_url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"
        response = requests.get(news_url)
        if response.status_code == 200:
            news_data = response.json()
            news = [
                {
                    'title': article['title'],
                    'description': article['body'],
                    'url': article['url'],
                    'image_url': article['imageurl'],  # Direct image URL
                    'source_name': article['source'],
                    'published_at': datetime.fromtimestamp(article['published_on'])
                }
                for article in news_data['Data'][:6]  # Get top 6 news items
            ]
        else:
            # Fallback to database
            news = conn.execute('''
                SELECT * FROM news_articles
                ORDER BY published_at DESC
                LIMIT 6
            ''').fetchall()
        
        posts = conn.execute('''
            SELECT p.*, u.username, 
                   COALESCE(p.updated_at, p.created_at) as updated_at
            FROM posts p 
            JOIN users u ON p.author_id = u.id 
            ORDER BY p.created_at DESC
            LIMIT 5
        ''').fetchall()
        
        user_count = conn.execute('SELECT COUNT(*) as count FROM users').fetchone()['count']
        
        return render_template('index.html', 
                             posts=posts,
                             news=news,
                             user_count=user_count,
                             meta_title="ChainScope - Cryptocurrency & Blockchain Insights",
                             meta_description="Your source for cryptocurrency insights and blockchain knowledge.")
    
    except Exception as e:
        print(f"Error in index route: {e}")
        return render_template('index.html', 
                             posts=[],
                             news=[],
                             user_count=0,
                             meta_title="ChainScope - Error Loading Content")
    finally:
        conn.close()

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if not username or not email or not password:
            flash('All fields are required')
            return render_template('register.html')
        
        profile_image = None
        if 'profile_image' in request.files:
            file = request.files['profile_image']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = str(uuid.uuid4()) + '.' + file.filename.rsplit('.', 1)[1].lower()
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                profile_image = filename
        
        conn = get_db_connection()
        
        existing_user = conn.execute(
            'SELECT id FROM users WHERE username = ? OR email = ?',
            (username, email)
        ).fetchone()
        
        if existing_user:
            flash('Username or email already exists')
            conn.close()
            return render_template('register.html')
        
        password_hash = generate_password_hash(password)
        conn.execute(
            'INSERT INTO users (username, email, password_hash, profile_image) VALUES (?, ?, ?, ?)',
            (username, email, password_hash, profile_image)
        )
        conn.commit()
        conn.close()
        
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute(
            'SELECT * FROM users WHERE username = ?',
            (username,)
        ).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('Login successful!')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out')
    return redirect(url_for('index'))

@app.route('/create_post', methods=['GET', 'POST'])
def create_post():
    if 'user_id' not in session:
        flash('Please login to create a post')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        
        if not title or not content:
            flash('Title and content are required')
            return render_template('create_post.html')
        
        image_filename = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = str(uuid.uuid4()) + '.' + file.filename.rsplit('.', 1)[1].lower()
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_filename = filename
        
        conn = get_db_connection()
        conn.execute(
            'INSERT INTO posts (title, content, image_filename, author_id) VALUES (?, ?, ?, ?)',
            (title, content, image_filename, session['user_id'])
        )
        conn.commit()
        conn.close()
        
        flash('Post created successfully!')
        
        # Notify subscribers
        try:
            subscribers = conn.execute('SELECT email FROM subscribers').fetchall()
            if subscribers:
                post_url = url_for('view_post', post_id=post_id, _external=True)
                for subscriber in subscribers:
                    html = render_template('email/new_post.html',
                        post=post,
                        post_url=post_url,
                        unsubscribe_url=url_for('unsubscribe',
                            email=subscriber['email'],
                            token=generate_unsubscribe_token(subscriber['email']),
                            _external=True))
                    send_email(f"New Post: {title}", [subscriber['email']], html)
        except Exception as e:
            print(f"Error sending email notifications: {e}")
        
        return redirect(url_for('index'))
    
    return render_template('create_post.html')

@app.route('/post/<int:post_id>')
def view_post(post_id):
    conn = get_db_connection()
    post = conn.execute('''
        SELECT p.*, u.username, u.profile_image
        FROM posts p 
        JOIN users u ON p.author_id = u.id 
        WHERE p.id = ?
    ''', (post_id,)).fetchone()
    
    messages = conn.execute('''
        SELECT c.*, u.profile_image
        FROM comments c
        LEFT JOIN users u ON c.user_id = u.id
        WHERE c.post_id = ?
        ORDER BY c.created_at ASC
    ''', (post_id,)).fetchall()
    
    conn.close()
    
    if not post:
        flash('Post not found')
        return redirect(url_for('index'))
    
    return render_template('post.html', post=post, messages=messages)

@app.route('/edit_post/<int:post_id>', methods=['GET', 'POST'])
def edit_post(post_id):
    if 'user_id' not in session:
        flash('Please login to edit posts')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    post = conn.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()
    
    if not post:
        flash('Post not found')
        conn.close()
        return redirect(url_for('index'))
    
    if post['author_id'] != session['user_id']:
        flash('You can only edit your own posts')
        conn.close()
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        
        if not title or not content:
            flash('Title and content are required')
            conn.close()
            return render_template('edit_post.html', post=post)
        
        image_filename = post['image_filename']
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '' and allowed_file(file.filename):
                if image_filename:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                
                filename = str(uuid.uuid4()) + '.' + file.filename.rsplit('.', 1)[1].lower()
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_filename = filename
        
        conn.execute(
            'UPDATE posts SET title = ?, content = ?, image_filename = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (title, content, image_filename, post_id)
        )
        conn.commit()
        conn.close()
        
        flash('Post updated successfully!')
        return redirect(url_for('view_post', post_id=post_id))
    
    conn.close()
    return render_template('edit_post.html', post=post)

@app.route('/admin')
def admin():
    if 'user_id' not in session:
        flash('Please login to access admin panel')
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    
    posts = conn.execute('''
        SELECT p.*, u.username 
        FROM posts p 
        JOIN users u ON p.author_id = u.id 
        ORDER BY p.created_at DESC
    ''').fetchall()
    
    users = conn.execute('SELECT * FROM users').fetchall()
    
    conn.close()
    
    return render_template('admin.html', posts=posts, users=users)

@app.route('/delete_post/<int:post_id>')
def delete_post(post_id):
    if 'user_id' not in session:
        flash('Please login to delete posts')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    post = conn.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()
    
    if not post:
        flash('Post not found')
        conn.close()
        return redirect(url_for('index'))
    
    if post['author_id'] != session['user_id']:
        flash('You can only delete your own posts')
        conn.close()
        return redirect(url_for('index'))
    
    if post['image_filename']:
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], post['image_filename'])
        if os.path.exists(image_path):
            os.remove(image_path)
    
    conn.execute('DELETE FROM posts WHERE id = ?', (post_id,))
    conn.commit()
    conn.close()
    
    flash('Post deleted successfully!')
    return redirect(url_for('index'))

@app.route('/post/<int:post_id>/send_message', methods=['POST'])
def send_message(post_id):
    message = request.form.get('message')
    username = request.form.get('username', 'Anonymous')
    
    if not message or not message.strip():
        return jsonify({'error': 'Message cannot be empty'}), 400
    
    conn = get_db_connection()
    anon_user = conn.execute('SELECT id FROM users WHERE username = "Anonymous"').fetchone()
    if not anon_user:
        conn.execute('''
            INSERT INTO users (username, email, password_hash) 
            VALUES ("Anonymous", "anonymous@example.com", "none")
        ''')
        conn.commit()
        anon_user = conn.execute('SELECT id FROM users WHERE username = "Anonymous"').fetchone()
    
    user_id = session.get('user_id', anon_user['id'])
    
    conn.execute('''
        INSERT INTO chat_messages (post_id, user_id, message)
        VALUES (?, ?, ?)
    ''', (post_id, user_id, message.strip()))
    
    new_message = conn.execute('''
        SELECT m.*, COALESCE(?, u.username) as username
        FROM chat_messages m
        JOIN users u ON m.user_id = u.id
        WHERE m.id = last_insert_rowid()
    ''', (username if not session.get('user_id') else None,)).fetchone()
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'id': new_message['id'],
        'username': new_message['username'],
        'message': new_message['message'],
        'created_at': new_message['created_at']
    })

@app.route('/post/<int:post_id>/comment', methods=['POST'])
def add_comment(post_id):
    if not request.json or 'message' not in request.json:
        return jsonify({'error': 'No message provided'}), 400
        
    data = request.json
    message = data.get('message').strip()
    
    if not message:
        return jsonify({'error': 'Message cannot be empty'}), 400
    
    try:
        conn = get_db_connection()
        if session.get('user_id'):
            user_id = session['user_id']
            username = session['username']
            user = conn.execute('SELECT profile_image FROM users WHERE id = ?', 
                              (user_id,)).fetchone()
            profile_image = user['profile_image'] if user else None
        else:
            user_id = None
            username = data.get('username') or 'Anonymous'
            profile_image = None

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute('''
            INSERT INTO comments (post_id, user_id, username, message, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (post_id, user_id, username, message, now))
        conn.commit()
        conn.close()

        return jsonify({
            'username': username,
            'message': message,
            'created_at': now,
            'profile_image': profile_image
        })
        
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/news')
def news():
    conn = get_db_connection()
    try:
        news_articles = update_news()
        
        if not news_articles:
            news_articles = conn.execute('''
                SELECT a.*, c.name as category_name, c.slug as category_slug,
                       datetime(a.published_at) as formatted_date
                FROM news_articles a
                LEFT JOIN news_categories c ON a.category_id = c.id
                ORDER BY a.published_at DESC
                LIMIT 50
            ''').fetchall()
        
        categories = conn.execute('''
            SELECT c.*, COUNT(a.id) as article_count
            FROM news_categories c
            LEFT JOIN news_articles a ON c.id = a.category_id
            GROUP BY c.id
            ORDER BY article_count DESC
        ''').fetchall()
        
        return render_template('news.html',
                             categories=categories,
                             articles=news_articles,
                             meta_title="Crypto News - ChainScope",
                             meta_description="Latest cryptocurrency and blockchain news")
                             
    except Exception as e:
        print(f"Error in news route: {e}")
        return render_template('news.html',
                             categories=[],
                             articles=[],
                             meta_title="News - Error Loading Content")
    finally:
        conn.close()

@app.route('/news/category/<slug>')
def news_category(slug):
    conn = get_db_connection()
    try:
        category = conn.execute('''
            SELECT c.*, COUNT(a.id) as article_count
            FROM news_categories c
            LEFT JOIN news_articles a ON c.id = a.category_id
            WHERE c.slug = ?
            GROUP BY c.id
        ''', (slug,)).fetchone()
        
        if not category:
            flash('Category not found')
            return redirect(url_for('news'))
        
        articles = conn.execute('''
            SELECT a.*, c.name as category_name, c.slug as category_slug,
                   datetime(a.published_at) as formatted_date
            FROM news_articles a
            JOIN news_categories c ON a.category_id = c.id
            WHERE c.slug = ?
            ORDER BY a.published_at DESC
            LIMIT 50
        ''', (slug,)).fetchall()
        
        return render_template('news_category.html',
                             category=category,
                             articles=articles,
                             meta_title=f"{category['name']} News - ChainScope",
                             meta_description=f"Latest {category['name']} news and updates")
                             
    except Exception as e:
        print(f"Error in category route: {e}")
        return redirect(url_for('news'))
    finally:
        conn.close()

@app.route('/about')
def about():
    try:
        conn = get_db_connection()
        stats = {
            'user_count': conn.execute('SELECT COUNT(*) FROM users').fetchone()[0],
            'post_count': conn.execute('SELECT COUNT(*) FROM posts').fetchone()[0],
            'comment_count': conn.execute('SELECT COUNT(*) FROM comments').fetchone()[0]
        }
        conn.close()
        
        return render_template('about.html',
                             title="About ChainScope",
                             meta_title="About ChainScope - Our Story",
                             meta_description="Learn about ChainScope's mission to provide insightful cryptocurrency and blockchain analysis.",
                             stats=stats)
    except Exception as e:
        print(f"Error loading about page: {e}")
        return render_template('about.html',
                             title="About ChainScope",
                             meta_title="About ChainScope - Our Story",
                             meta_description="Learn about ChainScope's mission to provide insightful cryptocurrency and blockchain analysis.",
                             stats=None)

@app.route('/contact')
def contact():
    return render_template('contact.html',
                         title="Contact Us",
                         meta_title="Contact ChainScope - Get in Touch",
                         meta_description="Contact ChainScope for inquiries, partnerships, or support.")

@app.route('/privacy')
def privacy():
    return render_template('privacy.html',
                         title="Privacy Policy",
                         meta_title="Privacy Policy - ChainScope",
                         meta_description="ChainScope privacy policy and data protection information.")

@app.route('/terms')
def terms():
    return render_template('terms.html',
                         title="Terms of Service",
                         meta_title="Terms of Service - ChainScope",
                         meta_description="ChainScope terms of service and user agreement.")

@app.route('/blog')
def blog():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    
    conn = get_db_connection()
    try:
        posts = conn.execute('''
            SELECT p.*, u.username, u.profile_image,
                   COALESCE(p.updated_at, p.created_at) as updated_at
            FROM posts p 
            JOIN users u ON p.author_id = u.id 
            ORDER BY p.created_at DESC
            LIMIT ? OFFSET ?
        ''', (per_page, offset)).fetchall()
        
        total_posts = conn.execute('SELECT COUNT(*) FROM posts').fetchone()[0]
        
        return render_template('blog.html',
                             posts=posts,
                             page=page,
                             total_posts=total_posts,
                             per_page=per_page,
                             title="Blog Posts",
                             meta_title="Blog - ChainScope",
                             meta_description="Read the latest blog posts about cryptocurrency and blockchain technology.")
    finally:
        conn.close()

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        flash('Please login to view your profile')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    try:
        user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        
        user_posts = conn.execute('''
            SELECT p.*, COUNT(c.id) as comment_count
            FROM posts p
            LEFT JOIN comments c ON p.id = c.post_id
            WHERE p.author_id = ?
            GROUP BY p.id
            ORDER BY p.created_at DESC
        ''', (session['user_id'],)).fetchall()
        
        return render_template('profile.html',
                             user=user,
                             posts=user_posts,
                             title="My Profile",
                             meta_title="Profile - ChainScope",
                             meta_description="Manage your ChainScope profile and posts.")
    finally:
        conn.close()

def send_async_email(app, msg):
    with app.app_context():
        try:
            mail.send(msg)
        except Exception as e:
            print(f"Error sending email: {e}")

def send_email(subject, recipients, html_body):
    msg = Message(subject, recipients=recipients, html=html_body)
    Thread(target=send_async_email, args=(app, msg)).start()

def generate_unsubscribe_token(email):
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return serializer.dumps(email, salt='unsubscribe-salt')

# Update the subscribe route
@app.route('/subscribe', methods=['POST'])
def subscribe():
    email = request.form.get('email')
    if not email:
        return jsonify({'error': 'Email is required'}), 400

    conn = get_db_connection()
    try:
        # Check if already subscribed
        existing = conn.execute('SELECT 1 FROM subscribers WHERE email = ?', (email,)).fetchone()
        if existing:
            return jsonify({'error': 'Email already subscribed'}), 400

        # Add to subscribers
        conn.execute('INSERT INTO subscribers (email) VALUES (?)', (email,))
        conn.commit()

        # Send welcome email
        welcome_html = render_template('email/welcome.html',
            unsubscribe_url=url_for('unsubscribe', 
                email=email, 
                token=generate_unsubscribe_token(email),
                _external=True))
        send_email('Welcome to ChainScope', [email], welcome_html)

        return jsonify({'message': 'Successfully subscribed! Check your email for confirmation.'})
    except Exception as e:
        print(f"Error in subscribe: {e}")
        return jsonify({'error': 'An error occurred'}), 500
    finally:
        conn.close()

# Add unsubscribe route
@app.route('/unsubscribe')
def unsubscribe():
    email = request.args.get('email')
    token = request.args.get('token')
    
    if not email or not token:
        flash('Invalid unsubscribe link')
        return redirect(url_for('index'))
    
    try:
        serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
        email_check = serializer.loads(token, salt='unsubscribe-salt', max_age=86400)
        
        if email != email_check:
            raise ValueError('Invalid token')
            
        conn = get_db_connection()
        conn.execute('DELETE FROM subscribers WHERE email = ?', (email,))
        conn.commit()
        conn.close()
        
        flash('Successfully unsubscribed from notifications')
    except:
        flash('Invalid or expired unsubscribe link')
    
    return redirect(url_for('index'))

@app.route('/sitemap.xml')
def sitemap():
    pages = []
    ten_days_ago = datetime.now() - timedelta(days=10)
    
    pages.append({
        'loc': url_for('index', _external=True),
        'lastmod': datetime.now().strftime('%Y-%m-%d'),
        'changefreq': 'daily',
        'priority': '1.0'
    })
    
    pages.append({
        'loc': url_for('about', _external=True),
        'lastmod': datetime.now().strftime('%Y-%m-%d'),
        'changefreq': 'monthly',
        'priority': '0.8'
    })
    
    pages.append({
        'loc': url_for('news', _external=True),
        'lastmod': datetime.now().strftime('%Y-%m-%d'),
        'changefreq': 'daily',
        'priority': '0.9'
    })
    
    pages.append({
        'loc': url_for('blog', _external=True),
        'lastmod': datetime.now().strftime('%Y-%m-%d'),
        'changefreq': 'daily',
        'priority': '0.9'
    })
    
    conn = get_db_connection()
    posts = conn.execute('SELECT id, updated_at FROM posts').fetchall()
    for post in posts:
        pages.append({
            'loc': url_for('view_post', post_id=post['id'], _external=True),
            'lastmod': post['updated_at'].strftime('%Y-%m-%d') if post['updated_at'] else datetime.now().strftime('%Y-%m-%d'),
            'changefreq': 'weekly',
            'priority': '0.8'
        })
    
    conn.close()
    return Response(
        render_template('sitemap.xml', pages=pages),
        mimetype='application/xml'
    )

@app.route('/test_news')
def test_news():
    conn = get_db_connection()
    news_service = NewsService(conn)
    news_service.fetch_and_store_news()
    
    news = conn.execute('''
        SELECT a.*, c.name as category_name, c.slug as category_slug
        FROM news_articles a
        LEFT JOIN news_categories c ON a.category_id = c.id
        ORDER BY a.published_at DESC
        LIMIT 10
    ''').fetchall()
    
    conn.close()
    
    return jsonify([{
        'title': article['title'],
        'description': article['description'],
        'url': article['url'],
        'source': article['source_name'],
        'category': article['category_name'],
        'published_at': article['published_at']
    } for article in news])

@app.before_request
def before_request():
    if not request.is_secure and app.debug is False:
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)

def update_news():
    conn = get_db_connection()
    try:
        # Fetch latest news from CryptoCompare
        news_url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"
        response = requests.get(news_url)
        if response.status_code == 200:
            news_data = response.json()
            news = [
                {
                    'title': article['title'],
                    'description': article['body'],
                    'url': article['url'],
                    'image_url': article['imageurl'],
                    'source_name': article['source'],
                    'published_at': datetime.fromtimestamp(article['published_on'])
                }
                for article in news_data['Data']
            ]
            
            # Store or update news in the database
            for article in news:
                conn.execute('''
                    INSERT INTO news_articles (title, description, url, image_url, source_name, published_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(url) DO UPDATE SET
                        title = excluded.title,
                        description = excluded.description,
                        image_url = excluded.image_url,
                        source_name = excluded.source_name,
                        published_at = excluded.published_at,
                        updated_at = CURRENT_TIMESTAMP
                ''', (article['title'], article['description'], article['url'], article['image_url'], article['source_name'], article['published_at']))
            
            conn.commit()
            
            return news
        
        return None
    
    except Exception as e:
        print(f"Error updating news: {e}")
        return None
    finally:
        conn.close()

def init_app(app):
    init_db()
    
    with app.app_context():
        update_news()
    
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        func=update_news,
        trigger="interval",
        minutes=30,
        max_instances=1,
        next_run_time=datetime.now()
    )
    scheduler.start()

def get_new_token_launches():
    return crypto_launcher.get_new_launches()

@app.route('/crypto-news')
def crypto_news():
    conn = get_db_connection()
    try:
        # Force refresh crypto launches data
        launches = crypto_launcher.get_new_launches(force_refresh=True)
        
        # Get latest news with images from CryptoCompare
        news_url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"
        response = requests.get(news_url)
        if response.status_code == 200:
            news_data = response.json()
            news_articles = [
                {
                    'title': article['title'],
                    'description': article['body'],
                    'url': article['url'],
                    'image_url': article['imageurl'],
                    'source_name': article['source'],
                    'published_at': datetime.fromtimestamp(article['published_on'])
                }
                for article in news_data['Data'][:12]
            ]
        else:
            news_articles = []

        # Get fresh market data
        crypto_data = cg.get_coins_markets(
            vs_currency='usd',
            order='market_cap_desc',
            per_page=50,
            sparkline=True,
            price_change_percentage='24h,7d,30d'
        )
        
        # Get fresh trending data
        trending = cg.get_search_trending()
        
        # Get fresh global data
        global_data = cg.get_global()
        
        # Get fresh fear and greed index
        fear_greed_response = requests.get('https://api.alternative.me/fng/')
        fear_greed = fear_greed_response.json() if fear_greed_response.status_code == 200 else None

        return render_template(
            'crypto_news.html',
            news=news_articles,
            crypto_data=crypto_data,
            trending=trending['coins'][:5] if trending else [],
            global_data=global_data,
            fear_greed=fear_greed['data'][0] if fear_greed else None,
            launches=launches,
            last_updated=launches.get('last_updated', 'N/A')
        )
        
    except Exception as e:
        print(f"Error in crypto news route: {e}")
        return render_template(
            'crypto_news.html',
            error="Unable to load crypto data",
            meta_title="Crypto News - Error"
        )
    finally:
        conn.close()

@app.route('/add_cryptocurrency', methods=['POST'])
def add_cryptocurrency():
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401

    try:
        name = request.form.get('name')
        symbol = request.form.get('symbol')
        price = request.form.get('price')
        description = request.form.get('description')
        image_url = request.form.get('image_url')

        if not all([name, symbol, price]):
            return jsonify({'error': 'Name, symbol and price are required'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Add new cryptocurrency
        cursor.execute('''
            INSERT INTO cryptocurrencies (
                name, symbol, current_price, description, image_url, 
                created_at, updated_at, added_by
            ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
        ''', (name, symbol, price, description, image_url, session['user_id']))

        conn.commit()
        conn.close()

        return jsonify({'message': 'Cryptocurrency added successfully'}), 200

    except Exception as e:
        print(f"Error adding cryptocurrency: {e}")
        return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    init_app(app)
    app.run(debug=True, port=5000)