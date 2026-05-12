# med2md

Batch PDF → Markdown converter using MinerU, optimised for single-GPU machines.

## Kurulum

```bash
pip install mineru[full] tqdm
```

## Kullanım

```bash
# Tek PDF
python med2md.py -i ./paper.pdf -o ./output/

# Klasör (recursive)
python med2md.py -i ./papers/ -o ./output/

# Tüm seçeneklerle
python med2md.py -i ./papers/ -o ./output/ \
    --mode pipeline \
    --workers 3 \
    --failed-log failed.txt \
    --log-file run.log
```

## Argümanlar

| Argüman | Default | Açıklama |
|---|---|---|
| `-i` / `--input` | — | PDF dosyası veya klasörü (recursive) |
| `-o` / `--output` | — | Çıktı klasörü |
| `-m` / `--mode` | `auto` | MinerU modu: `auto`, `pipeline`, `vlm` |
| `-w` / `--workers` | `3` | Paralel worker sayısı |
| `--no-skip` | — | Zaten dönüştürülmüş dosyaları da yeniden işle |
| `--failed-log` | — | Başarısız PDF path'lerini bu dosyaya yaz |
| `--log-file` | — | Logları dosyaya da yaz |

## Modlar

| Mod | Hız | Kalite | Ne zaman |
|---|---|---|---|
| `pipeline` | En hızlı | İyi | Standart akademik makaleler |
| `vlm` | Yavaş | En iyi | Karmaşık layout, yoğun formül |
| `auto` | Orta | İyi | MinerU karar verir |

## Çıktı Yapısı

```
output/
├── paper_a/
│   ├── paper_a.md
│   └── figures/
├── paper_b/
│   └── paper_b.md
└── conversion_report.json
```

`conversion_report.json` içeriği: timestamp, toplam/başarılı/başarısız sayısı, PDF başına süre, PDF/dakika throughput.

## vast.ai / RTX 4090 Önerileri

```bash
# Pipeline modu — 24 GB VRAM'da 3 worker güvenli
python med2md.py -i ~/papers/ -o ~/output/ --mode pipeline --workers 3

# VLM modu — worker düşür
python med2md.py -i ~/papers/ -o ~/output/ --mode vlm --workers 1

# OOM alırsan
python med2md.py -i ~/papers/ -o ~/output/ --workers 2
```

Dosyaları vast.ai'ya aktarma:

```bash
rsync -avz ./papers/ root@<host>:~/papers/
```

İşlem bittikten sonra çıktıyı indirme:

```bash
rsync -avz root@<host>:~/output/ ./output/
```

## Başarısız Dosyaları Yeniden İşleme

```bash
# İlk çalıştırma — başarısızları kaydet
python med2md.py -i ~/papers/ -o ~/output/ --failed-log failed.txt

# Retry — sadece başarısızlar
python med2md.py -i failed.txt -o ~/output/ --no-skip
```
