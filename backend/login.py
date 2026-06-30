from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        channel="chrome",                    # ← запускает твой обычный Chrome
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-default-browser-check"
        ]
    )
    
    context = browser.new_context(
        viewport={"width": 1280, "height": 720}
    )
    page = context.new_page()
    
    page.goto("https://x.com/login")
    
    input("\n>>> Залогинься в аккаунт в открывшемся Chrome.\n>>> После успешного входа нажми Enter здесь...\n")
    
    context.storage_state(path="auth.json")
    print("✅ auth.json успешно создан!")
    browser.close()