from apscheduler.schedulers.background import BackgroundScheduler
import requests
import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# LINE bot access tokens
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# 匯率來源與警戒值
EXCHANGE_API = "https://api.exchangerate.fun/latest?base=USD"
THRESHOLD = 29.00  # 低於此值發送警告

# ✅ 群組 ID
GROUP_ID = "C896c2909a2348220effebff19eac1a24"

def get_usd_to_twd():
    try:
        response = requests.get(EXCHANGE_API)
        data = response.json()
        usd_twd = float(data["rates"]["TWD"])
        return round(usd_twd, 4)
    except Exception as e:
        print(f"[ERROR] 匯率查詢失敗: {e}")
        return None

def notify_group(text):
    try:
        line_bot_api.push_message(GROUP_ID, TextSendMessage(text=text))
    except Exception as e:
        print(f"[ERROR] 訊息推播失敗: {e}")

# 每日定時推播
def daily_rate_check():
    rate = get_usd_to_twd()
    if rate:
        print(f"[SCHEDULE] 發送每日匯率：{rate}")
        notify_group(f"📢 今日美元對台幣匯率：{rate}")

# 門檻觸發通知
def threshold_check():
    rate = get_usd_to_twd()
    if rate and rate < THRESHOLD:
        print(f"[SCHEDULE] 匯率跌破門檻：{rate}")
        notify_group(f"⚠️ 美元匯率已低於 {THRESHOLD}：目前為 {rate}")

# 啟動排程器
scheduler = BackgroundScheduler(daemon=True)
for h in range(5):
    scheduler.add_job(daily_rate_check, 'cron', hour=h, minute=0)
scheduler.add_job(threshold_check, 'interval', minutes=30)
scheduler.start()

# Facebook webhook：驗證 + 接收事件
@app.route("/facebook_webhook", methods=['GET', 'POST'])
def facebook_webhook():
    if request.method == 'GET':
        print("[Webhook] Facebook 發起驗證請求")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if token == "hyderson_verify_token":
            print("[Webhook] 驗證成功，回傳 challenge")
            return challenge
        print("[Webhook] 驗證失敗")
        return "驗證失敗", 403

    if request.method == 'POST':
        data = request.get_json()
        print("[Facebook Webhook] 收到事件：", data)

        # 處理貼文通知
        try:
            if data.get("object") == "page":
                for entry in data.get("entry", []):
                    for change in entry.get("changes", []):
                        if change.get("field") == "feed":
                            message = change["value"].get("message", "📰 有新貼文")
                            notify_group(f"📰 Facebook 新貼文：{message}")
        except Exception as e:
            print("[ERROR] webhook 資料處理失敗：", e)

        return "OK", 200

# 健康檢查
@app.route("/")
def home():
    return "LINE Bot is running."

# LINE webhook
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# LINE訊息處理
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    print(f"[DEBUG] 來源：{event.source.type} / ID：{event.source.group_id if event.source.type == 'group' else 'N/A'}")
    msg = event.message.text.strip()
    if msg.lower() == "匯率":
        rate = get_usd_to_twd()
        reply = f"目前美元對台幣匯率：{rate}" if rate else "無法取得匯率資料，請稍後再試。"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply)
        )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
