import os, requests

H = "https://api.dexscreener.com"
SOGLIA = 15_000_000

def indirizzi():
    out = set()
    for p in ["/token-boosts/top/v1", "/token-boosts/latest/v1", "/token-profiles/latest/v1"]:
        try:
            for t in requests.get(H + p, timeout=20).json():
                if t.get("chainId") == "solana":
                    out.add(t["tokenAddress"])
        except Exception as e:
            print("errore", p, e)
    return list(out)

def volume_5m():
    tot, visti = 0, set()
    a = indirizzi()
    for i in range(0, len(a), 30):
        url = f"{H}/tokens/v1/solana/{','.join(a[i:i+30])}"
        for p in requests.get(url, timeout=20).json():
            if p["pairAddress"] in visti:
                continue
            visti.add(p["pairAddress"])
            tot += (p.get("volume") or {}).get("m5") or 0
    return tot

v = volume_5m()
print(f"Volume ultimi 5 min: {v:,.0f} $")

if v >= SOGLIA:
    requests.post(
        f"https://api.telegram.org/bot{os.environ['TG_TOKEN']}/sendMessage",
        data={"chat_id": os.environ["TG_CHAT"],
              "text": f"🚀 Volume memecoin Solana (5 min): {v/1e6:.1f} mln $"},
        timeout=20,
    )
