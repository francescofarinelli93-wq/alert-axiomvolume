import re
from playwright.sync_api import sync_playwright

URL = "https://dexscreener.com/solana?rankBy=trendingScoreM5&order=desc"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
PAT = re.compile(r"5M\s*VOLUME\s*:?\s*\$\s*([\d.,]+)\s*([KMBkmb]?)", re.I)
MOLT = {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}


def cerca(page):
    m = PAT.search(page.inner_text("body"))
    if m:
        val = float(m.group(1).replace(",", "")) * MOLT[m.group(2).upper()]
        return m.group(0).replace("\n", " "), f"{val:,.0f} $"
    return None


with sync_playwright() as p:
    browser = p.chromium.launch(
        args=["--disable-blink-features=AutomationControlled"])
    page = browser.new_context(
        user_agent=UA, viewport={"width": 1280, "height": 900}).new_page()
    page.goto(URL, timeout=45000, wait_until="domcontentloaded")
    try:
        page.wait_for_function(
            "document.body.innerText.toUpperCase().includes('24H VOLUME')",
            timeout=30000)
    except Exception as e:
        print("attesa fallita:", str(e)[:100])
    page.wait_for_timeout(4000)
    print("Titolo:", page.title())

    r = cerca(page)
    if r:
        print("TROVATO subito:", r)
    else:
        a = page.get_by_text("24H", exact=True)
        print("Elementi 24H:", a.count())
        for i in range(min(a.count(), 4)):
            print(i, a.nth(i).evaluate("e => e.outerHTML.slice(0, 160)"))
        try:
            a.first.click(timeout=5000)
            page.wait_for_timeout(2000)
        except Exception as e:
            print("click 24H fallito:", str(e)[:100])
        c = page.get_by_text("5M", exact=True)
        print("Elementi 5M:", c.count())
        for i in range(c.count()):
            try:
                c.nth(i).click(timeout=3000)
                page.wait_for_timeout(4000)
                r = cerca(page)
                print("dopo click", i, "->", r)
                if r:
                    break
            except Exception as e:
                print("click", i, "fallito:", str(e)[:80])

    righe = [x.strip() for x in page.inner_text("body").splitlines()
             if "VOLUME" in x.upper()]
    print("Righe con VOLUME:", righe[:8])
    browser.close()
