---
title: madame, help!
emoji: 🔮
colorFrom: pink
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# madame, help!

`madame, help!` adalah app ramalan ringan berbahasa Indonesia untuk `Streamlit`.

- BaZi
- Western Astrology
- Numerologi
- Intinya

## Input

- Tanggal lahir
- Jam lahir, termasuk opsi `Tidak Tahu`
- Tempat lahir
- Periode ramalan: `Hari ini`, `Minggu ini`, `Tahun ini`
- Fokus pertanyaan: `Umum`, `Keuangan`, `Karir`, `Asmara`, `Kesehatan`

## Secret di Streamlit Community Cloud

Tambahkan secret berikut di menu app `Settings > Secrets`:

- `OPENAI_API_KEY` wajib
- `OPENAI_ENABLED` opsional, default `false`
- `OPENAI_MODEL` opsional, default `gpt-5.4-mini`
- `OPENAI_REASONING_EFFORT` opsional, default `minimal`
- `OPENAI_BASE_URL` opsional untuk endpoint OpenAI-compatible

Secara default app memakai engine lokal agar stabil di Streamlit Community Cloud. Jika benar-benar ingin memanggil OpenAI, set `OPENAI_ENABLED=true`.

Isi value secret dengan nilai mentah saja. Contoh yang benar untuk `OPENAI_API_KEY`:

```text
sk-xxxx
```

Jangan isi seperti ini:

```text
OPENAI_API_KEY="sk-xxxx"
EVOLINK_API_KEY="sk-yyyy"
```

Jika butuh lebih dari satu secret, buat masing-masing di field secret terpisah.

## Local Run

```bash
streamlit run app.py
```

## Deploy ke Streamlit Community Cloud

Pastikan repo berisi file-file ini:

- `app.py`
- `fortune_engine.py`
- `requirements.txt`
- `runtime.txt`
- `README.md`
- `header.png`

Lalu set `Main file path` ke `app.py`.

Jangan commit `.streamlit/secrets.toml`. Secret itu hanya untuk local run.

## Catatan

- Tempat lahir dicoba di-normalisasi ke zona waktu dengan geocoding. Jika gagal, app memakai fallback estimasi yang konsisten.
- Jika jam lahir `Tidak Tahu`, engine akan memperlakukan jam lahir sebagai `unknown`, bukan memaksakan `12:00`.
- Output ditampilkan dalam empat bagian tetap, sesuai urutan UI.
