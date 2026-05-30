import os
import json
import math
import sqlite3
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from flask import Flask, request, abort, render_template, jsonify
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    ConfirmTemplate,
    ButtonsTemplate,
    CarouselTemplate,
    CarouselColumn,
    ImageCarouselColumn,
    ImageCarouselTemplate,
    PushMessageRequest,
    BroadcastRequest,
    MulticastRequest,
    TextMessage,
    LocationAction,
    TemplateMessage,
    ButtonsTemplate,
    PostbackAction,
    MessageAction,
    DatetimePickerAction,
    QuickReply,
    QuickReplyItem,
    FlexMessage,
    FlexContainer
)

from linebot.v3.webhooks import (
    MessageEvent,
    FollowEvent,
    PostbackEvent,
    TextMessageContent,
    LocationMessageContent
)
from sqlite import init_db

app = Flask(__name__)
# 確保啟動時建立資料表（適用於 gunicorn / WSGI 等執行模式）
try:
    init_db()
except Exception:
    # 若初始化失敗（例如檔案權限或路徑問題），延後處理但不阻塞啟動
    pass
# 從環境變數讀取憑證
CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

geolocator =  Nominatim(user_agent="my_line_foodbot")
DB_NAME=('food_bot.db')

# app.py 內部的函式修改
def get_lat_lng_from_address(address):
    if not address:
        return None, None
        
    try:
        # 1. 自動防呆：將所有的「臺」統一替換成地圖識別率較高的「台」
        formatted_address = address.replace("臺", "台")
        
        # 2. 確保開頭有台灣
        full_query = f"台灣 {formatted_address}" if not formatted_address.startswith("台灣") else formatted_address
        
        print(f"[Debug] 正在嘗試定位地址: {full_query}") # 方便在 Render Logs 看查詢字串
        
        # 3. 進行地圖查詢
        location = geolocator.geocode(full_query, timeout=10)
        
        # 4. 備用方案：如果換成「台」還是查不到，嘗試把「台灣 」字眼拿掉，直接查地址
        if not location:
            fallback_query = formatted_address.replace("台灣", "").strip()
            print(f"[Debug] 第一次嘗試失敗，嘗試備用定位: {fallback_query}")
            location = geolocator.geocode(fallback_query, timeout=10)
            
        if location:
            print(f"[Debug] 定位成功! 緯度: {location.latitude}, 經度: {location.longitude}")
            return location.latitude, location.longitude
            
        print("[Debug] 地圖伺服器查無此地址")
        return None, None
        
    except GeocoderTimedOut:
        print("[Debug] 地圖查詢超時")
        return None, None
    
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371.0 # 地球半徑
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c

@app.route("/liff", methods=['GET'])
def liff_page():
    return render_template('form.html')

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("Invalid signature. Check token and secret.")
        abort(400)

    return 'OK'

@app.route("/add_restaurant",methods=['POST'])
def add_restaurant():
    data=request.get_json()

    if not data:
        return jsonify({"status":"fail","message":"無效的資料"})
    
    name=data.get('name')
    address=data.get('address')
    category = data.get('category')
    price_range = data.get('price_range')
    latitude, longitude=get_lat_lng_from_address(address)

    if latitude is None or longitude is None:
        return jsonify({"status": "fail", "message": "找不到該地址的經緯度，請輸入更詳細的地址！"}), 400

    user_id = data.get('user_id')
    search_radius = data.get('search_radius', 5.0)

    try:
        conn=sqlite3.connect('food_bot.db')
        cursor=conn.cursor()
        if user_id:
            cursor.execute('''
                REPLACE INTO user_settings (user_id, search_radius) VALUES (?, ?)
            ''', (user_id, search_radius))

        cursor.execute('''
                INSERT INTO restaurants (name, address, category, price_range, latitude, longitude, is_favorite)
                VALUES (?,?,?,?,?,?,1)
            ''',(name,address,category,price_range,latitude,longitude))
        conn.commit()
        conn.close()
        return jsonify({"status":"success","message":"成功寫入資料庫"})
    except Exception as e:
        print(f"Database error: {e}")
        return jsonify({"status":"fail","message":str(e)}), 500



# 當收到追蹤（加入好友）事件時的處理邏輯
@handler.add(FollowEvent)
def handle_follow(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        
        # 修正：1. 統一使用 reply_token 2. 文字必須用 TextMessage 包裹
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text="已加入好友，輸入「很餓」來使用機器人！\n(如果沒人使用可能要等約一分鐘才能正常使用)")]
            )
        )


# 當收到文字訊息時的處理邏輯
@handler.add(MessageEvent, message=TextMessageContent)
def message_text(event):
    text = event.message.text
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        
        if text == "很餓":
            # 修正：移除最外層重複的花括號
            line_flex_json = {
                "type": "bubble",
                "hero": {
                    "type": "image",
                    "size": "full",
                    "aspectRatio": "4:3",
                    "aspectMode": "cover",
                    "url": "https://linefoodbot.onrender.com/static/Denia.jpg"
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "您的餐廳小幫手",
                            "weight": "bold",
                            "size": "xl"
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": "解決選擇困難，刻不容緩！",
                                    "size": "sm"
                                }
                            ]
                        }
                    ]
                },
                "footer": {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "button",
                            "action": {
                                "type": "uri",
                                "label": "定位",
                                "uri":"https://line.me/R/nv/location/"
                            },
                            "margin": "md",
                            "style": "primary"
                        },
                        {
                            "type": "button",
                            "action": {
                                "type": "uri",
                                "label": "編輯表單",
                                "uri": "https://liff.line.me/2010226173-gsT146Rp"
                            },
                            "margin": "md"
                        }
                    ]
                }
            }
            
            # 修正：縮排移入 if 內，並改用 from_dict 更安全、簡潔
            flex_content = FlexContainer.from_dict(line_flex_json)
            
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[FlexMessage(alt_text='詳細說明',contents=flex_content)]
                )
            )

@handler.add(MessageEvent, message=LocationMessageContent)
def handle_location(event):
    user_id = event.source.user_id # 取得目前發送定位的使用者 ID
    user_lat = event.message.latitude
    user_lon = event.message.longitude
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 新增：先從資料庫抓取使用者的自訂範圍
    cursor.execute("SELECT search_radius FROM user_settings WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    # 如果使用者從未設定過，預設為 5.0 公里
    max_distance = result[0] if result else 5.0
    
    # 撈取所有餐廳
    cursor.execute("SELECT name, address, category, price_range, latitude, longitude, is_favorite FROM restaurants")
    rows = cursor.fetchall()
    conn.close()
    
    nearby_restaurants = []
    
    for row in rows:
        name, address, category, price, r_lat, r_lon, is_fav = row
        distance = calculate_distance(user_lat, user_lon, r_lat, r_lon)
        
        # 使用動態的 max_distance
        if distance <= max_distance:
            nearby_restaurants.append({
                'name': name, 'address': address, 'category': category,
                'price': price, 'distance': distance, 'is_favorite': is_fav
            })
            
    nearby_restaurants.sort(key=lambda x: (-x['is_favorite'], x['distance']))
    
    if not nearby_restaurants:
        reply_text = f"方圓 {max_distance} 公里內找不到任何您收藏或推薦的餐廳。"
    else:
        reply_text = f"幫您找到附近 {max_distance} 公里內的餐廳（⭐為收藏）：\n\n"
        for idx, res in enumerate(nearby_restaurants[:5], 1):
            fav_tag = "⭐ " if res['is_favorite'] == 1 else ""
            reply_text += f"{idx}. {fav_tag}{res['name']} ({res['category']})\n"
            reply_text += f"   價格: {res['price']} | 距離: {res['distance']:.2f} km\n"
            reply_text += f"   地址: {res['address']}\n\n"
            
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text.strip())]
            )
        )

if __name__ == "__main__":
    # 強制在主程式啟動前建立 user_settings 資料表，徹底杜絕 no such table 錯誤
    try:
        print("--- 開始檢查並強制修復資料表 ---")
        conn = sqlite3.connect('food_bot.db')
        cursor = conn.cursor()
        
        # 補上缺失的 user_settings 資料表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id TEXT PRIMARY KEY,
                search_radius REAL DEFAULT 5.0
            )
        ''')
        conn.commit()
        conn.close()
        print("--- 資料表強制修復成功 ---")
    except Exception as e:
        print(f"--- 強制建立資料表時發生錯誤: {e} ---")

    # 原本的初始化與啟動
    init_db()
    app.run()
