# 🔭 YouTube Niş Keşif Motoru

**Önceden tanımlı kategori YOK.** Kendi başına trendleri analiz eder, viral anomalileri tespit eder, anahtar kelime çıkarır, yeni nişleri keşfeder. Her çalışmada önceki keşiflerini hatırlar ve yeni alanlar keşfeder.

## Nasıl Çalışır

```
Her 6 saatte otomatik:
  FAZA 1 → 8 ülkeden trending videoları çeker
  FAZA 2 → Viral anomalileri tespit eder (küçük kanal + büyük izlenme)
  FAZA 3 → Viral başlıklardan anahtar kelime çıkarır
  FAZA 4 → Çıkan kelimelerle yeni aramalar yapar (snowball keşif)
  FAZA 5 → Bulunanları otomatik nişlere gruplar
  FAZA 6 → CPM, gelir tahmini, Remotion uyumu, rekabet analizi
  
  → HTML rapor üretir → GitHub Pages'te yayınlar → Email atar
```

**Hafıza sistemi:** `discoveries.json` dosyasında önceki keşiflerini saklar. Aynı keyword'leri tekrar aramaz, her seferinde yeni yollar keşfeder.

## Kurulum (5 dk)

### 1. GitHub'da public repo oluştur, bu dosyaları push et

### 2. YouTube API Key al (ücretsiz)
[Google Cloud Console](https://console.cloud.google.com/) → Yeni proje → YouTube Data API v3 etkinleştir → API Key oluştur

### 3. GitHub Secrets ayarla
Repo → Settings → Secrets → Actions:

| Secret | Değer | Zorunlu |
|--------|-------|---------|
| `YT_API_KEYS` | `AIzaXXX,AIzaYYY` | ✅ |
| `EMAIL_FROM` | `senin@gmail.com` | ❌ |
| `EMAIL_TO` | `kisi1@mail.com,kisi2@mail.com` | ❌ |
| `EMAIL_PASSWORD` | Gmail App Password | ❌ |

### 4. GitHub Pages aç
Settings → Pages → Source: **GitHub Actions**

### 5. İlk taramayı başlat
Actions → "🔭 Niş Keşif" → Run workflow

Raporlar: `https://KULLANICIADI.github.io/REPO-ADI/`

## Maliyet

**$0.** GitHub Actions (public = sınırsız), YouTube API (10K/gün ücretsiz), GitHub Pages (ücretsiz).

## Tempo Değiştirme

`.github/workflows/tarama.yml` → cron satırını düzenle:
- `*/6` → Her 6 saatte (varsayılan)
- `*/4` → Her 4 saatte  
- `*/3` → Her 3 saatte

## Durdurma

Actions → Workflow → "..." → Disable workflow
