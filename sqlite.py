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

    cursor.execute('SELECT COUNT(*) FROM restaurants')
    if cursor.fetchone()[0] == 0:
        test_data = [
            ('美味拉麵屋', '台北市信義區XX路', '日式料理', '$$', 25.033964, 121.564468, 1),
            ('超讚義大利麵', '台北市大安區YY街', '義式料理', '$$$', 25.042123, 121.543210, 1),
            ('巷口乾麵', '台北市信義區ZZ巷', '小吃', '$', 25.035000, 121.567000, 0)
        ]
        cursor.executemany('''
            INSERT INTO restaurants (name, address, category, price_range, latitude, longitude, is_favorite)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', test_data)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
