import os, time, requests

# ================= SOGLIE =================
# Volume in dollari negli ultimi 5 minuti.
# Il messaggio parte se ALMENO UNA fonte supera la sua soglia.
SOGLIA_DEX = 10_000       # DexScreener
SOGLIA_GECKO = 100_000    # GeckoTerminal
SOGLIA_JUP = 100_000      # Jupiter
# ==========================================

DEX = "https://api.dexscreener.com"
GECKO = "https://api.geckoterminal.com/api/v2"
JUP = "https://api.jup.ag/tokens/v2"
TG = f"https://api.telegram.org/bot{os.environ['TG_TOKEN']}/sendMessage"
CHAT = os.environ["TG_CHAT"]

SOL = "So11111111111111111111111111111111111111112"
ESCLUDI = {"SOL", "WSOL", "USDC", "USDT", "USDS", "PYUSD", "JITOSOL",
           "MSOL", "JUPSOL", "BSOL", "WBTC", "WETH", "CBBTC"}

LISTE_DEX = ["/token-boosts/top/v1", "/token-boosts/latest/v1",
             "/token-profiles/latest/v1", "/community-takeovers/latest/v1",
             "/ads/latest/v1"]
TERMINI = ["pump", "pumpswap", "raydium", "meteora", "orca", "bonk", "pepe",
           "dog", "cat", "trump", "ai", "agent", "elon", "frog", "moon",
           "baby", "coin", "sol", "meme", "inu", "wif", "fart", "grok",
           "jensen", "gpu"]


def get(url, params=None, headers=None):
    for _ in range(2):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=20)
            if r.status_code == 429:
                time.sleep(5)
                continue
            if r.status_code in (401, 403, 404):
                print("errore", r.status_code, url[:90])
                return None
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print("errore", url[:90], str(e)[:80])
            time.sleep(2)
    return None


def jupiter():
    chiave = os.environ.get("JUP_KEY")
    h = {"x-api-key": chiave} if chiave else None
    data = get(f"{JUP}/toptraded/5m", {"limit": 100}, h)
    if not isinstance(data, list):
        return None, 0, []
    tot, mints = 0.0, []
    for t in data:
        s = t.get("stats5m") or {}
        tot += float(s.get("buyVolume") or 0) + float(s.get("sellVolume") or 0)
        if t.get("id"):
            mints.append(t["id"])
    return tot, len(data), mints


def gecko():
    richieste = []
    for pg in range(1, 4):
        richieste.append(("trending_pools", {"duration": "5m", "page": pg}))
    for pg in range(1, 9):
        richieste.append(("pools", {"page": pg, "sort": "h24_volume_usd_desc"}))
    for pg in range(1, 5):
        richieste.append(("pools", {"page": pg, "sort": "h24_tx_count_desc"}))
    for pg in range(1, 3):
        richieste.append(("new_pools", {"page": pg}))
    tot, visti, mints = 0.0, set(), set()
    for nome, params in richieste:
        d = get(f"{GECKO}/networks/solana/{nome}", params)
        time.sleep(2.2)
        for pool in (d or {}).get("data", []):
            a = pool.get("attributes", {})
            base = a.get("name", "").split(" / ")[0].strip().upper()
            if pool["id"] in visti or base in ESCLUDI:
                continue
            visti.add(pool["id"])
            tot += float((a.get("volume_usd") or {}).get("m5") or 0)
            try:
                bt = pool["relationships"]["base_token"]["data"]["id"]
                mints.add(bt.replace("solana_", ""))
            except Exception:
                pass
    return tot, len(visti), list(mints)


def dexscreener(extra):
    coppie = {}
    indirizzi = set(extra)

    def aggiungi(lista):
        for p in lista or []:
            if p.get("chainId") != "solana" or not p.get("pairAddress"):
                continue
            bt = p.get("baseToken") or {}
            if bt.get("symbol", "").upper() in ESCLUDI:
                continue
            coppie[p["pairAddress"]] = float((p.get("volume") or {}).get("m5") or 0)
            if bt.get("address"):
                indirizzi.add(bt["address"])

    for path in LISTE_DEX:
        for t in get(DEX + path) or []:
            if isinstance(t, dict) and t.get("chainId") == "solana" \
                    and t.get("tokenAddress"):
                indirizzi.add(t["tokenAddress"])
        time.sleep(1.1)
    for q in TERMINI:
        d = get(f"{DEX}/latest/dex/search", {"q": q})
        aggiungi((d or {}).get("pairs"))
        time.sleep(0.3)
    indirizzi.discard(SOL)
    lista = list(indirizzi)[:600]
    for i in range(0, len(lista), 30):
        aggiungi(get(f"{DEX}/tokens/v1/solana/{','.join(lista[i:i+30])}"))
        time.sleep(0.3)
    return sum(coppie.values()), len(coppie)


def invia(testo):
    try:
        r = requests.post(TG, data={"chat_id": CHAT, "text": testo}, timeout=20)
        print("Telegram:", r.status_code, r.text[:150])
    except Exception as e:
        print("Telegram errore", e)


def riga(nome, v, n, soglia, unita):
    if v is None:
        return f"⚠️ {nome}: non disponibile"
    segno = "🔥" if v >= soglia else "▫️"
    return f"{segno} {nome}: {v:,.0f} $ ({n} {unita}), soglia {soglia:,}"


jv = jn = gv = gn = dv = dn = None
jm, gm = [], []
try:
    jv, jn, jm = jupiter()
except Exception as e:
    print("Jupiter errore", e)
try:
    gv, gn, gm = gecko()
except Exception as e:
    print("Gecko errore", e)
try:
    dv, dn = dexscreener(set(jm) | set(gm))
except Exception as e:
    print("DexScreener errore", e)

righe = [
    riga("DexScreener", dv, dn, SOGLIA_DEX, "coppie"),
    riga("GeckoTerminal", gv, gn, SOGLIA_GECKO, "pool"),
    riga("Jupiter", jv, jn, SOGLIA_JUP, "token"),
]
print("\n".join(righe))

scatta = any(v is not None and v >= s for v, s in
             ((dv, SOGLIA_DEX), (gv, SOGLIA_GECKO), (jv, SOGLIA_JUP)))
if scatta:
    invia("🚀 MERCATO HOT, Solana ultimi 5 min\n" + "\n".join(righe))
else:
    print("Nessuna soglia superata, nessun messaggio")
