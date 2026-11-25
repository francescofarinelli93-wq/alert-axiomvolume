import os, time, requests

# ================= IMPOSTAZIONI =================
# Soglie sul volume in dollari degli ultimi 5 minuti, una per fonte.
SOGLIA_DEX = 6_500_000
SOGLIA_JUP = 2_500_000

FONTI_MINIME = 1   # quante fonti devono superare la loro soglia (1 o 2)
TOP = 100          # i token con più volume contati per fonte
# ================================================

DEX = "https://api.dexscreener.com"
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
    # items: lista di (token, volume_5m, volume_1h).
    # Le coppie dello stesso token si sommano; poi si tengono i TOP token
    # con più volume orario.
    tok = {}
    for k, m5, h1 in items:
        a = tok.setdefault(k, [0.0, 0.0])
        a[0] += m5
        a[1] += h1
    sel = sorted(tok.values(), key=lambda x: x[1], reverse=True)[:TOP]
    v5 = sum(x[0] for x in sel)
    v1 = sum(x[1] for x in sel)
    norm = max(v1 - v5, 0) / 11
    indice = v5 / norm if norm > 0 else None
    return {"v5": v5, "v1": v1, "n": len(sel), "tot": len(tok),
            "indice": indice}


def jupiter():
    chiave = os.environ.get("JUP_KEY")
    h = {"x-api-key": chiave} if chiave else None
    data = get(f"{JUP}/toptraded/1h", {"limit": 100}, h)
    if not isinstance(data, list):
        return None, []
    items, mints = [], []
    for i, t in enumerate(data):
        s5 = t.get("stats5m") or {}
        s1 = t.get("stats1h") or {}
        m5 = float(s5.get("buyVolume") or 0) + float(s5.get("sellVolume") or 0)
        h1 = float(s1.get("buyVolume") or 0) + float(s1.get("sellVolume") or 0)
        items.append((t.get("id") or f"j{i}", m5, h1))
        if t.get("id"):
            mints.append(t["id"])
    return riassumi(items), mints


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
            tok = bt.get("address") or p["pairAddress"]
            coppie[p["pairAddress"]] = (tok, float(v.get("m5") or 0),
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


def riga(emoji, nome, r, soglia):
    if not r:
        return f"{emoji} {nome}: non disponibile"
    ind = f"×{r['indice']:.1f}" if r["indice"] is not None else "×–"
    fuoco = " 🔥" if scatta(r, soglia) else ""
    return f"{emoji} {nome}: {r['v5']:,.0f} $ {ind}{fuoco} ({r['tot']})"


rj = rd = None
jm = []
try:
    rj, jm = jupiter()
except Exception as e:
    print("Jupiter errore", e)
try:
    rd = dexscreener(set(jm))
except Exception as e:
    print("DexScreener errore", e)

fonti = [("🦅", "Dex", rd, SOGLIA_DEX),
         ("🪐", "Jupiter", rj, SOGLIA_JUP)]
for emoji, nome, r, soglia in fonti:
    if r:
        ind = f"{r['indice']:.2f}" if r["indice"] is not None else "n/d"
        print(f"[log] {nome}: 5min={r['v5']:,.0f} | 1h={r['v1']:,.0f} | "
              f"token contati={r['n']}/{r['tot']} | indice={ind} | "
              f"soglia={soglia:,} | scattata={scatta(r, soglia)}")
    else:
        print(f"[log] {nome}: non disponibile")

conta = sum(1 for _, _, r, s in fonti if scatta(r, s))
print(f"[log] fonti sopra soglia: {conta} su 2 (servono {FONTI_MINIME})")

if conta >= FONTI_MINIME:
    righe = [riga(e, n, r, s) for e, n, r, s in fonti]
    invia("🚀🌪️ SOLANA VOLUME, a 5 min:\n\n" + "\n".join(righe))
else:
    print("NO ACTION, nessun messaggio")
