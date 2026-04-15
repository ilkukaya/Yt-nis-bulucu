"""
YouTube Nis Kesif Motoru — Faceless Remotion Edition
=====================================================
Sadece Ingilizce pazarlar. Sadece faceless, JSON->Remotion ile
programatik uretilebilen nisler. Kamera/edit gerektiren icerik filtrelenir.

Akis:
  1. Trending — US, GB, CA, AU trendleri
  2. Viral Anomali — Kucuk kanal + buyuk izlenme
  3. Keyword Mining — Viral basliklardan faceless keyword cikar
  4. Snowball — Yeni aramalar
  5. Faceless Filtre — Sadece programatik uretilebilenleri tut
  6. Analiz — CPM, gelir, Remotion notu
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

# SADECE INGILIZCE YUKSEK CPM PAZARLAR
SCAN_REGIONS = ["US", "GB", "CA", "AU"]
DAYS_BACK = 14
MIN_VIRAL_RATIO = 8
MIN_VIEWS = 100_000

YT_CATEGORIES = {
    "1": "Film", "10": "Music", "15": "Animals", "17": "Sports",
    "20": "Gaming", "22": "Vlogs", "23": "Comedy", "24": "Entertainment",
    "25": "News", "26": "How-to", "27": "Education", "28": "Science & Tech",
}

# Faceless icerik belirteçleri — bunlar IYIDIR
FACELESS_SIGNALS = [
    "quiz", "guess", "trivia", "riddle", "puzzle", "challenge", "test your",
    "can you name", "can you guess", "how many", "only genius", "impossible",
    "would you rather", "this or that", "higher or lower", "pick one",
    "spot the difference", "find the odd", "find the hidden", "odd one out",
    "facts", "did you know", "things you", "reasons why", "psychology",
    "comparison", "vs", "versus", "which is", "bigger than",
    "tier list", "ranking", "top 10", "top 5", "countdown",
    "history of", "evolution of", "timeline", "explained",
    "ai voice", "tts", "text to speech", "ai generated",
    "what if", "how much", "how many", "percentage", "probability",
    "never have i ever", "true or false", "myth or fact",
    "name the", "identify", "recognize", "fill in the blank",
    "emoji", "flag", "logo", "silhouette", "shadow", "country",
    "price guess", "age guess", "before and after",
    "satisfying", "asmr", "compilation", "montage",
]

# Bu icerikler FILTRELENIR — faceless degildir
EXCLUDE_SIGNALS = [
    "vlog", "day in my life", "get ready with me", "grwm", "morning routine",
    "haul", "unboxing", "room tour", "house tour", "mukbang",
    "cover song", "singing", "guitar", "piano", "dance",
    "prank", "reaction video", "reacting to", "i tried",
    "storytime", "my story", "personal", "family", "boyfriend", "girlfriend",
    "wedding", "baby", "pregnancy", "travel vlog", "hotel review",
    "cooking with", "recipe with me", "baking",
    "workout with", "exercise routine", "yoga flow",
    "makeup tutorial", "skincare", "fashion", "outfit",
    "podcast", "interview", "talking to",
    "live stream", "livestream", "stream highlights",
]

# Turkce / non-Latin karakter tespiti
def is_english(text):
    if not text: return False
    latin = sum(1 for c in text if c.isascii() or c in ' .-!?#0123456789')
    return latin / max(len(text), 1) > 0.85

def is_faceless_compatible(title, tags=None, desc=""):
    """Bu video faceless/programatik uretilebilir mi?"""
    t = title.lower()
    d = (desc or "").lower()
    all_text = f"{t} {d}"

    # Exclude sinyalleri
    for sig in EXCLUDE_SIGNALS:
        if sig in all_text:
            return False

    # Faceless sinyalleri
    for sig in FACELESS_SIGNALS:
        if sig in all_text:
            return True

    # Tag kontrolu
    if tags:
        tag_text = " ".join(tags).lower()
        for sig in FACELESS_SIGNALS:
            if sig in tag_text:
                return True

    return False

# CPM — yuksek odenmeli pazarlar
CPM_EST = {
    "finance":       {"US": [12, 30], "GB": [8, 20], "CA": [10, 22], "AU": [8, 18]},
    "education":     {"US": [6, 15],  "GB": [4, 10], "CA": [5, 12],  "AU": [4, 10]},
    "technology":    {"US": [8, 20],  "GB": [5, 14], "CA": [6, 15],  "AU": [5, 12]},
    "gaming":        {"US": [3, 8],   "GB": [2, 6],  "CA": [3, 7],   "AU": [2, 6]},
    "entertainment": {"US": [3, 8],   "GB": [2, 6],  "CA": [3, 7],   "AU": [2, 6]},
    "health":        {"US": [8, 22],  "GB": [5, 14], "CA": [6, 16],  "AU": [5, 12]},
    "food":          {"US": [4, 10],  "GB": [3, 8],  "CA": [4, 9],   "AU": [3, 8]},
    "quiz":          {"US": [3, 8],   "GB": [2, 6],  "CA": [3, 7],   "AU": [2, 6]},
    "unknown":       {"US": [2, 6],   "GB": [1, 5],  "CA": [2, 5],   "AU": [1, 5]},
}

TYPE_KW = {
    "finance": ["money","invest","stock","crypto","earn","income","passive","rich","wealth","budget"],
    "education": ["learn","explain","how to","tutorial","science","history","facts","psychology"],
    "technology": ["tech","ai","robot","coding","software","gadget","phone"],
    "gaming": ["game","gaming","minecraft","fortnite","roblox","gta","gameplay","speedrun"],
    "health": ["health","fitness","workout","diet","mental","yoga","sleep"],
    "food": ["food","recipe","cook","eat","restaurant","taste"],
    "quiz": ["quiz","guess","trivia","riddle","puzzle","challenge","test","iq","emoji","flag","logo"],
}

STOP = set("the a an is are was were be been being have has had do does did will would could should may might shall can need to of in for on with at by from as into through during before after above below between out off over under again then once here there when where why how all each every both few more most other some such no nor not only own same so than too very just don now and but or if that this these those what which who whom it its i me my we our you your he him his she her they them their vs part new best top most ever never video shorts short watch subscribe like comment share follow click link viral trending official full hd 4k".split())


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

    def search(self, query, region="US", after=None, dur="short", pages=2):
        ids = set()
        for order in ["relevance", "viewCount"]:
            tok = None
            for _ in range(pages):
                p = {"part": "snippet", "q": query, "type": "video", "maxResults": 50,
                     "order": order, "regionCode": region, "relevanceLanguage": "en"}
                if dur: p["videoDuration"] = dur
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
            title = sn.get("title", "")
            tags = sn.get("tags", [])
            desc = sn.get("description", "")[:500]
            return {"id": vid, "title": title, "channel": sn.get("channelTitle", ""),
                    "channel_id": cid, "subs": subs, "views": views, "likes": likes, "comments": comments,
                    "engagement": round(eng, 2), "viral_ratio": round(vr, 2), "published": sn.get("publishedAt", ""),
                    "thumb": sn.get("thumbnails", {}).get("medium", {}).get("url", ""),
                    "duration": dur, "is_shorts": 0 < dur <= 60,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "ch_url": f"https://www.youtube.com/channel/{cid}",
                    "category_id": sn.get("categoryId", ""), "tags": tags, "description": desc}
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
            # SADECE INGILIZCE icerik
            if not is_english(v["title"]):
                continue
            self.pool[v["id"]] = v

    # FAZA 1 — Trending (sadece EN pazarlar)
    def p1_trending(self):
        print("\n" + "="*55 + "\n  FAZA 1 — Trending (US/GB/CA/AU only)\n" + "="*55)
        tasks = [(r, None) for r in SCAN_REGIONS]
        for cat in random.sample(list(YT_CATEGORIES.keys()), min(5, len(YT_CATEGORIES))):
            tasks.append((random.choice(SCAN_REGIONS), cat))
        for reg, cat in tasks:
            if not self.yt.km.alive: break
            cn = YT_CATEGORIES.get(cat, "General") if cat else "General"
            print(f"  [{reg}] {cn}...", end=" ", flush=True)
            vids = self.yt.trending(reg, cat)
            self._add(vids)
            print(f"{len(vids)} found, pool={len(self.pool)}")
        print(f"  Pool: {len(self.pool)} English videos")

    # FAZA 2 — Viral Anomali
    def p2_anomalies(self):
        print("\n" + "="*55 + "\n  FAZA 2 — Viral Anomalies\n" + "="*55)
        anom = []
        for v in self.pool.values():
            if (v["viral_ratio"] >= MIN_VIRAL_RATIO and v["views"] >= MIN_VIEWS) or \
               (v["subs"] < 50000 and v["views"] >= 500000) or \
               (v["engagement"] >= 8 and v["views"] >= 50000):
                anom.append(v)
        anom.sort(key=lambda x: x["viral_ratio"], reverse=True)
        print(f"  {len(anom)} anomalies")
        for v in anom[:8]:
            fc = "✓" if is_faceless_compatible(v["title"], v.get("tags"), v.get("description")) else "✗"
            print(f"    {fc} {v['viral_ratio']:.0f}x | {fmt(v['views'])} | {v['title'][:55]}")
        return anom

    # FAZA 3 — Keyword Mining (faceless-biased)
    def p3_keywords(self, anom):
        print("\n" + "="*55 + "\n  FAZA 3 — Keyword Mining (faceless focus)\n" + "="*55)

        # Sadece faceless-uyumlu videolardan keyword cikar
        faceless_vids = [v for v in anom if is_faceless_compatible(v["title"], v.get("tags"), v.get("description"))]
        # Fallback: tum anomalilerden de al ama faceless oncelikli
        sources = faceless_vids + [v for v in self.pool.values()
                                    if v["viral_ratio"] >= 5
                                    and is_faceless_compatible(v["title"], v.get("tags"), v.get("description"))]

        bg, tg = Counter(), Counter()
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
        for ph, c in tg.most_common(40):
            if ph not in explored and c >= 2: kws.append(ph)
        for ph, c in bg.most_common(60):
            if ph not in explored and c >= 2: kws.append(ph)

        seen = set(); uniq = []
        for k in kws:
            if k not in seen: seen.add(k); uniq.append(k)
        random.shuffle(uniq)
        uniq = uniq[:35]

        # Eger cok az faceless keyword bulunduysa, seed ekle
        if len(uniq) < 10:
            seeds = ["guess the country", "emoji quiz challenge", "would you rather",
                     "spot the difference", "higher or lower", "psychology facts",
                     "did you know facts", "true or false quiz", "odd one out",
                     "guess the logo", "guess the animal", "fill in the blank",
                     "comparison video", "tier list ranking", "price guess challenge",
                     "never have i ever", "general knowledge quiz", "history facts",
                     "science facts", "which is bigger"]
            random.shuffle(seeds)
            for s in seeds:
                if s not in explored and s not in seen:
                    uniq.append(s)
                    seen.add(s)
                    if len(uniq) >= 25: break

        print(f"  {len(uniq)} keywords (faceless-filtered):")
        for k in uniq[:12]: print(f"    -> {k}")
        if len(uniq) > 12: print(f"    ... +{len(uniq)-12} more")
        return uniq

    # FAZA 4 — Snowball (English only)
    def p4_snowball(self, kws):
        print("\n" + "="*55 + "\n  FAZA 4 — Snowball Discovery\n" + "="*55)
        after = (datetime.now() - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%dT%H:%M:%SZ")
        explored = []
        for kw in kws:
            if not self.yt.km.alive: break
            reg = random.choice(["US", "US", "US", "GB", "CA", "AU"])  # US agirlikli
            print(f"  [{reg}] '{kw}'...", end=" ", flush=True)
            ids = self.yt.search(kw, reg, after, "short", 1)
            new = [i for i in ids if i not in self.pool]
            if new:
                vids = self.yt.details(new[:50])
                for v in vids: v["discovered_via"] = kw
                self._add(vids)  # is_english filtresi burada
                print(f"{len(new)} new, pool={len(self.pool)}")
            else:
                print("(cache)")
            explored.append(kw)
        self.mem.setdefault("explored", []).extend(explored)

    # FAZA 5 — Faceless Clustering
    def p5_cluster(self):
        print("\n" + "="*55 + "\n  FAZA 5 — Faceless Clustering\n" + "="*55)

        # SERT FILTRE: sadece faceless-uyumlu + viral + Ingilizce
        viral = [v for v in self.pool.values()
                 if (v["viral_ratio"] >= MIN_VIRAL_RATIO or v["views"] >= MIN_VIEWS)
                 and is_english(v["title"])
                 and is_faceless_compatible(v["title"], v.get("tags"), v.get("description"))]

        print(f"  {len(viral)} faceless viral videos (filtered from {len(self.pool)} pool)")

        if not viral:
            print("  ! No faceless viral videos found")
            return {}

        clusters = defaultdict(list)
        for v in viral:
            tc = v["title"].lower()
            mt, mx = "unknown", 0
            for ct, kws in TYPE_KW.items():
                m = sum(1 for k in kws if k in tc or k in v.get("description", "").lower())
                if m > mx: mx = m; mt = ct
            v["content_type"] = mt

            dv = v.get("discovered_via", "")
            if dv: clusters[dv].append(v)
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
        print(f"  {len(final)} faceless niches:")
        for n, vs in list(final.items())[:12]:
            av = sum(v["viral_ratio"] for v in vs)/len(vs)
            print(f"    {n}: {len(vs)} videos, avg {av:.0f}x viral")
        return final

    # FAZA 6 — Analiz
    def p6_analyze(self, clusters):
        print("\n" + "="*55 + "\n  FAZA 6 — Analysis\n" + "="*55)
        results = []
        for name, vids in list(clusters.items())[:25]:
            types = Counter(v.get("content_type", "unknown") for v in vids)
            mt = types.most_common(1)[0][0]
            cpm = CPM_EST.get(mt, CPM_EST["unknown"])
            av_views = int(sum(v["views"] for v in vids)/len(vids))
            av_subs = int(sum(v["subs"] for v in vids)/len(vids))
            av_vr = sum(v["viral_ratio"] for v in vids)/len(vids)
            av_eng = sum(v["engagement"] for v in vids)/len(vids)
            sh_pct = sum(1 for v in vids if v["is_shorts"])/len(vids)*100
            us_cpm = cpm.get("US", [2, 6])
            monthly = (av_views * 30 * sum(us_cpm)/2) / 1000

            if av_subs < 5000: comp, cs = "Very Low", 1
            elif av_subs < 20000: comp, cs = "Low", 2
            elif av_subs < 100000: comp, cs = "Medium", 3
            elif av_subs < 500000: comp, cs = "High", 4
            else: comp, cs = "Very High", 5

            # Remotion uyumu — faceless filtresi zaten yapildi, detay ver
            tt = " ".join(v["title"].lower() for v in vids)
            qkw = ["quiz","guess","trivia","riddle","puzzle","challenge","test","emoji","flag","logo","animal","food","country"]
            fkw = ["facts","things","reasons","ways","did you know","comparison","vs","tier","ranking"]
            wkw = ["would you rather","this or that","pick one","higher lower","never have"]
            skw = ["spot","find","odd one","hidden","difference"]

            if any(k in tt for k in qkw):
                rf = {"s": 10, "l": "PERFECT FIT",
                      "n": "JSON soru bankasi -> Remotion quiz template -> toplu video uretimi. Soru/cevap/timer/skor animasyonlari."}
                rf_type = "quiz"
            elif any(k in tt for k in wkw):
                rf = {"s": 10, "l": "PERFECT FIT",
                      "n": "Iki secenek karti + timer + sonuc. JSON ile sinirsiz kombinasyon. Yuksek yorum orani."}
                rf_type = "interactive"
            elif any(k in tt for k in skw):
                rf = {"s": 9, "l": "PERFECT FIT",
                      "n": "Grid gorsel + highlight animasyonu. Remotion ile programatik uretim, replay degeri yuksek."}
                rf_type = "visual_puzzle"
            elif any(k in tt for k in fkw):
                rf = {"s": 8, "l": "STRONG FIT",
                      "n": "Fact kartlari + arka plan gorseli + text animasyonu. JSON listesinden toplu uretim."}
                rf_type = "facts"
            else:
                rf = {"s": 7, "l": "GOOD FIT",
                      "n": "Faceless format uyumlu. Text/gorsel kartlari ile Remotion uretimi mumkun."}
                rf_type = "general_faceless"

            opp = min(monthly/500, 30) + (5-cs)*8 + rf["s"]*3 + min(av_vr/10, 15)

            results.append({"name": name, "type": mt, "rf_type": rf_type, "count": len(vids),
                           "videos": vids[:10], "av_views": av_views, "av_subs": av_subs,
                           "av_vr": round(av_vr,1), "av_eng": round(av_eng,2), "sh_pct": round(sh_pct),
                           "cpm": cpm, "monthly": round(monthly), "comp": comp, "cs": cs, "rf": rf,
                           "opp": round(opp)})

            print(f"  {name}: {comp} comp | ${monthly:,.0f}/mo | {rf['l']}")

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
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Faceless Niche Discovery #{rn}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0c0f1a;color:#c8cdd8;line-height:1.6;padding:16px}}
.w{{max-width:1000px;margin:0 auto}}
.hdr{{background:linear-gradient(135deg,#059669,#0d9488,#0891b2);padding:28px;border-radius:16px;margin-bottom:24px;text-align:center}}
.hdr h1{{font-size:22px;color:#fff;margin-bottom:4px}}
.hdr p{{color:rgba(255,255,255,.75);font-size:13px}}
.hdr .sts{{display:flex;justify-content:center;gap:14px;margin-top:14px;flex-wrap:wrap}}
.hdr .st{{background:rgba(255,255,255,.15);padding:6px 14px;border-radius:10px;font-size:12px;color:#fff}}
.nis{{background:#151929;border:1px solid #1e2640;border-radius:14px;padding:20px;margin-bottom:20px;position:relative;overflow:hidden}}
.nis-rk{{position:absolute;top:0;right:0;background:linear-gradient(135deg,#059669,#0d9488);color:#fff;padding:6px 16px;border-radius:0 14px 0 12px;font-weight:700;font-size:14px}}
.nis h2{{font-size:17px;color:#e0e4ec;margin-bottom:2px;padding-right:60px}}
.nis-tp{{font-size:12px;color:#0d9488;margin-bottom:10px}}
.mg{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:12px 0}}
.mc{{background:#1a2035;border-radius:10px;padding:12px}}
.mc label{{display:block;font-size:10px;color:#6b7a94;text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px}}
.mc .vl{{font-size:16px;font-weight:700}}
.mc .sb{{font-size:11px;color:#6b7a94;margin-top:2px}}
.g{{color:#4ade80}} .y{{color:#facc15}} .r{{color:#f87171}} .p{{color:#a78bfa}} .b{{color:#60a5fa}} .wh{{color:#e0e4ec}} .tl{{color:#2dd4bf}}
.nt{{background:#1a2035;border-left:3px solid #0d9488;padding:12px;border-radius:0 10px 10px 0;margin:10px 0;font-size:12px;color:#a0aabe}}
.nt strong{{color:#5eead4}}
.ct{{width:100%;border-collapse:collapse;font-size:12px;margin:8px 0}}
.ct th{{text-align:left;padding:6px 10px;background:#1a2035;color:#6b7a94;font-size:10px;text-transform:uppercase}}
.ct td{{padding:6px 10px;border-bottom:1px solid #1e2640}}
.vl{{margin-top:14px}}
.vc{{display:flex;gap:10px;padding:10px;background:#111524;border-radius:10px;margin-bottom:6px}}
.vc img{{width:140px;height:78px;border-radius:8px;object-fit:cover;flex-shrink:0}}
.vi{{flex:1;min-width:0}}
.vi a{{color:#d0d6e2;text-decoration:none;font-weight:600;font-size:12px;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.vi a:hover{{color:#2dd4bf}}
.vi .ch{{font-size:11px;color:#6b7a94;margin:2px 0}}
.vi .ms{{display:flex;gap:8px;font-size:10px;color:#8892a8;flex-wrap:wrap}}
.op{{display:inline-block;padding:3px 8px;border-radius:6px;font-size:11px;font-weight:700}}
.oh{{background:#166534;color:#4ade80}} .om{{background:#854d0e;color:#facc15}} .ol{{background:#7f1d1d;color:#f87171}}
.ft{{text-align:center;padding:24px;font-size:11px;color:#4a5568;margin-top:20px}}
.tag{{display:inline-block;padding:2px 8px;border-radius:6px;font-size:10px;margin-right:4px;margin-bottom:4px}}
.tag-quiz{{background:#1e3a5f;color:#60a5fa}}
.tag-facts{{background:#3b1f5e;color:#a78bfa}}
.tag-interactive{{background:#1a3a2a;color:#4ade80}}
.tag-visual{{background:#3a2a1a;color:#facc15}}
.tag-faceless{{background:#1a2a3a;color:#67e8f9}}
@media(max-width:640px){{.mg{{grid-template-columns:1fr 1fr}}.vc img{{width:100px;height:56px}}}}
</style></head><body><div class="w">
<div class="hdr"><h1>Faceless Niche Discovery #{rn}</h1>
<p>{d} | English markets only (US/GB/CA/AU) | Remotion-ready faceless content only</p>
<div class="sts"><div class="st">{pool:,} videos scanned</div><div class="st">{viral} faceless viral</div>
<div class="st">{nc} niches found</div><div class="st">{rq} API calls</div></div></div>
"""

    type_tags = {"quiz": ("tag-quiz", "QUIZ"), "interactive": ("tag-interactive", "INTERACTIVE"),
                 "visual_puzzle": ("tag-visual", "VISUAL PUZZLE"), "facts": ("tag-facts", "FACTS"),
                 "general_faceless": ("tag-faceless", "FACELESS")}

    for rank, a in enumerate(analyses, 1):
        o = a["opp"]; oc = "oh" if o >= 60 else "om" if o >= 35 else "ol"
        ol = "HIGH OPPORTUNITY" if o >= 60 else "MEDIUM OPPORTUNITY" if o >= 35 else "LOW OPPORTUNITY"
        cc = "g" if a["cs"] <= 2 else "y" if a["cs"] <= 3 else "r"
        rf = a["rf"]; cpm = a["cpm"]
        crows = "".join(f"<tr><td>{c}</td><td>${r[0]:.0f} - ${r[1]:.0f}</td></tr>" for c, r in cpm.items())
        tag_cls, tag_lbl = type_tags.get(a.get("rf_type", ""), ("tag-faceless", "FACELESS"))

        html += f"""<div class="nis"><div class="nis-rk">#{rank}</div>
<h2>{a['name']}</h2>
<div class="nis-tp"><span class="tag {tag_cls}">{tag_lbl}</span> <span class="tag tag-faceless">JSON -> REMOTION</span> {a['count']} videos | <span class="op {oc}">{o}/100 {ol}</span></div>
<div class="mg">
<div class="mc"><label>Avg Views</label><div class="vl wh">{fmt(a['av_views'])}</div></div>
<div class="mc"><label>Avg Subs</label><div class="vl wh">{fmt(a['av_subs'])}</div></div>
<div class="mc"><label>Viral Ratio</label><div class="vl tl">{a['av_vr']}x</div></div>
<div class="mc"><label>Engagement</label><div class="vl b">{a['av_eng']:.1f}%</div></div>
<div class="mc"><label>Competition</label><div class="vl {cc}">{a['comp']}</div></div>
<div class="mc"><label>Shorts</label><div class="vl wh">{a['sh_pct']}%</div></div>
<div class="mc"><label>Est. Monthly Rev</label><div class="vl g">${a['monthly']:,}</div><div class="sb">US CPM based</div></div>
<div class="mc"><label>Remotion Fit</label><div class="vl g">{rf['l']}</div></div>
</div>
<div class="nt"><strong>Remotion Production Plan:</strong> {rf['n']}</div>
<table class="ct"><tr><th>Country</th><th>Est. CPM Range</th></tr>{crows}</table>
"""
        if a["videos"]:
            html += '<div class="vl">'
            for v in a["videos"][:6]:
                tp = "S" if v.get("is_shorts") else "V"
                html += f"""<div class="vc"><img src="{v.get('thumb','')}" loading="lazy">
<div class="vi"><a href="{v['url']}" target="_blank">{v['title'][:70]}</a>
<div class="ch"><a href="{v['ch_url']}" target="_blank">[{tp}] {v['channel']}</a> | {fmt(v['subs'])} subs</div>
<div class="ms"><span>{fmt(v['views'])} views</span><span>{v['viral_ratio']:.0f}x viral</span><span>{v['engagement']:.1f}% eng</span><span>{fmt(v['likes'])} likes</span></div>
</div></div>"""
            html += '</div>'
        html += '</div>\n'

    html += f'<div class="ft">Faceless Niche Discovery Engine | Run #{rn} | {d}<br>English markets only | Remotion JSON pipeline compatible | No camera, no editing</div></div></body></html>'
    return html


# ═══════════ INDEX + EMAIL + MAIN ═══════════

def save_report(html):
    ts = datetime.now().strftime("%Y%m%d_%H%M"); fn = f"rapor_{ts}.html"
    (DOCS_DIR / fn).write_text(html, encoding="utf-8"); print(f"Report: {fn}"); return fn

def update_index():
    reps = sorted(DOCS_DIR.glob("rapor_*.html"), reverse=True)
    rows = ""
    for r in reps[:100]:
        ts = r.stem.replace("rapor_", "")
        try: lb = datetime.strptime(ts, "%Y%m%d_%H%M").strftime("%d.%m.%Y %H:%M")
        except: lb = ts
        rows += f'<tr><td><a href="raporlar/{r.name}">{lb}</a></td><td>{r.stat().st_size/1024:.0f} KB</td></tr>\n'
    idx = f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Faceless Niche Discovery</title><style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0c0f1a;color:#c8cdd8;padding:24px}}
.w{{max-width:700px;margin:0 auto}}h1{{font-size:22px;color:#2dd4bf;margin-bottom:4px}}p{{color:#6b7a94;margin-bottom:16px;font-size:13px}}
table{{width:100%;border-collapse:collapse}}th{{text-align:left;padding:10px;background:#151929;color:#94a0b8;font-size:11px;text-transform:uppercase}}
td{{padding:10px;border-bottom:1px solid #1e2640;font-size:14px}}a{{color:#2dd4bf;text-decoration:none}}a:hover{{text-decoration:underline}}
.e{{color:#4a5568;padding:50px;text-align:center;background:#151929;border-radius:12px}}</style></head>
<body><div class="w"><h1>Faceless Niche Discovery</h1><p>English markets | Remotion-ready | JSON -> Video pipeline</p>
{"<table><tr><th>Date</th><th>Size</th></tr>"+rows+"</table>" if rows else '<div class="e">Waiting for first scan...</div>'}
</div></body></html>"""
    (DOCS_DIR.parent / "index.html").write_text(idx, encoding="utf-8")

def send_email(url, meta):
    if not all([EMAIL_FROM, EMAIL_TO, EMAIL_PASSWORD]): return
    subj = f"Faceless Niche #{meta.get('run','?')} | {meta['viral']} viral | {meta['nc']} niches"
    body = f"New report:\n{meta['pool']:,} scanned, {meta['viral']} faceless viral, {meta['nc']} niches\n\n{url}\n\nAll reports: {PAGES_URL}"
    try:
        msg = MIMEMultipart(); msg["From"]=EMAIL_FROM; msg["To"]=EMAIL_TO; msg["Subject"]=subj
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as s:
            s.starttls(); s.login(EMAIL_FROM, EMAIL_PASSWORD)
            s.sendmail(EMAIL_FROM, [e.strip() for e in EMAIL_TO.split(",")], msg.as_string())
        print("Email sent")
    except Exception as e: print(f"Email error: {e}")


if __name__ == "__main__":
    print(f"Faceless Niche Discovery | {datetime.now().strftime('%d.%m.%Y %H:%M')} | {len(YT_API_KEYS)} keys\n")
    if not YT_API_KEYS: print("YT_API_KEYS not set!"); exit(1)

    km = KM(YT_API_KEYS); yt = YT(km); eng = Discovery(yt); res = eng.run()
    if not res: print("No faceless niches found."); exit(0)

    viral = sum(a["count"] for a in res)
    meta = {"date_fmt": datetime.now().strftime("%d.%m.%Y %H:%M"), "pool": len(eng.pool),
            "viral": viral, "nc": len(res), "reqs": yt.reqs, "run": eng.mem.get("run_count", 1)}

    html = build_report(res, meta); fn = save_report(html); update_index()
    url = f"{PAGES_URL}/raporlar/{fn}" if PAGES_URL else fn
    send_email(url, {**meta}); print(f"\nReport: {url}")
