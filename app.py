import os
import json
import sqlite3
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

app = Flask(__name__)
# 從環境變數讀取憑證
CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

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


# 當收到追蹤（加入好友）事件時的處理邏輯
@handler.add(FollowEvent)
def handle_follow(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        
        # 修正：1. 統一使用 reply_token 2. 文字必須用 TextMessage 包裹
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text="已加入好友，輸入「很餓」來使用機器人！")]
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
                    "action": {
                        "type": "uri",
                        "uri": "https://line.me/"
                    },
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


if __name__ == "__main__":
    app.run()