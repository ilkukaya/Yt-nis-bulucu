"""
YouTube Nis Kesif Motoru — Otonom Tarayici
==========================================
Onceden tanimli kategori YOK.
Kendi basina trend analiz eder, viral anomalileri tespit eder,
anahtar kelime cikarir, yeni nisleri kesfeder.

Her calismada onceki kesiflerini hatirlar (discoveries.json)
ve yeni alanlar kesfeder.

Akis:
  1. Trending Harvest — 8 ulkeden trend videolari cek
  2. Viral Anomaly — Kucuk kanal + buyuk izlenme = altin
  3. Keyword Mining — Viral basliklardan anahtar kelime cikar
  4. Snowball Search — Cikan kelimelerle yeni aramalar yap
  5. Niche Clustering — Bulunanlari otomatik grupla
  6. Analysis & Report — CPM, Remotion uyumu, gelir tahmini
"""

import requests, json, os, re, time, smtplib, hashlib, random
from collections import Counter, defaultdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path

# ═══════════ CONFIG ═══════════

YT_API_KEYS = [k.strip() for k in os.environ.get("YT_API_KEYS", "").split(",") if k.strip()]
EMAIL_FROM = os.environ.get("EMAIL_FROM", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
PAGES_URL = os.environ.get("PAGES_URL", "")

BASE_DIR = Path(__file__).parent
DOCS_DIR = BASE_DIR / "docs" / "raporlar"
DOCS_DIR.mkdir(parents=True, exist_ok=True)
MEMORY_FILE = BASE_DIR / "discoveries.json"

SCAN_REGIONS = ["US", "TR", "GB", "DE", "FR", "BR", "IN", "JP"]
DAYS_BACK = 14
MIN_VIRAL_RATIO = 8
MIN_VIEWS = 100_000

YT_CATEGORIES = {
    "1": "Film", "2": "Otomobil", "10": "Muzik", "15": "Hayvanlar",
    "17": "Spor", "19": "Seyahat", "20": "Oyun", "22": "Blog",
    "23": "Komedi", "24": "Eglence", "25": "Haber", "26": "Nasil Yapilir",
    "27": "Egitim", "28": "Bilim Teknoloji",
}

CPM_EST = {
    "finance":       {"US": [12, 30], "GB": [8, 20], "DE": [10, 25], "TR": [1, 3],   "other": [5, 15]},
    "education":     {"US": [6, 15],  "GB": [4, 10], "DE": [5, 12],  "TR": [0.5, 2], "other": [3, 8]},
    "technology":    {"US": [8, 20],  "GB": [5, 14], "DE": [6, 16],  "TR": [0.8, 2], "other": [4, 10]},
    "gaming":        {"US": [3, 8],   "GB": [2, 6],  "DE": [3, 7],   "TR": [0.3, 1], "other": [2, 5]},
    "entertainment": {"US": [3, 8],   "GB": [2, 6],  "DE": [3, 7],   "TR": [0.3, 1], "other": [2, 5]},
    "health":        {"US": [8, 22],  "GB": [5, 14], "DE": [6, 16],  "TR": [0.5, 2], "other": [4, 10]},
    "food":          {"US": [4, 10],  "GB": [3, 8],  "DE": [4, 9],   "TR": [0.4, 1], "other": [2, 6]},
    "travel":        {"US": [5, 12],  "GB": [4, 10], "DE": [5, 11],  "TR": [0.5, 1], "other": [3, 7]},
    "lifestyle":     {"US": [4, 10],  "GB": [3, 8],  "DE": [4, 9],   "TR": [0.4, 1], "other": [2, 6]},
    "quiz":          {"US": [3, 8],   "GB": [2, 6],  "DE": [3, 7],   "TR": [0.3, 1], "other": [2, 5]},
    "unknown":       {"US": [2, 6],   "GB": [1, 5],  "DE": [2, 6],   "TR": [0.2, 1], "other": [1, 4]},
}

TYPE_KW = {
    "finance": ["money","invest","stock","crypto","earn","income","passive","rich","wealth","para","yatirim"],
    "education": ["learn","explain","how to","tutorial","science","history","facts","egitim","bilim"],
    "technology": ["tech","ai","robot","coding","software","gadget","phone","teknoloji","yapay zeka"],
    "gaming": ["game","gaming","minecraft","fortnite","roblox","gta","gameplay","speedrun","oyun"],
    "health": ["health","fitness","workout","diet","mental","yoga","saglik","egzersiz"],
    "food": ["food","recipe","cook","eat","restaurant","taste","yemek","tarif","mutfak"],
    "travel": ["travel","country","city","visit","tourist","seyahat","gezi","ulke"],
    "lifestyle": ["life","motivation","productivity","habit","routine","motivasyon"],
    "quiz": ["quiz","guess","trivia","riddle","puzzle","challenge","test","iq","tahmin","bulmaca","bilgi"],
}

STOP = set("the a an is are was were be been being have has had do does did will would could should may might shall can need to of in for on with at by from as into through during before after above below between out off over under again then once here there when where why how all each every both few more most other some such no nor not only own same so than too very just don now and but or if that this these those what which who whom it its i me my we our you your he him his she her they them their vs part new best top ever never video shorts short watch subscribe like comment share follow click link viral trending official full hd 4k".split())


# ═══════════ API ═══════════

class KM:
    def __init__(self, keys):
        self.keys, self.idx, self.dead = keys, 0, set()
    def get(self):
        if not self.keys: return None
        for _ in range(len(self.keys)):
            if self.idx not in self.dead: return self.keys[self.idx]
            self.idx = (self.idx + 1) % len(self.keys)
        return None
    def exhaust(self):
        self.dead.add(self.idx); self.idx = (self.idx + 1) % len(self.keys)
    @property
    def alive(self): return any(i not in self.dead for i in range(len(self.keys)))

class YT:
    def __init__(self, km):
        self.km, self.base, self.reqs, self.cache = km, "https://www.googleapis.com/youtube/v3", 0, {}

    def _get(self, ep, params, cost=1):
        ck = hashlib.md5(json.dumps({**params, "_": ep}, sort_keys=True).encode()).hexdigest()
        if ck in self.cache: return self.cache[ck]
        key = self.km.get()
        if not key: return None
        params["key"] = key
        try:
            time.sleep(0.5)
            r = requests.get(f"{self.base}/{ep}", params=params, timeout=20)
            self.reqs += 1
            if r.status_code == 200:
                d = r.json(); self.cache[ck] = d; return d
            elif r.status_code == 403 and "quotaExceeded" in r.text:
                print(f"    ! Key #{self.km.idx} kota doldu")
                self.km.exhaust(); del params["key"]; return self._get(ep, params, cost)
            return None
        except: return None

    def trending(self, region="US", cat=None):
        p = {"part": "snippet,statistics,contentDetails", "chart": "mostPopular", "regionCode": region, "maxResults": 50}
        if cat: p["videoCategoryId"] = cat
        d = self._get("videos", p)
        if not d: return []
        ch = self._chs([it["snippet"]["channelId"] for it in d.get("items", [])])
        return [v for it in d["items"] if (v := self._parse(it, ch))]

    def search(self, query, region="US", lang="en", after=None, dur="short", pages=2):
        ids = set()
        for order in ["relevance", "viewCount"]:
            tok = None
            for _ in range(pages):
                p = {"part": "snippet", "q": query, "type": "video", "maxResults": 50, "order": order, "regionCode": region}
                if dur: p["videoDuration"] = dur
                if lang and lang != "all": p["relevanceLanguage"] = lang
                if after: p["publishedAfter"] = after
                if tok: p["pageToken"] = tok
                d = self._get("search", p, 100)
                if not d: break
                for it in d.get("items", []):
                    v = it.get("id", {}).get("videoId")
                    if v: ids.add(v)
                tok = d.get("nextPageToken")
                if not tok: break
        return list(ids)

    def details(self, vids):
        out = []
        for i in range(0, len(vids), 50):
            b = vids[i:i+50]
            d = self._get("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(b)})
            if not d: continue
            ch = self._chs([it["snippet"]["channelId"] for it in d.get("items", [])])
            for it in d["items"]:
                v = self._parse(it, ch)
                if v: out.append(v)
        return out

    def _chs(self, ids):
        ids = list(set(ids)); info = {}
        for i in range(0, len(ids), 50):
            d = self._get("channels", {"part": "statistics", "id": ",".join(ids[i:i+50])})
            if d:
                for it in d.get("items", []):
                    info[it["id"]] = int(it.get("statistics", {}).get("subscriberCount", 0))
        return info

    def _dur(self, iso):
        m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
        return (int(m.group(1) or 0)*3600 + int(m.group(2) or 0)*60 + int(m.group(3) or 0)) if m else 0

    def _parse(self, it, ch):
        try:
            s, sn, c = it.get("statistics", {}), it.get("snippet", {}), it.get("contentDetails", {})
            cid = sn.get("channelId", ""); subs = ch.get(cid, 0)
            views = int(s.get("viewCount", 0)); likes = int(s.get("likeCount", 0))
            comments = int(s.get("commentCount", 0)); dur = self._dur(c.get("duration", "PT0S"))
            vid = it["id"] if isinstance(it["id"], str) else it["id"].get("videoId", "")
            eng = ((likes + comments) / max(views, 1) * 100) if views else 0
            vr = (views / subs) if subs > 0 else 0
            return {"id": vid, "title": sn.get("title", ""), "channel": sn.get("channelTitle", ""),
                    "channel_id": cid, "subs": subs, "views": views, "likes": likes, "comments": comments,
                    "engagement": round(eng, 2), "viral_ratio": round(vr, 2), "published": sn.get("publishedAt", ""),
                    "thumb": sn.get("thumbnails", {}).get("medium", {}).get("url", ""),
                    "duration": dur, "is_shorts": 0 < dur <= 60,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "ch_url": f"https://www.youtube.com/channel/{cid}",
                    "category_id": sn.get("categoryId", ""), "tags": sn.get("tags", []),
                    "description": sn.get("description", "")[:500]}
        except: return None


# ═══════════ KESIF MOTORU ═══════════

class Discovery:
    def __init__(self, yt):
        self.yt = yt
        self.pool = {}
        self.mem = self._load_mem()

    def _load_mem(self):
        if MEMORY_FILE.exists():
            try: return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            except: pass
        return {"explored": [], "run_count": 0}

    def _save_mem(self):
        self.mem["last_run"] = datetime.now().isoformat()
        self.mem["run_count"] = self.mem.get("run_count", 0) + 1
        self.mem["explored"] = self.mem.get("explored", [])[-500:]
        MEMORY_FILE.write_text(json.dumps(self.mem, ensure_ascii=False, indent=2), encoding="utf-8")

    def _add(self, vids):
        for v in vids:
            if v["id"] not in self.pool: self.pool[v["id"]] = v

    # FAZA 1 — Trending
    def p1_trending(self):
        print("\n" + "="*55 + "\n  FAZA 1 — Trending Harvest\n" + "="*55)
        tasks = [(r, None) for r in SCAN_REGIONS]
        for cat in random.sample(list(YT_CATEGORIES.keys()), min(6, len(YT_CATEGORIES))):
            tasks.append((random.choice(["US", "TR", "GB", "DE"]), cat))
        for reg, cat in tasks:
            if not self.yt.km.alive: break
            cn = YT_CATEGORIES.get(cat, "Genel") if cat else "Genel"
            print(f"  [{reg}] {cn}...", end=" ", flush=True)
            vids = self.yt.trending(reg, cat)
            self._add(vids)
            vir = sum(1 for v in vids if v["viral_ratio"] >= MIN_VIRAL_RATIO)
            print(f"{len(vids)} video, {vir} viral")
        print(f"  Havuz: {len(self.pool)} video")

    # FAZA 2 — Viral Anomali
    def p2_anomalies(self):
        print("\n" + "="*55 + "\n  FAZA 2 — Viral Anomali Tespiti\n" + "="*55)
        anom = []
        for v in self.pool.values():
            if (v["viral_ratio"] >= MIN_VIRAL_RATIO and v["views"] >= MIN_VIEWS) or \
               (v["subs"] < 50000 and v["views"] >= 500000) or \
               (v["engagement"] >= 8 and v["views"] >= 50000):
                anom.append(v)
        anom.sort(key=lambda x: x["viral_ratio"], reverse=True)
        print(f"  {len(anom)} anomali")
        for v in anom[:8]:
            print(f"    {v['viral_ratio']:.0f}x | {fmt(v['views'])} | {v['title'][:50]}")
        return anom

    # FAZA 3 — Keyword Mining
    def p3_keywords(self, anom):
        print("\n" + "="*55 + "\n  FAZA 3 — Keyword Mining\n" + "="*55)
        bg, tg = Counter(), Counter()
        sources = anom + [v for v in self.pool.values() if v["viral_ratio"] >= 5]
        for v in sources:
            t = re.sub(r'[^\w\s]', ' ', v["title"].lower())
            ws = [w for w in t.split() if w not in STOP and len(w) > 2 and not w.isdigit()]
            for i in range(len(ws)-1): bg[f"{ws[i]} {ws[i+1]}"] += 1
            for i in range(len(ws)-2): tg[f"{ws[i]} {ws[i+1]} {ws[i+2]}"] += 1
            for tag in v.get("tags", [])[:5]:
                tc = tag.lower().strip()
                if len(tc) > 3 and tc not in STOP: bg[tc] += 1

        explored = set(self.mem.get("explored", []))
        kws = []
        for ph, c in tg.most_common(30):
            if ph not in explored and c >= 2: kws.append(ph)
        for ph, c in bg.most_common(50):
            if ph not in explored and c >= 2: kws.append(ph)

        seen = set(); uniq = []
        for k in kws:
            if k not in seen: seen.add(k); uniq.append(k)
        random.shuffle(uniq)
        uniq = uniq[:30]

        print(f"  {len(uniq)} yeni keyword:")
        for k in uniq[:12]: print(f"    -> {k}")
        if len(uniq) > 12: print(f"    ... +{len(uniq)-12} daha")
        return uniq

    # FAZA 4 — Snowball
    def p4_snowball(self, kws):
        print("\n" + "="*55 + "\n  FAZA 4 — Snowball Kesif\n" + "="*55)
        after = (datetime.now() - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%dT%H:%M:%SZ")
        explored = []
        for kw in kws:
            if not self.yt.km.alive: break
            reg = random.choice(["US", "US", "US", "GB", "TR", "DE"])
            lang = "tr" if reg == "TR" else "en"
            print(f"  [{reg}] '{kw}'...", end=" ", flush=True)
            ids = self.yt.search(kw, reg, lang, after, "short", 1)
            new = [i for i in ids if i not in self.pool]
            if new:
                vids = self.yt.details(new[:50])
                for v in vids: v["discovered_via"] = kw
                self._add(vids)
                vir = sum(1 for v in vids if v["viral_ratio"] >= MIN_VIRAL_RATIO)
                print(f"{len(new)} yeni, {vir} viral")
            else:
                print("(cache)")
            explored.append(kw)
        self.mem.setdefault("explored", []).extend(explored)
        print(f"  Havuz: {len(self.pool)} video")

    # FAZA 5 — Kumeleme
    def p5_cluster(self):
        print("\n" + "="*55 + "\n  FAZA 5 — Nis Kumeleme\n" + "="*55)
        viral = [v for v in self.pool.values() if v["viral_ratio"] >= MIN_VIRAL_RATIO or v["views"] >= MIN_VIEWS]
        if not viral:
            print("  Viral video yok"); return {}

        clusters = defaultdict(list)
        for v in viral:
            tc = re.sub(r'[^\w\s]', ' ', v["title"].lower())
            mt, mx = "unknown", 0
            for ct, kws in TYPE_KW.items():
                m = sum(1 for k in kws if k in tc or k in v.get("description", "").lower())
                if m > mx: mx = m; mt = ct
            v["content_type"] = mt
            dv = v.get("discovered_via", "")
            if dv: clusters[dv].append(v)
            cn = YT_CATEGORIES.get(v.get("category_id", ""), "")
            if cn: clusters[f"[{cn}]"].append(v)
            if mt != "unknown": clusters[f"[{mt}]"].append(v)

        final = {}
        for n, vs in clusters.items():
            if len(vs) >= 2:
                seen = set(); u = []
                for v in vs:
                    if v["id"] not in seen: seen.add(v["id"]); u.append(v)
                u.sort(key=lambda x: x["viral_ratio"], reverse=True)
                final[n] = u

        final = dict(sorted(final.items(), key=lambda x: sum(v["viral_ratio"] for v in x[1])/len(x[1]), reverse=True))
        print(f"  {len(final)} kume:")
        for n, vs in list(final.items())[:12]:
            av = sum(v["viral_ratio"] for v in vs)/len(vs)
            print(f"    {n}: {len(vs)} video, ort. {av:.0f}x viral")
        return final

    # FAZA 6 — Analiz
    def p6_analyze(self, clusters):
        print("\n" + "="*55 + "\n  FAZA 6 — Nis Analizi\n" + "="*55)
        results = []
        for name, vids in list(clusters.items())[:20]:
            types = Counter(v.get("content_type", "unknown") for v in vids)
            mt = types.most_common(1)[0][0]
            cpm = CPM_EST.get(mt, CPM_EST["unknown"])
            av_views = int(sum(v["views"] for v in vids)/len(vids))
            av_subs = int(sum(v["subs"] for v in vids)/len(vids))
            av_vr = sum(v["viral_ratio"] for v in vids)/len(vids)
            av_eng = sum(v["engagement"] for v in vids)/len(vids)
            sh_pct = sum(1 for v in vids if v["is_shorts"])/len(vids)*100
            us_cpm = cpm.get("US", cpm["other"])
            monthly = (av_views * 30 * sum(us_cpm)/2) / 1000
            if av_subs < 5000: comp, cs = "Cok Dusuk", 1
            elif av_subs < 20000: comp, cs = "Dusuk", 2
            elif av_subs < 100000: comp, cs = "Orta", 3
            elif av_subs < 500000: comp, cs = "Yuksek", 4
            else: comp, cs = "Cok Yuksek", 5

            # Remotion uyumu
            tt = " ".join(v["title"].lower() for v in vids)
            qkw = ["quiz","guess","trivia","riddle","puzzle","challenge","test","tahmin","bulmaca","bilgi"]
            fkw = ["facts","things","reasons","ways","tips","did you know","comparison","vs"]
            qm = any(k in tt for k in qkw)
            fm = any(k in tt for k in fkw)
            sh = sh_pct > 50
            if qm and sh: rf = {"s": 10, "l": "Mukemmel Uyum", "n": "Dogrudan Remotion JSON pipeline ile toplu uretilebilir."}
            elif qm or (fm and sh): rf = {"s": 8, "l": "Yuksek Uyum", "n": "Remotion template ile uretilebilir. Kart, timer, skor animasyonlari."}
            elif fm or mt in ["education","quiz"]: rf = {"s": 6, "l": "Uyarlanabilir", "n": "Text kartlari + arka plan gorselleri ile Remotion uretimi mumkun."}
            elif sh: rf = {"s": 4, "l": "Kismi Uyum", "n": "Shorts formati uygun ama ek araclar gerekebilir."}
            else: rf = {"s": 2, "l": "Dusuk Uyum", "n": "Kamera/editing agirlikli. Programatik uretim zor."}

            # Bolge
            regs = Counter()
            for v in vids:
                t = v["title"]
                if any(c in t for c in "cgsouCGSOU"): regs["TR"] += 1
                else: regs["EN"] += 1

            opp = min(monthly/500, 30) + (5-cs)*8 + rf["s"]*4 + min(av_vr/10, 10)

            results.append({"name": name, "type": mt, "count": len(vids), "videos": vids[:10],
                           "av_views": av_views, "av_subs": av_subs, "av_vr": round(av_vr,1),
                           "av_eng": round(av_eng,2), "sh_pct": round(sh_pct), "cpm": cpm,
                           "monthly": round(monthly), "comp": comp, "cs": cs, "rf": rf,
                           "regs": dict(regs), "opp": round(opp)})
            print(f"  {name}: {comp} rek. | ${monthly:,.0f}/ay | {rf['l']}")

        results.sort(key=lambda x: x["opp"], reverse=True)
        return results

    def run(self):
        self.p1_trending()
        anom = self.p2_anomalies()
        kws = self.p3_keywords(anom)
        self.p4_snowball(kws)
        cl = self.p5_cluster()
        res = self.p6_analyze(cl)
        self._save_mem()
        return res


# ═══════════ HELPERS ═══════════

def fmt(n):
    if n >= 1e6: return f"{n/1e6:.1f}M"
    if n >= 1e3: return f"{n/1e3:.1f}K"
    return str(n)


# ═══════════ HTML RAPOR ═══════════

def build_report(analyses, meta):
    d = meta["date_fmt"]; pool = meta["pool"]; viral = meta["viral"]; nc = len(analyses); rq = meta["reqs"]; rn = meta.get("run", "?")

    html = f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nis Kesif #{rn} - {d}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0c0f1a;color:#c8cdd8;line-height:1.6;padding:16px}}
.w{{max-width:1000px;margin:0 auto}}
.hdr{{background:linear-gradient(135deg,#4f46e5,#7c3aed,#ec4899);padding:28px;border-radius:16px;margin-bottom:24px;text-align:center}}
.hdr h1{{font-size:22px;color:#fff;margin-bottom:4px}}
.hdr p{{color:rgba(255,255,255,.75);font-size:13px}}
.hdr .sts{{display:flex;justify-content:center;gap:14px;margin-top:14px;flex-wrap:wrap}}
.hdr .st{{background:rgba(255,255,255,.15);padding:6px 14px;border-radius:10px;font-size:12px;color:#fff}}
.nis{{background:#151929;border:1px solid #1e2640;border-radius:14px;padding:20px;margin-bottom:20px;position:relative;overflow:hidden}}
.nis-rk{{position:absolute;top:0;right:0;background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;padding:6px 16px;border-radius:0 14px 0 12px;font-weight:700;font-size:14px}}
.nis h2{{font-size:17px;color:#e0e4ec;margin-bottom:2px;padding-right:60px}}
.nis-tp{{font-size:12px;color:#7c3aed;margin-bottom:10px}}
.mg{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:12px 0}}
.mc{{background:#1a2035;border-radius:10px;padding:12px}}
.mc label{{display:block;font-size:10px;color:#6b7a94;text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px}}
.mc .vl{{font-size:16px;font-weight:700}}
.mc .sb{{font-size:11px;color:#6b7a94;margin-top:2px}}
.g{{color:#4ade80}} .y{{color:#facc15}} .r{{color:#f87171}} .p{{color:#a78bfa}} .b{{color:#60a5fa}} .wh{{color:#e0e4ec}}
.nt{{background:#1a2035;border-left:3px solid #7c3aed;padding:12px;border-radius:0 10px 10px 0;margin:10px 0;font-size:12px;color:#a0aabe}}
.nt strong{{color:#c4b5fd}}
.ct{{width:100%;border-collapse:collapse;font-size:12px;margin:8px 0}}
.ct th{{text-align:left;padding:6px 10px;background:#1a2035;color:#6b7a94;font-size:10px;text-transform:uppercase}}
.ct td{{padding:6px 10px;border-bottom:1px solid #1e2640}}
.vl{{margin-top:14px}}
.vc{{display:flex;gap:10px;padding:10px;background:#111524;border-radius:10px;margin-bottom:6px}}
.vc img{{width:140px;height:78px;border-radius:8px;object-fit:cover;flex-shrink:0}}
.vi{{flex:1;min-width:0}}
.vi a{{color:#d0d6e2;text-decoration:none;font-weight:600;font-size:12px;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.vi a:hover{{color:#a78bfa}}
.vi .ch{{font-size:11px;color:#6b7a94;margin:2px 0}}
.vi .ms{{display:flex;gap:8px;font-size:10px;color:#8892a8;flex-wrap:wrap}}
.op{{display:inline-block;padding:3px 8px;border-radius:6px;font-size:11px;font-weight:700}}
.oh{{background:#166534;color:#4ade80}} .om{{background:#854d0e;color:#facc15}} .ol{{background:#7f1d1d;color:#f87171}}
.ft{{text-align:center;padding:24px;font-size:11px;color:#4a5568;margin-top:20px}}
@media(max-width:640px){{.mg{{grid-template-columns:1fr 1fr}}.vc img{{width:100px;height:56px}}}}
</style></head><body><div class="w">
<div class="hdr"><h1>Nis Kesif Raporu #{rn}</h1><p>{d} - Otonom tarama, onceden tanimli kategori yok</p>
<div class="sts"><div class="st">{pool:,} video tarandi</div><div class="st">{viral} viral tespit</div>
<div class="st">{nc} nis kesfedildi</div><div class="st">{rq} API istek</div></div></div>
"""

    for rank, a in enumerate(analyses, 1):
        o = a["opp"]; oc = "oh" if o >= 60 else "om" if o >= 35 else "ol"
        ol = "YUKSEK FIRSAT" if o >= 60 else "ORTA FIRSAT" if o >= 35 else "DUSUK FIRSAT"
        cc = "g" if a["cs"] <= 2 else "y" if a["cs"] <= 3 else "r"
        rf = a["rf"]; cpm = a["cpm"]
        crows = "".join(f"<tr><td>{c}</td><td>${r[0]:.1f} - ${r[1]:.1f}</td></tr>" for c, r in cpm.items() if c != "other")
        rg = ", ".join(f"{k}: {v}" for k, v in sorted(a["regs"].items(), key=lambda x: -x[1]))

        html += f"""<div class="nis"><div class="nis-rk">#{rank}</div>
<h2>{a['name']}</h2>
<div class="nis-tp">{a['type'].upper()} - {a['count']} video kesfedildi - <span class="op {oc}">{o}/100 {ol}</span></div>
<div class="mg">
<div class="mc"><label>Ort. Izlenme</label><div class="vl wh">{fmt(a['av_views'])}</div></div>
<div class="mc"><label>Ort. Abone</label><div class="vl wh">{fmt(a['av_subs'])}</div></div>
<div class="mc"><label>Viral Ratio</label><div class="vl p">{a['av_vr']}x</div></div>
<div class="mc"><label>Engagement</label><div class="vl b">{a['av_eng']:.1f}%</div></div>
<div class="mc"><label>Rekabet</label><div class="vl {cc}">{a['comp']}</div></div>
<div class="mc"><label>Shorts</label><div class="vl wh">%{a['sh_pct']}</div></div>
<div class="mc"><label>Aylik Gelir</label><div class="vl g">${a['monthly']:,}</div><div class="sb">US CPM baz</div></div>
<div class="mc"><label>Remotion</label><div class="vl">{rf['l']}</div></div>
</div>
<div class="nt"><strong>Remotion:</strong> {rf['n']}</div>
<div class="nt"><strong>Bolge:</strong> {rg} | <strong>Icerik:</strong> {a['type']}</div>
<table class="ct"><tr><th>Ulke</th><th>CPM Araligi</th></tr>{crows}</table>
"""
        if a["videos"]:
            html += '<div class="vl">'
            for v in a["videos"][:6]:
                tp = "S" if v.get("is_shorts") else "V"
                html += f"""<div class="vc"><img src="{v.get('thumb','')}" loading="lazy">
<div class="vi"><a href="{v['url']}" target="_blank">{v['title'][:70]}</a>
<div class="ch"><a href="{v['ch_url']}" target="_blank">[{tp}] {v['channel']}</a> - {fmt(v['subs'])} abone</div>
<div class="ms"><span>{fmt(v['views'])} izl</span><span>{v['viral_ratio']:.0f}x viral</span><span>{v['engagement']:.1f}% eng</span><span>{fmt(v['likes'])} beg</span></div>
</div></div>"""
            html += '</div>'
        html += '</div>\n'

    html += f'<div class="ft">Nis Kesif Motoru - Otonom Tarama #{rn} - {d}</div></div></body></html>'
    return html


# ═══════════ INDEX + EMAIL + MAIN ═══════════

def save_report(html):
    ts = datetime.now().strftime("%Y%m%d_%H%M"); fn = f"rapor_{ts}.html"
    (DOCS_DIR / fn).write_text(html, encoding="utf-8"); print(f"Rapor: {fn}"); return fn

def update_index():
    reps = sorted(DOCS_DIR.glob("rapor_*.html"), reverse=True)
    rows = ""
    for r in reps[:100]:
        ts = r.stem.replace("rapor_", "")
        try: lb = datetime.strptime(ts, "%Y%m%d_%H%M").strftime("%d.%m.%Y %H:%M")
        except: lb = ts
        rows += f'<tr><td><a href="raporlar/{r.name}">{lb}</a></td><td>{r.stat().st_size/1024:.0f} KB</td></tr>\n'
    idx = f"""<!DOCTYPE html><html lang="tr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nis Kesif</title><style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0c0f1a;color:#c8cdd8;padding:24px}}
.w{{max-width:700px;margin:0 auto}}h1{{font-size:22px;color:#a78bfa;margin-bottom:4px}}p{{color:#6b7a94;margin-bottom:16px;font-size:13px}}
table{{width:100%;border-collapse:collapse}}th{{text-align:left;padding:10px;background:#151929;color:#94a0b8;font-size:11px;text-transform:uppercase}}
td{{padding:10px;border-bottom:1px solid #1e2640;font-size:14px}}a{{color:#a78bfa;text-decoration:none}}a:hover{{text-decoration:underline}}
.e{{color:#4a5568;padding:50px;text-align:center;background:#151929;border-radius:12px}}</style></head>
<body><div class="w"><h1>Nis Kesif Raporlari</h1><p>Otonom YouTube nis tarama</p>
{"<table><tr><th>Tarih</th><th>Boyut</th></tr>"+rows+"</table>" if rows else '<div class="e">Ilk tarama bekleniyor...</div>'}
</div></body></html>"""
    (DOCS_DIR.parent / "index.html").write_text(idx, encoding="utf-8")

def send_email(url, meta):
    if not all([EMAIL_FROM, EMAIL_TO, EMAIL_PASSWORD]): print("Email ayarlari eksik"); return
    subj = f"Nis Kesif #{meta.get('run','?')} - {meta['viral']} viral, {meta['nc']} nis"
    body = f"Yeni rapor:\n{meta['pool']:,} tarandi, {meta['viral']} viral, {meta['nc']} nis\n\n{url}\n\nTum raporlar: {PAGES_URL}"
    try:
        msg = MIMEMultipart(); msg["From"]=EMAIL_FROM; msg["To"]=EMAIL_TO; msg["Subject"]=subj
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as s:
            s.starttls(); s.login(EMAIL_FROM, EMAIL_PASSWORD)
            s.sendmail(EMAIL_FROM, [e.strip() for e in EMAIL_TO.split(",")], msg.as_string())
        print("Email gonderildi")
    except Exception as e: print(f"Email hatasi: {e}")


if __name__ == "__main__":
    print(f"Nis Kesif Motoru | {datetime.now().strftime('%d.%m.%Y %H:%M')} | {len(YT_API_KEYS)} key\n")
    if not YT_API_KEYS: print("YT_API_KEYS tanimli degil!"); exit(1)

    km = KM(YT_API_KEYS); yt = YT(km); eng = Discovery(yt); res = eng.run()
    if not res: print("Hic nis kesfedilemedi."); exit(0)

    viral = sum(a["count"] for a in res)
    meta = {"date_fmt": datetime.now().strftime("%d.%m.%Y %H:%M"), "pool": len(eng.pool),
            "viral": viral, "nc": len(res), "reqs": yt.reqs, "run": eng.mem.get("run_count", 1)}

    html = build_report(res, meta); fn = save_report(html); update_index()
    url = f"{PAGES_URL}/raporlar/{fn}" if PAGES_URL else fn
    send_email(url, {**meta}); print(f"\nRapor: {url}")
