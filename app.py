from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
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

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def init_db():
    conn = sqlite3.connect('blog.db')
    cursor = conn.cursor()
    
    # Users table
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
    
    # Posts table
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
    
    # Add Chat Messages table
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
    
    # Add Comments table
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
    
    # News Categories table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            description TEXT
        )
    ''')
    
    # News Articles table
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

    # Add Subscribers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Insert default categories
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
        # Get fresh news first
        news = update_news()
        
        if not news:
            # Fallback to database if update fails
            news = conn.execute('''
                SELECT a.*, c.name as category_name, c.slug as category_slug
                FROM news_articles a
                LEFT JOIN news_categories c ON a.category_id = c.id
                ORDER BY a.published_at DESC
                LIMIT 6
            ''').fetchall()
        
        # Get posts with author info and updated_at time
        posts = conn.execute('''
            SELECT p.*, u.username, 
                   COALESCE(p.updated_at, p.created_at) as updated_at
            FROM posts p 
            JOIN users u ON p.author_id = u.id 
            ORDER BY p.created_at DESC
            LIMIT 5
        ''').fetchall()
        
        # Get total user count for stats
        user_count = conn.execute('SELECT COUNT(*) as count FROM users').fetchone()['count']
        
        return render_template('index.html', 
                             posts=posts,
                             news=news,  # Make sure this is included
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
        
        # Handle profile image upload
        profile_image = None
        if 'profile_image' in request.files:
            file = request.files['profile_image']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = str(uuid.uuid4()) + '.' + file.filename.rsplit('.', 1)[1].lower()
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                profile_image = filename
        
        conn = get_db_connection()
        
        # Check if user already exists
        existing_user = conn.execute(
            'SELECT id FROM users WHERE username = ? OR email = ?',
            (username, email)
        ).fetchone()
        
        if existing_user:
            flash('Username or email already exists')
            conn.close()
            return render_template('register.html')
        
        # Create new user with profile image
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
                # Generate unique filename
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
    
    # Fetch all comments for this post
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
                # Delete old image if exists
                if image_filename:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                
                # Save new image
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
    
    # Get all posts with author information
    posts = conn.execute('''
        SELECT p.*, u.username 
        FROM posts p 
        JOIN users u ON p.author_id = u.id 
        ORDER BY p.created_at DESC
    ''').fetchall()
    
    # Get all users
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
    
    # Delete image file if exists
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
    username = request.form.get('username', 'Anonymous')  # Default to 'Anonymous' if no name provided
    
    if not message or not message.strip():
        return jsonify({'error': 'Message cannot be empty'}), 400
    
    conn = get_db_connection()
    # Create anonymous user if needed
    anon_user = conn.execute('SELECT id FROM users WHERE username = "Anonymous"').fetchone()
    if not anon_user:
        conn.execute('''
            INSERT INTO users (username, email, password_hash) 
            VALUES ("Anonymous", "anonymous@example.com", "none")
        ''')
        conn.commit()
        anon_user = conn.execute('SELECT id FROM users WHERE username = "Anonymous"').fetchone()
    
    user_id = session.get('user_id', anon_user['id'])  # Use logged in user ID or anonymous ID
    
    conn.execute('''
        INSERT INTO chat_messages (post_id, user_id, message)
        VALUES (?, ?, ?)
    ''', (post_id, user_id, message.strip()))
    
    # Fetch the just-inserted message
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
        if session.get('user_id'):
            # Logged in user
            user_id = session['user_id']
            username = session['username']
            # Get user's profile image if exists
            conn = get_db_connection()
            user = conn.execute('SELECT profile_image FROM users WHERE id = ?', 
                              (user_id,)).fetchone()
            profile_image = user['profile_image'] if user else None
        else:
            # Anonymous user
            user_id = None
            username = data.get('username') or 'Anonymous'
            profile_image = None

        # Insert comment
        conn = get_db_connection()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute('''
            INSERT INTO comments (post_id, user_id, username, message, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (post_id, user_id, username, message, now))
        conn.commit()
        conn.close()

        # Return comment data for immediate display
        return jsonify({
            'username': username,
            'message': message,
            'created_at': now,
            'profile_image': profile_image
        })
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.before_request
def before_request():
    if not request.is_secure and app.debug is False:
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)

@app.route('/sitemap.xml')
def sitemap():
    pages = []
    ten_days_ago = datetime.now() - timedelta(days=10)
    
    # Add static pages
    pages.append({
        'loc': url_for('index', _external=True),
        'lastmod': datetime.now().strftime('%Y-%m-%d'),
        'changefreq': 'daily',
        'priority': '1.0'
    })
    
    # Add dynamic content pages
    conn = get_db_connection()
    posts = conn.execute('SELECT id, updated_at FROM posts').fetchall()
    for post in posts:
        pages.append({
            'loc': url_for('view_post', post_id=post['id'], _external=True),
            'lastmod': post['updated_at'].strftime('%Y-%m-%d'),
            'changefreq': 'weekly',
            'priority': '0.8'
        })
    
    conn.close()
    return Response(
        render_template('sitemap.xml', pages=pages),
        mimetype='application/xml'
    )

scheduler = BackgroundScheduler()

@app.route('/news')
def news():
    conn = get_db_connection()
    try:
        # Get fresh news first
        news_articles = update_news()
        
        if not news_articles:
            # Fallback to database if update fails
            news_articles = conn.execute('''
                SELECT a.*, c.name as category_name, c.slug as category_slug,
                       datetime(a.published_at) as formatted_date
                FROM news_articles a
                LEFT JOIN news_categories c ON a.category_id = c.id
                ORDER BY a.published_at DESC
                LIMIT 50
            ''').fetchall()
        
        # Get categories with counts
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
        # Get category info
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
        
        # Get articles for this category
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

# Add this function to update news periodically
def update_news():
    with app.app_context():
        conn = get_db_connection()
        try:
            # Fetch fresh news
            news_service = NewsService(conn)
            news_service.fetch_and_store_news()
            
            # Get latest news with category info
            news = conn.execute('''
                SELECT a.*, c.name as category_name, c.slug as category_slug,
                       datetime(a.published_at) as formatted_date
                FROM news_articles a
                LEFT JOIN news_categories c ON a.category_id = c.id
                ORDER BY a.published_at DESC
                LIMIT 12
            ''').fetchall()
            
            return [dict(row) for row in news]  # Convert rows to dictionaries
            
        except Exception as e:
            print(f"Error updating news: {e}")
            return None
        finally:
            conn.close()

# Add this function after your app initialization
def init_app(app):
    # Initialize database
    init_db()
    
    # Initialize news fetch on startup
    with app.app_context():
        update_news()
    
    # Start scheduler for periodic updates
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        func=update_news,
        trigger="interval",
        minutes=30,
        max_instances=1,
        next_run_time=datetime.now()
    )
    scheduler.start()

# Modify the bottom of the file to use init_app:
if __name__ == '__main__':
    init_app(app)
    app.run(debug=True, port=5000)

@app.route('/test_news')
def test_news():
    conn = get_db_connection()
    news_service = NewsService(conn)
    news_service.fetch_and_store_news()
    
    # Fetch stored news
    news = conn.execute('''
        SELECT a.*, c.name as category_name, c.slug as category_slug
        FROM news_articles a
        LEFT JOIN news_categories c ON a.category_id = c.id
        ORDER BY a.published_at DESC
        LIMIT 10
    ''').fetchall()
    
    conn.close()
    
    # Return as JSON for testing
    return jsonify([{
        'title': article['title'],
        'description': article['description'],
        'url': article['url'],
        'source': article['source_name'],
        'category': article['category_name'],
        'published_at': article['published_at']
    } for article in news])

@app.route('/about')
def about():
    """About page route"""
    try:
        conn = get_db_connection()
        # Get some stats for the about page
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

@app.route('/subscribe', methods=['POST'])
def subscribe():
    if not request.form.get('email'):
        return jsonify({'error': 'Email is required'}), 400
        
    email = request.form.get('email')
    
    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO subscribers (email) VALUES (?)', (email,))
        conn.commit()
        return jsonify({'message': 'Successfully subscribed!'})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Email already subscribed'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()