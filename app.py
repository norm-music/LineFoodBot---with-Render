import os
import json
import math
import sqlite3
import requests
import random
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

TOMTOM_API_KEY = os.environ.get('TOMTOM_API_KEY','kNjrRPh9HSER00naIpR3yR92xEHLdtmO')
DB_NAME=('food_bot.db')

# app.py 內部的函式修改
def get_lat_lng_from_address(address):
    if not address:
        return None, None
        
    try:
        # TomTom 模糊地址搜尋端點
        url = f"https://api.tomtom.com/search/2/geocode/{address}.json"
        
        params = {
            'key': TOMTOM_API_KEY,
            'countrySet': 'TW',    # 限制只搜尋台灣，精準度大暴增
            'language': 'zh-TW',   # 繁體中文
            'limit': 1
        }
        
        print(f"[TomTom Debug] 正在查詢地址: {address}")
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            results_list = result.get('results', [])
            
            if results_list:
                position = results_list[0].get('position', {})
                lat = position.get('lat')
                lng = position.get('lon')
                print(f"[TomTom Debug] 定位成功! lat: {lat}, lng: {lng}")
                return lat, lng
                
        print("[TomTom Debug] 查無此地址的經緯度")
        return None, None
        
    except Exception as e:
        print(f"[TomTom Debug] 查詢時發生錯誤: {e}")
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


        elif text == "查看":
            try:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                # 撈出前 20 筆最新的餐廳
                cursor.execute('SELECT name, category, price_range, address FROM restaurants ORDER BY id DESC LIMIT 20')
                rows = cursor.fetchall()
                conn.close()
            
                if not rows:
                    reply_text = "🍳 目前您的美食資料庫空空如也，趕快打開表單新增第一家餐廳吧！"
                else:
                    reply_text = "📋 【我的收藏餐廳清單】\n"
                    reply_text += "───────────────────\n"
                    for idx, row in enumerate(rows, 1):
                        name, category, price, address = row
                        reply_text += f"{idx}. ✨ {name} ({category})\n"
                        reply_text += f"   價格: {price}\n"
                        reply_text += f"   地址: {address}\n"
                        reply_text += "───────────────────\n"
                    
            except Exception as e:
                reply_text = f"讀取清單時發生錯誤: {e}"
            
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply_text)]
                )
            )
            return 
    
        elif text.startswith("刪除"):
            # 透過切片抓取「刪除」後面的餐廳名稱
            target_restaurant =text[2:].strip()
            
            if not target_restaurant:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text="請輸入正確格式，例如：「刪除 阿裕牛肉湯」")]
                    )
                )
                return
                
            try:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                # 先查看看有沒有這家店
                cursor.execute("SELECT id FROM restaurants WHERE name = ?", (target_restaurant,))
                row = cursor.fetchone()
                
                if row:
                    cursor.execute("DELETE FROM restaurants WHERE name = ?", (target_restaurant,))
                    conn.commit()
                    reply_text = f"❌ 已成功將「{target_restaurant}」從您的收藏中移除！"
                else:
                    reply_text = f"🔍 找不到名為「{target_restaurant}」的餐廳，請確認名稱是否正確。"
                conn.close()
            except Exception as e:
                reply_text = f"刪除資料時發生錯誤: {e}"

            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply_text)]
                )
            )
            return
        # 4. 🫵 新增關鍵字：設定範圍 [數字] (例如輸入：設定範圍 2.5)
        elif text.startswith("設定範圍"):
            # 取得「設定範圍」後面的文字並去除空白
            radius_str = text[4:].strip()
            
            try:
                # 嘗試轉換成浮點數
                new_radius = float(radius_str)
                
                if new_radius <= 0:
                    reply_text = "⚠️ 搜尋範圍必須大於 0 公里喔！"
                elif new_radius > 50:
                    reply_text = "⚠️ 為了查詢效能與精確度，自訂範圍最大請勿超過 50 公里。"
                else:
                    user_id = event.source.user_id
                    
                    # 更新或寫入資料庫
                    conn = sqlite3.connect(DB_NAME)
                    cursor = conn.cursor()
                    cursor.execute('''
                        REPLACE INTO user_settings (user_id, search_radius) VALUES (?, ?)
                    ''', (user_id, new_radius))
                    conn.commit()
                    conn.close()
                    
                    reply_text = f"🎯 設定成功！您目前的預設搜尋範圍已調整為：{new_radius} 公里。"
                    
            except ValueError:
                reply_text = "⚠️ 請輸入正確的數字格式，例如：「設定範圍 2.5」"
            except Exception as e:
                reply_text = f"⚠️ 設定時發生錯誤: {e}"

            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply_text)]
                )
            )
            return
        elif text.startswith("想吃"):
            keyword = text[2:].strip()
            user_id = event.source.user_id
            
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            if keyword == "全部" or keyword == "任何東西":
                cursor.execute("UPDATE user_settings SET current_keyword = NULL WHERE user_id = ?", (user_id,))
                reply_text = "✨ 已清除分類篩選，下一次發送定位將會顯示所有餐廳！"
            else:
                cursor.execute('''
                    REPLACE INTO user_settings (user_id, search_radius, current_keyword)
                    VALUES (?, (SELECT search_radius FROM user_settings WHERE user_id = ?), ?)
                ''', (user_id, user_id, keyword))
                reply_text = f"🔍 已鎖定口味：「{keyword}」！\n現在請點擊下方選單的「定位」按鈕，系統將優先推薦附近的{keyword}餐廳！\n(若想取消篩選，請輸入「想吃 全部」)"
            conn.commit()
            conn.close()
            
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply_text)]))
            return

        # 6. 🫵 新增關鍵字：吃什麼 / 抽籤 / 隨機
        elif text in ["吃什麼", "抽籤", "隨機"]:
            user_id = event.source.user_id
            
            # 設定一個特殊標記 TRIGGER_LUCKY，告知下一次的 handle_location 要走抽籤邏輯
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute('''
                REPLACE INTO user_settings (user_id, search_radius, current_keyword)
                VALUES (?, (SELECT search_radius FROM user_settings WHERE user_id = ?), 'TRIGGER_LUCKY')
            ''', (user_id, user_id))
            conn.commit()
            conn.close()
            
            reply_text = "🎲 抽籤準備就緒！\n請現在點擊下方選單的「定位」按鈕發送位置，天之御中主神將為您指引今天的命定美食！"
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply_text)]))
            return
            

import random  # 🧠 記得在 app.py 最上方確認有沒有 import random

@handler.add(MessageEvent, message=LocationMessageContent)
def handle_location(event):
    user_id = event.source.user_id
    user_lat = event.message.latitude
    user_lon = event.message.longitude
    
    # 1. 從資料庫抓取使用者的自訂範圍與目前想吃的分類關鍵字
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT search_radius, current_keyword FROM user_settings WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    
    max_distance_km = result[0] if (result and result[0]) else 5.0
    filter_keyword = result[1] if (result and result[1]) else None
    
    # 讀取完設定後，如果是單次篩選，我們可以把關鍵字清空，讓下一次定位恢復正常（可選，這裡我們先保留）
    
    # 2. 撈取該使用者在資料庫收藏的所有餐廳
    cursor.execute("SELECT name, category, address FROM restaurants")
    db_rows = cursor.fetchall()
    conn.close()
    
    my_favorites = {row[0]: {"category": row[1], "address": row[2]} for row in db_rows}
    
    # 3. 呼叫 TomTom Category Search API
    api_restaurants = []
    try:
        radius_meters = int(max_distance_km * 1000)
        tomtom_url = f"https://api.tomtom.com/search/2/categorySearch/restaurant.json"
        
        params = {
            'key': TOMTOM_API_KEY,
            'lat': user_lat,
            'lon': user_lon,
            'radius': radius_meters,
            'language': 'zh-TW',
            'countrySet': 'TW',
            'limit': 40  # 提高上限，方便分類篩選時有足夠的樣本
        }
        
        response = requests.get(tomtom_url, params=params, timeout=10)
        if response.status_code == 200:
            search_results = response.json().get('results', [])
            for item in search_results:
                poi = item.get('poi', {})
                name = poi.get('name')
                pos = item.get('position', {})
                r_lat = pos.get('lat')
                r_lon = pos.get('lon')
                
                if name and r_lat and r_lon:
                    distance = calculate_distance(user_lat, user_lon, r_lat, r_lon)
                    address = item.get('address', {}).get('freeformAddress', '未知地址')
                    categories = poi.get('categories', ['餐廳'])
                    category = categories[0] if categories else '餐廳'
                    
                    api_restaurants.append({
                        'name': name, 'address': address, 'category': category, 'distance': distance
                    })
    except Exception as e:
        print(f"[TomTom POI Error]: {e}")
    
    # 4. 混合與比對
    final_list = []
    for res in api_restaurants:
        name = res['name']
        if name in my_favorites:
            res['is_favorite'] = True
            res['category'] = my_favorites[name]['category']
        else:
            res['is_favorite'] = False
        final_list.append(res)
        
    # 5. 進階排序邏輯：加入了「分類篩選項目」
    # 排序優先級：
    # 1. 是否符合使用者指定的分類 (True 排前面)
    # 2. 是否為私房收藏 (True 排前面)
    # 3. 距離遠近 (近的排前面)
    if filter_keyword:
        # 檢查店名或種類是否有包含關鍵字
        final_list.sort(key=lambda x: (
            not (filter_keyword in x['category'] or filter_keyword in x['name']),
            not x['is_favorite'],
            x['distance']
        ))
    else:
        final_list.sort(key=lambda x: (not x['is_favorite'], x['distance']))
        
    # 6. 判斷使用者是否正在進行「隨機抽籤」
    # 我們可以檢查使用者在 user_settings 裡的 current_keyword 是不是特殊的 "TRIGGER_LUCKY"
    is_lucky_draw = (filter_keyword == "TRIGGER_LUCKY")
    
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        
        if not final_list:
            reply_text = f"方圓 {max_distance_km} 公里內找不到任何符合條件的餐廳。"
            if filter_keyword and not is_lucky_draw:
                reply_text += f"\n(目前的分類篩選關鍵字為: {filter_keyword})"
        
        elif is_lucky_draw:
            # 【隨機抽籤模式】從排序前 10 筆（或是總數內）隨機抽一家
            pool = final_list[:10] if len(final_list) >= 10 else final_list
            chosen = random.choice(pool)
            
            fav_tag = "⭐ [您的私房收藏] " if chosen['is_favorite'] else "[地圖熱門餐廳] "
            reply_text = "🧠 幫您算了一卦，今天就吃這家吧！\n"
            reply_text += "───────────────────\n"
            reply_text += f"店名：{fav_tag}{chosen['name']}\n"
            reply_text += f"種類：{chosen['category']}\n"
            reply_text += f"距離：{chosen['distance']:.2f} km\n"
            reply_text += f"地址：{chosen['address']}\n"
            reply_text += "───────────────────\n"
            reply_text += "💬 溫馨提示：抽籤完畢後，系統已自動為您重設狀態。直接再次發送定位即可看完整清單。"
            
            # 抽完籤後，自動將狀態重設
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("UPDATE user_settings SET current_keyword = NULL WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            
        else:
            # 【一般清單模式】
            reply_text = f"幫您找到附近 {max_distance_km} 公里內的餐廳：\n"
            if filter_keyword:
                reply_text += f"🔍 已自動為您篩選關鍵字：「{filter_keyword}」\n"
            reply_text += "（⭐ 代表您的私房收藏）\n\n"
            
            for idx, res in enumerate(final_list[:7], 1):
                fav_tag = "⭐ " if res['is_favorite'] else ""
                reply_text += f"{idx}. {fav_tag}{res['name']} ({res['category']})\n"
                reply_text += f"   距離: {res['distance']:.2f} km\n"
                reply_text += f"   地址: {res['address']}\n"
                reply_text += "───────────────────\n"
                
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text.strip())]
            )
        )

if __name__ == "__main__":
    try:
        print("--- 開始檢查並強制修復資料表 ---")
        conn = sqlite3.connect('food_bot.db')
        cursor = conn.cursor()
        
        # 補上缺失的 user_settings 資料表，並確保有 current_keyword 欄位
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id TEXT PRIMARY KEY,
                search_radius REAL DEFAULT 5.0,
                current_keyword TEXT
            )
        ''')
        
        # 防呆：如果以前建立過舊資料表，嘗試補上欄位避免報錯
        try:
            cursor.execute("ALTER TABLE user_settings ADD COLUMN current_keyword TEXT")
        except sqlite3.OperationalError:
            # 代表欄位本來就存在了，忽略即可
            pass
            
        conn.commit()
        conn.close()
        print("--- 資料表強制修復成功 ---")
    except Exception as e:
        print(f"--- 強制建立資料表時發生錯誤: {e} ---")

    init_db()
    app.run()
