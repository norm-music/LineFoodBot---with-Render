import sqlite3


def init_db():
    conn = sqlite3.connect('food_bot.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS restaurants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            address TEXT,
            category TEXT,
            price_range TEXT,
            latitude REAL,
            longitude REAL,
            is_favorite INTEGER DEFAULT 1
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id TEXT PRIMARY KEY,
            search_radius REAL DEFAULT 5.0
        )
    ''')
    
    conn.commit()
    conn.close()


