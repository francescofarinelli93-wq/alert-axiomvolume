import os, time, requests

SOGLIA = 300_000     # sopra questo volume (5 min) arriva il messaggio CON suono
MODO_TEST = True     # True = a ogni giro un messaggio silenzioso

DEX = "https://api.dexscreener.com"
GECKO = "https://api.geckoterminal.com/api/v2"
TG = f"https://api.telegram.org/bot{os.environ['TG_TOKEN']}/sendMessage"
CHAT = os.environ["TG_CHAT"]

# coppie da escludere (SOL, stablecoin...), non sono memecoin
ESCLUDI = {"SOL", "WSOL", "USDC", "USDT", "USDS", "PYUSD", "JITOSOL",
           "MSOL", "JUPSOL", "BSOL", "WBTC", "WETH", "CBBTC"}


def get(url, params=None):
    for _ in range(3):
        try:
            r = requests.get(url, params=params, timeout=20)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print("errore", url[:70], e)
            time.sleep(2)
    return None


def volume_dex():
    addr = set()
    for p in ["/token-boosts/top/v1", "/token-boosts/latest/v1",
              "/token-profiles/latest/v1"]:
        for t in get(DEX + p) or []:
            if t.get("chainId") == "solana":
                addr.add(t["tokenAddress"])
    addr = list(addr)
    tot, visti = 0.0, set()
    for i in range(0, len(addr), 30):
        url = f"{DEX}/tokens/v1/solana/{','.join(addr[i:i+30])}"
        for p in get(url) or []:
            if p["pairAddress"] in visti:
                continue
            visti.add(p["pairAddress"])
            tot += float((p.get("volume") or {}).get("m5") or 0)
    return tot, len(visti)


def volume_gecko():
    tot, visti = 0.0, set()
    richieste = [(f"{GECKO}/networks/solana/trending_pools", {})]
    for page in range(1, 6):
        richieste.append((f"{GECKO}/networks/solana/pools",
                          {"page": page, "sort": "h24_volume_usd_desc"}))
    for url, params in richieste:
        d = get(url, params)
        time.sleep(1.5)
        for pool in (d or {}).get("data", []):
            a = pool.get("attributes", {})
            base = a.get("name", "").split(" / ")[0].strip().upper()
            if pool["id"] in visti or base in ESCLUDI:
                continue
            visti.add(pool["id"])
            tot += float((a.get("volume_usd") or {}).get("m5") or 0)
    return tot, len(visti)


def invia(testo, silenzioso):
    try:
        r = requests.post(TG, data={
            "chat_id": CHAT,
            "text": testo,
            "disable_notification": "true" if silenzioso else "false",
        }, timeout=20)
        print("Telegram:", r.status_code, r.text[:150])
    except Exception as e:
        print("Telegram errore", e)


dex, n1 = 0.0, 0
gk, n2 = None, 0
try:
    dex, n1 = volume_dex()
except Exception as e:
    print("DexScreener errore", e)
try:
    gk, n2 = volume_gecko()
except Exception as e:
    print("GeckoTerminal errore", e)

valore = max(dex, gk or 0)
print(f"DexScreener: {dex:,.0f} $ ({n1} coppie)")
print(f"GeckoTerminal: {gk if gk is None else format(gk, ',.0f')} $ ({n2} pool)")
print(f"Soglia: {SOGLIA:,}")

testo = f"📊 Volume Solana, ultimi 5 min\nDexScreener: {dex:,.0f} $ ({n1} coppie)"
if gk is not None:
    testo += f"\nGeckoTerminal: {gk:,.0f} $ ({n2} pool)"

if valore >= SOGLIA:
    invia("🚀 MERCATO HOT\n" + testo, False)
elif MODO_TEST:
    invia(testo, True)

