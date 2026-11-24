import os, time, requests

# ================= IMPOSTAZIONI =================
# Soglie sul volume in dollari degli ultimi 5 minuti, una per fonte.
SOGLIA_DEX = 500_000
SOGLIA_GECKO = 1_000_000
SOGLIA_JUP = 500_000

FONTI_MINIME = 1   # quante fonti devono superare la loro soglia per avere il messaggio
TOP = 100          # coppie/token contate per fonte
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


def riassumi(items):
    # items: lista di (volume_5m, volume_1h); si tengono le prime TOP per volume orario
    sel = sorted(items, key=lambda x: x[1], reverse=True)[:TOP]
    v5 = sum(x[0] for x in sel)
    v1 = sum(x[1] for x in sel)
    norm = max(v1 - v5, 0) / 11
    indice = v5 / norm if norm > 0 else None
    return {"v5": v5, "v1": v1, "n": len(sel), "tot": len(items),
            "indice": indice}


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
        items.append((m5, h1))
        if t.get("id"):
            mints.append(t["id"])
    return riassumi(items), mints


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
            base = a.get("name", "").split(" / ")[0].strip().upper()
            if p["id"] in pool or base in ESCLUDI:
                continue
            v = a.get("volume_usd") or {}
            pool[p["id"]] = (float(v.get("m5") or 0), float(v.get("h1") or 0))
            try:
                bt = p["relationships"]["base_token"]["data"]["id"]
                mints.add(bt.replace("solana_", ""))
            except Exception:
                pass
    if not pool:
        return None, []
    return riassumi(list(pool.values())), list(mints)


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
            coppie[p["pairAddress"]] = (float(v.get("m5") or 0),
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
    return riassumi(list(coppie.values()))


def invia(testo):
    try:
        r = requests.post(TG, data={"chat_id": CHAT, "text": testo}, timeout=20)
        print("Telegram:", r.status_code, r.text[:150])
    except Exception as e:
        print("Telegram errore", e)


def scatta(r, soglia):
    return bool(r) and r["v5"] >= soglia


def riga(emoji, r, soglia):
    if not r:
        return f"{emoji} non disponibile"
    ind = f"×{r['indice']:.1f}" if r["indice"] is not None else "×–"
    fuoco = " 🔥" if scatta(r, soglia) else ""
    return f"{emoji} {r['v5']:,.0f} $ {ind}{fuoco} ({r['tot']})"


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

fonti = [("🦅", "DexScreener", rd, SOGLIA_DEX),
         ("🦎", "GeckoTerminal", rg, SOGLIA_GECKO),
         ("🪐", "Jupiter", rj, SOGLIA_JUP)]
for emoji, nome, r, soglia in fonti:
    if r:
        ind = f"{r['indice']:.2f}" if r["indice"] is not None else "n/d"
        print(f"[log] {nome}: 5min={r['v5']:,.0f} | 1h={r['v1']:,.0f} | "
              f"contati={r['n']}/{r['tot']} | indice={ind} | "
              f"soglia={soglia:,} | scattata={scatta(r, soglia)}")
    else:
        print(f"[log] {nome}: non disponibile")

conta = sum(1 for _, _, r, s in fonti if scatta(r, s))
print(f"[log] fonti sopra soglia: {conta} su 3 (servono {FONTI_MINIME})")

if conta >= FONTI_MINIME:
    righe = [riga(e, r, s) for e, _, r, s in fonti]
    invia("🚀🌪️ SOLANA VOLUME, a 5 min:\n" + "\n".join(righe))
else:
    print("NO ACTION, nessun messaggio")
