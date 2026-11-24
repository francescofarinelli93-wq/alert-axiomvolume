import re
from playwright.sync_api import sync_playwright

URLS = [
    "https://dexscreener.com/solana/5m",
    "https://dexscreener.com/solana?rankBy=trendingScoreM5&order=desc",
]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def converti(num, unita):
    n = float(num.replace(",", ""))
    return n * {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}[unita.upper()]


with sync_playwright() as p:
    browser = p.chromium.launch(
        args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(user_agent=UA,
                              viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    for url in URLS:
        print("=== Apro", url)
        try:
            page.goto(url, timeout=45000, wait_until="domcontentloaded")
            page.wait_for_function(
                "document.body.innerText.toUpperCase().includes('5M VOLUME')",
                timeout=25000)
        except Exception as e:
            print("attesa fallita:", str(e)[:150])
        testo = page.inner_text("body")
        print("Titolo pagina:", page.title())
        m = re.search(r"5M\s*VOLUME\s*:?\s*\$\s*([\d.,]+)\s*([KMBkmb]?)",
                      testo, re.I)
        if m:
            val = converti(m.group(1), m.group(2))
            print("TROVATO:", m.group(0).replace("\n", " "), "->", f"{val:,.0f} $")
        else:
            print("5M VOLUME non trovato")
            righe = [r for r in testo.splitlines()
                     if "VOLUME" in r.upper() or "moment" in r.lower()]
            print("Righe con VOLUME:", righe[:10])
            print("Inizio pagina:", testo[:300].replace("\n", " | "))
    browser.close()
