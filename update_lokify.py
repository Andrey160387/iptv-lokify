from playwright.sync_api import sync_playwright
import re
import os
import requests
from datetime import datetime, timezone, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "lokify_playlist.m3u")
LOG_FILE = os.path.join(SCRIPT_DIR, "lokify_log.txt")

# Московский часовой пояс (UTC+3)
MOSCOW_TZ = timezone(timedelta(hours=3))

def log(message):
    time = datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")
    msg = f"[{time}] {message}"
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def click_button(page, text):
    try:
        element = page.locator(f'button:has-text("{text}")').first
        if element.count() > 0:
            element.click()
            log(f"   ✅ Нажата кнопка: '{text}'")
            return True
    except: pass
    
    try:
        element = page.locator(f'a:has-text("{text}")').first
        if element.count() > 0:
            element.click()
            log(f"   ✅ Нажата ссылка: '{text}'")
            return True
    except: pass
    
    try:
        result = page.evaluate(f"""
            () => {{
                const all = document.querySelectorAll('*');
                for (const el of all) {{
                    const t = el.innerText || el.textContent || '';
                    if (t.trim() === '{text}' || t.trim().startsWith('{text}')) {{
                        el.click();
                        return 'ok';
                    }}
                }}
                return null;
            }}
        """)
        if result:
            log(f"   ✅ Нажат элемент (JS): '{text}'")
            return True
    except: pass
    
    log(f"   ❌ '{text}' не найдена")
    return False

def scroll_down(page):
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

def get_lokify_playlist():
    log("="*60)
    log("🚀 Запуск обновления LOKIFY (GitHub Actions)")
    log("="*60)
    
    new_playlist = None
    short_url = None
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-software-rasterizer'
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 13; HONOR 200) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            viewport={"width": 390, "height": 844}
        )
        page = context.new_page()
        
        try:
            log("🌐 Заходим на Lokify...")
            page.goto("https://i.lokify.ru/?screen=trial", timeout=30000)
            page.wait_for_timeout(3000)
            
            page_content = page.content()
            if "Тест 24 часа вам уже выдан" not in page_content:
                log("🖱️ Ищем 'Активировать тест'...")
                if not click_button(page, "Активировать тест"):
                    log("❌ Кнопка не найдена!")
                    browser.close()
                    _save_playlist(None)
                    return
                
                log("⏳ Ждём ссылку...")
                try:
                    page.wait_for_selector("a[href*='lokify.ru/']", timeout=20000)
                except:
                    log("❌ Ссылка не появилась!")
                    browser.close()
                    _save_playlist(None)
                    return
            
            links = page.locator("a[href*='lokify.ru/']").all()
            for link in links:
                href = link.get_attribute("href")
                if re.match(r'https?://lokify\.ru/[a-zA-Z0-9]+', href):
                    short_url = href
                    break
            
            if not short_url:
                log("❌ Ссылка не найдена!")
                browser.close()
                _save_playlist(None)
                return
            
            log(f"🎯 Ссылка: {short_url}")
            
            log("🔗 Переходим по ссылке...")
            page.goto(short_url, timeout=15000)
            page.wait_for_timeout(3000)
            
            log("🍪 Закрываем cookie...")
            click_button(page, "OK")
            page.wait_for_timeout(1000)
            
            log("⬅️ Ищем 'Назад'...")
            scroll_down(page)
            page.wait_for_timeout(1000)
            if not click_button(page, "Назад"):
                page.goto("https://i.lokify.ru/?screen=menu", timeout=15000)
                page.wait_for_timeout(2000)
            
            log("⚙️ Ищем 'Настройка вещания'...")
            if not click_button(page, "Настройка вещания"):
                log("❌ 'Настройка вещания' не найдена!")
                browser.close()
                _save_playlist(None)
                return
            
            log("⏳ Ждём загрузку серверов...")
            page.wait_for_timeout(3000)
            
            log("🌍 Ищем 'Krasnodar'...")
            scroll_down(page)
            page.wait_for_timeout(1000)
            if not click_button(page, "Krasnodar"):
                if not click_button(page, "KRDHLS"):
                    log("❌ Сервер не найден!")
                else:
                    page.wait_for_timeout(2000)
            else:
                page.wait_for_timeout(2000)
            
            log("⬅️ Нажимаем 'Назад'...")
            scroll_down(page)
            page.wait_for_timeout(1000)
            if not click_button(page, "Назад"):
                page.goto("https://i.lokify.ru/?screen=menu", timeout=15000)
                page.wait_for_timeout(2000)
            
            browser.close()
            
            log("📥 Скачиваем плейлист...")
            response = requests.get(short_url, allow_redirects=True, timeout=15,
                                   headers={"User-Agent": "Mozilla/5.0"})
            content = response.text
            
            if '#EXTM3U' in content:
                new_playlist = content
                log(f"✅ Скачан! Каналов: {content.count('#EXTINF')}")
            else:
                log("❌ Не плейлист")
                
        except Exception as e:
            log(f"❌ Ошибка: {e}")
            try:
                browser.close()
            except:
                pass
    
    _save_playlist(new_playlist)

def _save_playlist(new_playlist):
    update_time = datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")
    old_content = ""
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8-sig") as f:
            old_content = f.read()
    
    if new_playlist:
        final_content = new_playlist
        log(f"💾 Сохраняем НОВЫЙ плейлист")
    elif old_content:
        final_content = old_content
        log("⚠️ Оставляем СТАРЫЙ плейлист")
    else:
        log("❌ Нет плейлиста")
        return
    
    with open(OUTPUT_FILE, "w", encoding="utf-8-sig") as f:
        f.write(final_content)
    
    lines = []
    with open(OUTPUT_FILE, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()
    
    for i, line in enumerate(lines):
        if line.startswith('#EXTINF'):
            if ',' in line:
                parts = line.split(',', 1)
                parts[1] = f"🕐 Обновлено (Cloud): {update_time} | {parts[1]}"
                lines[i] = ','.join(parts)
                break
    
    with open(OUTPUT_FILE, "w", encoding="utf-8-sig") as f:
        f.writelines(lines)
    
    log(f"🕐 Обновлено по Москве: {update_time}")
    log(f"💾 Сохранено: {OUTPUT_FILE}")
    log("="*60)

if __name__ == "__main__":
    get_lokify_playlist()
