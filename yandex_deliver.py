import os
import requests
from datetime import datetime, timezone

# === Настройки ===
CAMPAIGN_ID = os.getenv("CAMPAIGN_ID")
OAUTH_TOKEN = os.getenv("OAUTH_TOKEN")
YOUR_APP_URL = os.getenv("YOUR_APP_URL", "https://digital-shop-sfbz.onrender.com")

# Соответствие shopSku → item_id
SKU_TO_ITEM = {
    "contract-pdf-01": 1,
    "license-key-pro": 2,
    # добавьте свои
}

HEADERS = {
    "Authorization": f"OAuth {OAUTH_TOKEN}",
    "Content-Type": "application/json",
}

BASE_URL = "https://api.partner.market.yandex.ru/v2"

def get_processing_orders():
    url = f"{BASE_URL}/campaigns/{CAMPAIGN_ID}/orders.json"
    params = {"status": "PROCESSING"}
    try:
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        return resp.json().get("orders", [])
    except Exception as e:
        print(f"❌ Ошибка получения заказов: {e}")
        return []

def is_order_recent(order):
    updated_at_str = order.get("updatedAt")
    if not updated_at_str:
        return False
    updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return (now - updated_at).total_seconds() < 29 * 60

def deliver_to_yandex(order_id, code, description):
    url = f"{BASE_URL}/campaigns/{CAMPAIGN_ID}/orders/{order_id}/deliverDigitalGoods.json"
    payload = {
        "digitalGoods": [{"code": code, "description": description}]
    }
    try:
        resp = requests.post(url, headers=HEADERS, json=payload)
        if resp.status_code == 200:
            print(f"✅ Отправлено: заказ {order_id}")
            return True
        else:
            print(f"❌ Ошибка отправки {order_id}: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        print(f"💥 Исключение: {e}")
        return False

def main():
    print("🔍 Проверка заказов...")
    orders = get_processing_orders()
    for order in orders:
        order_id = order["id"]
        if not is_order_recent(order):
            print(f"⏰ Старый заказ {order_id} — пропускаем")
            continue

        # Определяем товар
        items = order.get("items", [])
        if not items:
            continue
        shop_sku = items[0].get("shopSku")
        item_id = SKU_TO_ITEM.get(shop_sku)

        if not item_id:
            print(f"⚠️ Неизвестный shopSku: {shop_sku}")
            continue

        # Получаем цифровой товар из вашего приложения
        try:
            api_url = f"{YOUR_APP_URL}/api/deliver/{item_id}"
            resp = requests.get(api_url)
            resp.raise_for_status()
            data = resp.json()
            code = data["code"]
            description = data["description"]
        except Exception as e:
            print(f"❌ Ошибка получения товара {item_id}: {e}")
            continue

        # Отправляем в Яндекс
        deliver_to_yandex(order_id, code, description)

if __name__ == "__main__":
    main()