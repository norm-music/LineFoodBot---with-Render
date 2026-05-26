import os
from flask import Flask, request, abort

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
    QuickReplyItem
)

from linebot.v3.webhooks import (
    MessageEvent,
    FollowEvent,
    PostbackEvent,
    TextMessageContent
)

app = Flask(__name__)

# 從環境變數讀取憑證（避免將密鑰硬編碼在程式中，更安全）
CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

@app.route("/callback", methods=['POST'])
def callback():
    # 檢查 LINE 的數位簽章，確保請求真的來自 LINE 伺服器
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("Invalid signature. Check token and secret.")
        abort(400)

    return 'OK'

# 當收到文字訊息時的處理邏輯
@handler.add(FollowEvent)
def handle_follow(event):
    print(f'Got {event.type}event')


@handler.add(MessageEvent, message=TextMessageContent)
def message_text(event):
    text = event.message.text
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        
        if text == "很餓":
            url="https://linefoodbot.onrender.com/static/Denia.jpg"
            app.logger.info("url="+url)
            button_template = ButtonsTemplate(
                thumbnail_image_url=url,
                title='您的餐廳小幫手',
                text='解決您的選擇障礙',
                actions=[
                    MessageAction(label="早安", text="早安"),
                    DatetimePickerAction(label='選擇時間', data='時間', mode='datetime'),
                    LocationAction(label="回傳我的位置")
                ])
            template_message= TemplateMessage(
                alt_text="這是選擇機器人",
                template=button_template
            )

            line_bot_api.reply_message(
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[template_message]
                )
            )



if  __name__=="__main__":
    app.run()
