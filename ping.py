import requests
import time
import os

# Твой URL на Render (добавь в Environment Variables)
RENDER_URL = os.getenv("RENDER_URL")

def keep_alive():
    while True:
        try:
            if RENDER_URL:
                response = requests.get(RENDER_URL, timeout=10)
                print(f"✅ Пинг отправлен (статус: {response.status_code})")
            else:
                print("⚠️ RENDER_URL не указан")
            time.sleep(300)  # Пинг каждые 5 минут
        except Exception as e:
            print(f"❌ Ошибка пинга: {e}")
            time.sleep(60)  # Ждем минуту при ошибке

if __name__ == "__main__":
    print("🔄 Запуск пинг-сервиса...")
    keep_alive()
