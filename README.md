# med2md

MinerU ile PDF → Markdown toplu dönüştürücü. Tek GPU'lu makineler için.

## Hızlı başlangıç

```bash
# 1. Tek seferlik kurulum (.venv yaratır, torch + mineru + transformers kurar, doğrular)
bash setup.sh

# 2. venv'i aktif et
source .venv/bin/activate

# 3. Çalıştır
python med2md.py -i ./papers/ -o ./output/
```

`setup.sh` mevcut bir venv'i de kullanabilir:

```bash
bash setup.sh /venv/main      # belirli bir path
CUDA=cu121 bash setup.sh      # farklı CUDA (default: cu124)
CUDA=cpu   bash setup.sh      # GPU yoksa
```

## Kullanım

```bash
# Tek PDF
python med2md.py -i ./paper.pdf -o ./output/

# Klasör (recursive)
python med2md.py -i ./papers/ -o ./output/

# Hepsi
python med2md.py -i ./papers/ -o ./output/ \
    -b pipeline -m auto -l en \
    -j 3 \
    --failed-log failed.txt --log-file run.log
```

## Argümanlar

| Argüman | Default | Açıklama |
|---|---|---|
| `-i` / `--input` | — | PDF, klasör, ya da satır başına PDF path'i içeren text dosyası |
| `-o` / `--output` | — | Çıktı klasörü |
| `-b` / `--backend` | `pipeline` | `pipeline`, `vlm-auto-engine`, `hybrid-auto-engine` |
| `-m` / `--method` | `auto` | `auto`, `txt`, `ocr` (pipeline/hybrid backend'leri için) |
| `-l` / `--lang` | `en` | Doküman dili: `en`, `ch`, `japan`, `korean`, ... |
| `-j` / `--workers` | `1` | Paralel işçi sayısı |
| `--no-skip` | — | Zaten dönüştürülmüşleri de yeniden işle |
| `--failed-log` | — | Başarısız PDF path'lerini yaz |
| `--log-file` | — | Logları dosyaya yaz |

## Backend seçimi

| Backend | Hız | Kalite | Ne zaman |
|---|---|---|---|
| `pipeline` | En hızlı | İyi | Standart akademik PDF'ler |
| `vlm-auto-engine` | Yavaş | En iyi | Karmaşık layout, denklem ağırlıklı |
| `hybrid-auto-engine` | Orta | Çok iyi | Pipeline + VLM birlikte |

## Çıktı

```
output/
├── paper_a/
│   ├── paper_a.md
│   └── images/
├── paper_b/
│   └── paper_b.md
└── conversion_report.json
```

`conversion_report.json` her koşunun tam özetini içerir: timestamp, backend, başarılı/başarısız listesi, PDF başına süre.

## Başarısızları tekrar çalıştırma

```bash
# İlk koşu — başarısızları kaydet
python med2md.py -i ./papers/ -o ./output/ --failed-log failed.txt

# Sadece başarısızlar
python med2md.py -i failed.txt -o ./output/ --no-skip
```

## RTX 4090 (24 GB) için öneriler

```bash
# Pipeline — 3 worker güvenli
python med2md.py -i ./papers/ -o ./output/ -b pipeline -j 3

# VLM — 1 worker
python med2md.py -i ./papers/ -o ./output/ -b vlm-auto-engine -j 1

# OOM olursa worker düşür
```

## Sorun giderme

**`mineru CLI not found on PATH`**
venv aktif değil. `source .venv/bin/activate` yap, sonra `which mineru` ile doğrula.

**`No module named 'transformers'` (mineru service'den)**
Eski bir mineru-api servisi arkada açık kalmış olabilir. Kapat ve tekrar dene:
```bash
pkill -f mineru-api || true
```
Hâlâ olursa `bash setup.sh` ile bağımlılıkları yeniden kur.

**`CUDA out of memory`**
Worker sayısını düşür (`-j 1`) ya da `pipeline` backend'e geç.

**Çıkış kodları**
- `0` — hepsi başarılı
- `1` — hiç PDF bulunamadı / yapılandırma hatası
- `2` — bazıları başarısız (`failed-log` dosyasına bak)
