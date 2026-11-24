import os, time, requests

# ================= IMPOSTAZIONI =================
# Una fonte "scatta" se: volume 5 min >= MIN  E  indice di picco >= MOLT.
# Indice = volume 5 min / volume normale (x1 = norma, x2 = il doppio).
# Il messaggio parte se ALMENO UNA fonte scatta.
# Valori bassi per ora: poi alza MOLT (es. 2) e MIN.
MOLT_DEX, MIN_DEX = 0.5, 10_000
MOLT_GECKO, MIN_GECKO = 0.5, 10_000
MOLT_JUP, MIN_JUP = 0.5, 10_000

# Quante coppie/token contare per fonte (le più scambiate nell'ultima ora)
TOP_DEX = 100
TOP_GECKO = 100
TOP_JUP = 100     # massimo 100
# ================================================

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


def riassumi(items, top):
    # items: lista di (nome, volume_5m, volume_1h)
    sel = sorted(items, key=lambda x: x[2], reverse=True)[:top]
    v5 = sum(x[1] for x in sel)
    v1 = sum(x[2] for x in sel)
    norm = max(v1 - v5, 0) / 11
    indice = v5 / norm if norm > 0 else None
    best, extra = None, 0.0
    for nome, m5, h1 in sel:
        e = m5 - max(h1 - m5, 0) / 11
        if e > extra:
            best, extra = nome, e
    return {"v5": v5, "v1": v1, "n": len(sel), "indice": indice,
            "top": best, "extra": extra}


def jupiter():
    chiave = os.environ.get("JUP_KEY")
    h = {"x-api-key": chiave} if chiave else None
    data = get(f"{JUP}/toptraded/1h", {"limit": 100}, h)
    if not isinstance(data, list):
        return None, []
    items, mints = [], []
    for t in data:
        s5 = t.get("stats5m") or {}
        s1 = t.get("stats1h") or {}
        m5 = float(s5.get("buyVolume") or 0) + float(s5.get("sellVolume") or 0)
        h1 = float(s1.get("buyVolume") or 0) + float(s1.get("sellVolume") or 0)
        items.append((t.get("symbol", "?"), m5, h1))
        if t.get("id"):
            mints.append(t["id"])
    return riassumi(items, TOP_JUP), mints


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
    pool, mints = {}, set()
    for nome, params in richieste:
        d = get(f"{GECKO}/networks/solana/{nome}", params)
        time.sleep(2.2)
        for p in (d or {}).get("data", []):
            a = p.get("attributes", {})
            base = a.get("name", "").split(" / ")[0].strip()
            if p["id"] in pool or base.upper() in ESCLUDI:
                continue
            v = a.get("volume_usd") or {}
            pool[p["id"]] = (base, float(v.get("m5") or 0), float(v.get("h1") or 0))
            try:
                bt = p["relationships"]["base_token"]["data"]["id"]
                mints.add(bt.replace("solana_", ""))
            except Exception:
                pass
    if not pool:
        return None, []
    return riassumi(list(pool.values()), TOP_GECKO), list(mints)


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
            v = p.get("volume") or {}
            coppie[p["pairAddress"]] = (bt.get("symbol", "?"),
                                        float(v.get("m5") or 0),
                                        float(v.get("h1") or 0))
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
    if not coppie:
        return None
    return riassumi(list(coppie.values()), TOP_DEX)


def invia(testo):
    try:
        r = requests.post(TG, data={"chat_id": CHAT, "text": testo}, timeout=20)
        print("Telegram:", r.status_code, r.text[:150])
    except Exception as e:
        print("Telegram errore", e)


def scatta(r, molt, minimo):
    return bool(r) and r["v5"] >= minimo and r["indice"] is not None \
        and r["indice"] >= molt


def riga(emoji, nome, r, molt, minimo):
    if not r:
        return f"⚠️ {emoji} {nome}: non disponibile"
    ind = f"×{r['indice']:.1f}" if r["indice"] is not None else "×n/d"
    fuoco = " 🔥" if scatta(r, molt, minimo) else ""
    testo = f"{emoji} {nome}: {r['v5']:,.0f} $ ({ind}){fuoco}"
    if r["top"]:
        testo += f"\n   ↳ {r['top']} +{r['extra']:,.0f} $"
    return testo


def log(nome, r):
    if not r:
        print(f"[log] {nome}: non disponibile")
        return
    ind = f"{r['indice']:.2f}" if r["indice"] is not None else "n/d"
    print(f"[log] {nome}: 5min={r['v5']:,.0f} | 1h={r['v1']:,.0f} | "
          f"elementi={r['n']} | indice={ind}")


rj = rg = rd = None
jm, gm = [], []
try:
    rj, jm = jupiter()
except Exception as e:
    print("Jupiter errore", e)
try:
    rg, gm = gecko()
except Exception as e:
    print("Gecko errore", e)
try:
    rd = dexscreener(set(jm) | set(gm))
except Exception as e:
    print("DexScreener errore", e)

for nome, r in (("DexScreener", rd), ("GeckoTerminal", rg), ("Jupiter", rj)):
    log(nome, r)

if scatta(rd, MOLT_DEX, MIN_DEX) or scatta(rg, MOLT_GECKO, MIN_GECKO) \
        or scatta(rj, MOLT_JUP, MIN_JUP):
    righe = [riga("🦅", "DexScreener", rd, MOLT_DEX, MIN_DEX),
             riga("🦎", "GeckoTerminal", rg, MOLT_GECKO, MIN_GECKO),
             riga("🪐", "Jupiter", rj, MOLT_JUP, MIN_JUP)]
    invia("🚀 PICCO DI VOLUME, Solana ultimi 5 min\n" + "\n".join(righe))
else:
    print("Nessun picco, nessun messaggio")
