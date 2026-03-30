import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, time
from functools import lru_cache
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from geopy.geocoders import Nominatim

try:
    from lunardate import LunarDate
except ImportError:  # pragma: no cover
    LunarDate = None


class FortuneError(Exception):
    pass


SECTION_ORDER = [
    "BaZi",
    "Western Astrology",
    "Numerologi",
    "Intinya",
]

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
DEFAULT_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "")
DEFAULT_OPENAI_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "20"))
DEFAULT_OPENAI_RETRY_COUNT = int(os.getenv("OPENAI_RETRY_COUNT", "3"))
SYSTEM_PROMPT = """Anda adalah peramal profesional multidisiplin yang menggabungkan tiga sistem ramalan:
BaZi
Western Astrology
Numerologi

Gunakan input pengguna berikut:
* Tanggal lahir
* Tahun lahir
* Jam lahir
* Tempat lahir
* Periode ramalan yang dipilih pengguna:
  * Hari ini
  * Minggu ini
  * Tahun ini

Tujuan Anda adalah menghasilkan ramalan singkat, mudah dipahami, dan terasa hidup berdasarkan tiga sistem ramalan tersebut.

TUGAS
Buat ramalan sesuai periode yang dipilih pengguna.
Setiap sistem ramalan harus memberikan perspektif yang berbeda dan relevan dengan periode yang dipilih.
Ramalan harus terasa praktis, ringan, dan sedikit playful, sesuai karakter aplikasi.
Jangan menulis teori, proses perhitungan, atau penjelasan teknis.

CALENDAR AND TIME CONVERSION (WAJIB)
Sebelum membuat ramalan, lakukan normalisasi waktu dan konversi kalender sesuai sistem masing-masing.
Gunakan aturan berikut:
BaZi
Konversi tanggal dan jam lahir dari kalender Gregorian ke kalender Cina lunisolar.
Gunakan empat pilar: tahun, bulan, hari, dan jam.
Western Astrology
Gunakan kalender Gregorian dan sistem zodiak tropical.
Numerologi
Gunakan tanggal lahir Gregorian tanpa konversi kalender.
Jika perhitungan presisi tidak tersedia, gunakan pendekatan estimasi yang konsisten.
Jangan menampilkan detail perhitungan kepada pengguna.

TIME AND LOCATION NORMALIZATION
Gunakan aturan berikut:
* Gunakan zona waktu berdasarkan tempat lahir
* Gunakan jam lahir sebagai waktu lokal
* Perhitungkan perbedaan zona waktu secara logis
* Jika jam lahir tidak tersedia, gunakan default 12:00 siang

ADAPTASI PERIODE RAMALAN
Sesuaikan fokus ramalan berdasarkan periode yang dipilih pengguna.
Hari ini
Fokus pada:
* keputusan cepat
* interaksi sosial
* mood dan energi
* hal praktis yang bisa dilakukan hari ini
Minggu ini
Fokus pada:
* momentum
* relasi
* progres pekerjaan
* peluang jangka pendek
Tahun ini
Fokus pada:
* arah besar
* perubahan utama
* peluang jangka panjang
* fase kehidupan
Semua bagian harus merujuk pada periode yang sama.

ATURAN KONTEN
Gunakan aturan berikut:
* Gunakan bahasa Indonesia yang cocok untuk generasi millenial dan gen z
* Gunakan gaya ringkas, jelas, mudah dipahami
* Maksimal 50 kata per bagian
* Gunakan tone ringan dan sedikit playful
* Fokus pada arah atau peluang yang spesifik
* Hindari istilah teknis kompleks
* Hindari jargon astrologi atau metafisika
* Hindari pengulangan kalimat antar sistem

BATASAN KEAMANAN
Jangan membuat prediksi tentang:
* kematian
* penyakit serius
* kecelakaan besar
* bencana
* diagnosis medis
* kepastian masa depan
* klaim supranatural absolut
Gunakan bahasa yang bersifat kemungkinan, arah, atau kecenderungan. Kalau ada hal negatif, bisa dikasih 'hint' saja agar waspada.

ATURAN OUTPUT
Keluarkan tepat empat bagian:
* BaZi
* Western Astrology
* Numerologi
* Intinya
Tiga bagian pertama boleh punya sudut pandang yang berbeda dan tidak harus sepenuhnya selaras.
Bagian "Intinya" wajib terasa seperti rangkuman yang menyatukan semuanya secara saling melengkapi.
"""


@dataclass
class BirthContext:
    birth_local_iso: str
    birth_utc_iso: str
    birth_time_source: str
    timezone_name: str
    timezone_source: str
    birth_place: str
    coordinates: str
    lunar_date: str
    western_sign: str
    vedic_sign_estimate: str
    life_path_number: int
    personal_year_number: int
    bazi_estimate: str
    zi_wei_estimate: str


def generate_fortune(
    *,
    api_key: str,
    model: str = DEFAULT_MODEL,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    base_url: str | None = None,
    birth_date: date,
    birth_time: time | None,
    is_birth_time_known: bool,
    birth_place: str,
    period_label: str,
    period_key: str,
    question_focus: str,
    debug_log=None,
) -> dict[str, str]:
    if debug_log:
        debug_log("generate_fortune:start")
    context = build_birth_context(
        birth_date=birth_date,
        birth_time=birth_time,
        is_birth_time_known=is_birth_time_known,
        birth_place=birth_place,
    )
    if debug_log:
        debug_log(
            "generate_fortune:context_ready "
            f"tz={context.timezone_name} source={context.timezone_source} coords={context.coordinates}"
        )
    if debug_log:
        debug_log(f"generate_fortune:client_ready model={model}")
    user_prompt = build_user_prompt(
        context=context,
        period_label=period_label,
        period_key=period_key,
        question_focus=question_focus,
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    if debug_log:
        debug_log("generate_fortune:requesting_completion")
    content = request_fortune_completion(
        api_key=api_key,
        base_url=base_url,
        model=model,
        reasoning_effort=reasoning_effort,
        messages=messages,
        debug_log=debug_log,
    )

    if debug_log:
        debug_log("generate_fortune:completion_received")
    if not content:
        raise FortuneError("Model tidak mengembalikan isi ramalan.")
    if debug_log:
        debug_log(f"generate_fortune:content_received chars={len(content)}")

    try:
        payload = json.loads(clean_json_payload(content))
    except json.JSONDecodeError as exc:
        raise FortuneError("Respons model tidak berbentuk JSON yang valid.") from exc
    if debug_log:
        debug_log(f"generate_fortune:json_parsed keys={sorted(payload.keys())}")

    result: dict[str, str] = {}
    for section in SECTION_ORDER:
        text = str(payload.get(section, "")).strip()
        if not text:
            raise FortuneError(f"Bagian `{section}` kosong pada respons model.")
        result[section] = trim_words(text, limit=50)
    if debug_log:
        debug_log("generate_fortune:result_ready")
    return result


def run_openai_smoke_test(
    *,
    api_key: str,
    model: str = DEFAULT_MODEL,
    base_url: str | None = None,
    debug_log=None,
) -> str:
    endpoint_base = (base_url or "https://api.openai.com/v1").rstrip("/")
    endpoint = endpoint_base if endpoint_base.endswith("/chat/completions") else f"{endpoint_base}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Reply with valid JSON only."},
            {"role": "user", "content": '{"ok":true}'},
        ],
        "max_tokens": 32,
        "temperature": 0,
    }
    if debug_log:
        debug_log("run_openai_smoke_test:start")
    content = post_chat_completion(
        endpoint=endpoint,
        api_key=api_key,
        payload=payload,
        debug_log=debug_log,
    )
    if debug_log:
        debug_log(f"run_openai_smoke_test:ok content={content[:120]}")
    return content


def generate_fallback_fortune(
    *,
    birth_date: date,
    birth_time: time | None,
    is_birth_time_known: bool,
    birth_place: str,
    period_label: str,
    period_key: str,
    question_focus: str,
) -> dict[str, str]:
    context = build_birth_context(
        birth_date=birth_date,
        birth_time=birth_time,
        is_birth_time_known=is_birth_time_known,
        birth_place=birth_place,
    )
    focus_map = {
        "Umum": "ritme harian dan keputusan kecil",
        "Keuangan": "arus uang dan prioritas belanja",
        "Karir": "arah kerja dan cara ambil posisi",
        "Asmara": "chemistry, batas, dan kejelasan rasa",
        "Kesehatan": "energi, pola istirahat, dan tempo tubuh",
    }
    period_map = {
        "today": "hari ini",
        "week": "minggu ini",
        "year": "tahun ini",
    }
    focus_label = focus_map.get(question_focus, "arah hidup secara umum")
    period_phrase = period_map.get(period_key, period_label.lower())
    sign = context.western_sign
    life_path = context.life_path_number
    personal_year = context.personal_year_number
    bazi_hint = context.bazi_estimate.split(",")[0].replace("Tahun ", "")
    birth_time_note = (
        "jam lahirmu ikut bikin timing-nya lebih spesifik"
        if is_birth_time_known and birth_time is not None
        else "karena jam lahir belum diketahui, bacaan ini sengaja dibikin lebih fleksibel"
    )
    momentum = pick_variant(
        "momentum",
        birth_date.isoformat(),
        birth_place.lower(),
        question_focus,
        period_key,
        str(life_path),
    )
    strategy = pick_variant(
        "strategy",
        birth_date.isoformat(),
        birth_place.lower(),
        context.western_sign,
        context.vedic_sign_estimate,
    )
    social_mode = pick_variant(
        "social",
        birth_place.lower(),
        question_focus,
        period_key,
        str(personal_year),
    )
    caution = pick_variant(
        "caution",
        birth_date.isoformat(),
        context.bazi_estimate,
        context.zi_wei_estimate,
        question_focus,
    )
    sections = {
        "BaZi": (
            f"BaZi kamu buat {period_phrase} kebaca lebih {momentum}. "
            f"Vibe {bazi_hint} enaknya dipakai buat {strategy}, terutama di area {focus_label}. "
            f"{birth_time_note.capitalize()}."
        ),
        "Western Astrology": (
            f"Sebagai {sign}, kamu lagi lebih kuat kalau maunya dibikin kelihatan, bukan disimpan rapi di kepala. "
            f"Untuk {period_phrase}, peluang biasanya kebuka waktu kamu pilih gaya {social_mode} saat ngurus {focus_label}."
        ),
        "Numerologi": (
            f"Life path {life_path} ketemu personal year {personal_year} bikin tema kamu sekarang condong ke pola yang lebih dewasa dan kepakai lama. "
            f"Buat {focus_label}, pilih langkah yang {caution}, bukan yang cuma seru di awal."
        ),
        "Intinya": (
            f"Madame bilang: dari tiga bacaan ini, benang merahnya ada di cara kamu nyusun ritme, nunjukkin maumu, dan jaga langkah yang realistis. "
            f"Untuk {period_phrase}, pakai yang paling nyambung buat {focus_label}, lalu biarin sisanya jadi pelengkap, bukan rebutan."
        ),
    }
    return {section: trim_words(text, limit=50) for section, text in sections.items()}


def pick_variant(bucket: str, *parts: str) -> str:
    variants = {
        "momentum": [
            "tajam tapi hemat gerak",
            "pelan tapi ngunci",
            "lebih taktis daripada spontan",
            "rapi dan minim drama",
            "tenang tapi susah digeser",
        ],
        "strategy": [
            "langsung dan elegan",
            "simple tapi presisi",
            "rapi tanpa banyak ancang-ancang",
            "kalem tapi jelas arahnya",
            "praktis dan nggak muter-muter",
        ],
        "social": [
            "tegas tapi tetap manis",
            "hangat tapi nggak ngasih sinyal campur aduk",
            "jelas, santai, dan nggak defensif",
            "ringan tapi tahu batas",
            "jujur tanpa bikin suasana berat",
        ],
        "caution": [
            "bisa dijaga ritmenya",
            "punya efek nyata dalam beberapa langkah ke depan",
            "nggak bikin kamu capek ngejar image",
            "lebih stabil daripada heboh",
            "masuk akal buat diulang terus",
        ],
    }
    pool = variants[bucket]
    seed = "|".join(part.strip().lower() for part in parts if part).encode("utf-8")
    digest = hashlib.sha256(seed).hexdigest()
    return pool[int(digest[:8], 16) % len(pool)]
def request_fortune_completion(
    *,
    api_key: str,
    base_url: str | None,
    model: str,
    reasoning_effort: str,
    messages: list[dict[str, str]],
    debug_log=None,
):
    endpoint_base = (base_url or "https://api.openai.com/v1").rstrip("/")
    endpoint = endpoint_base if endpoint_base.endswith("/chat/completions") else f"{endpoint_base}/chat/completions"
    attempts = [
        {
            "response_format": None,
            "include_reasoning_effort": False,
        },
        {
            "response_format": {"type": "json_object"},
            "include_reasoning_effort": False,
        },
        {
            "response_format": None,
            "include_reasoning_effort": True,
        },
    ]
    last_error: Exception | None = None

    for index, attempt in enumerate(attempts, start=1):
        kwargs = {
            "model": model,
            "messages": messages,
        }
        if attempt["response_format"] is not None:
            kwargs["response_format"] = attempt["response_format"]
        if attempt["include_reasoning_effort"] and reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort

        try:
            if debug_log:
                debug_log(
                    "request_fortune_completion:attempt "
                    f"index={index}/{len(attempts)} "
                    f"response_format={attempt['response_format'] is not None} "
                    f"reasoning_effort={attempt['include_reasoning_effort']}"
                )
            return post_chat_completion(
                endpoint=endpoint,
                api_key=api_key,
                payload=kwargs,
                debug_log=debug_log,
            )
        except FortuneError as exc:
            last_error = exc
            if debug_log:
                debug_log(
                    "request_fortune_completion:attempt_failed "
                    f"index={index}/{len(attempts)} error_type={type(exc).__name__} error={exc}"
                )

    raise FortuneError(f"Gagal meminta respons ke model: {last_error}")


def post_chat_completion(*, endpoint: str, api_key: str, payload: dict, debug_log=None) -> str:
    return post_chat_completion_via_urllib(
        endpoint=endpoint,
        api_key=api_key,
        payload=payload,
        debug_log=debug_log,
    )


def post_chat_completion_via_urllib(
    *,
    endpoint: str,
    api_key: str,
    payload: dict,
    debug_log=None,
) -> str:
    body = json.dumps(payload).encode("utf-8")
    last_error: Exception | None = None

    for attempt_index in range(1, DEFAULT_OPENAI_RETRY_COUNT + 1):
        request = Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

        try:
            if debug_log:
                debug_log(
                    "post_chat_completion:open "
                    f"attempt={attempt_index}/{DEFAULT_OPENAI_RETRY_COUNT} "
                    f"url={endpoint} timeout={DEFAULT_OPENAI_TIMEOUT_SECONDS}s body_chars={len(body)}"
                )
            with urlopen(request, timeout=DEFAULT_OPENAI_TIMEOUT_SECONDS) as response:
                status_code = getattr(response, "status", None) or response.getcode()
                raw = response.read().decode("utf-8")
            if debug_log:
                debug_log(
                    "post_chat_completion:response_received "
                    f"attempt={attempt_index}/{DEFAULT_OPENAI_RETRY_COUNT} "
                    f"status={status_code} chars={len(raw)}"
                )
            break
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            if debug_log:
                debug_log(
                    "post_chat_completion:http_error "
                    f"attempt={attempt_index}/{DEFAULT_OPENAI_RETRY_COUNT} "
                    f"status={exc.code} reason={exc.reason} details={details[:200]}"
                )
            if exc.code in {408, 409, 429, 500, 502, 503, 504} and attempt_index < DEFAULT_OPENAI_RETRY_COUNT:
                backoff_seconds = attempt_index
                if debug_log:
                    debug_log(f"post_chat_completion:retrying_in seconds={backoff_seconds}")
                sleep(backoff_seconds)
                last_error = exc
                continue
            raise FortuneError(f"HTTP {exc.code} dari OpenAI: {details[:300]}") from exc
        except URLError as exc:
            if debug_log:
                debug_log(
                    "post_chat_completion:url_error "
                    f"attempt={attempt_index}/{DEFAULT_OPENAI_RETRY_COUNT} "
                    f"reason_type={type(exc.reason).__name__} reason={exc.reason}"
                )
            if attempt_index < DEFAULT_OPENAI_RETRY_COUNT:
                backoff_seconds = attempt_index
                if debug_log:
                    debug_log(f"post_chat_completion:retrying_in seconds={backoff_seconds}")
                sleep(backoff_seconds)
                last_error = exc
                continue
            raise FortuneError(f"Koneksi ke OpenAI gagal: {exc.reason}") from exc
        except TimeoutError as exc:
            if debug_log:
                debug_log(
                    "post_chat_completion:timeout "
                    f"attempt={attempt_index}/{DEFAULT_OPENAI_RETRY_COUNT}"
                )
            if attempt_index < DEFAULT_OPENAI_RETRY_COUNT:
                backoff_seconds = attempt_index
                if debug_log:
                    debug_log(f"post_chat_completion:retrying_in seconds={backoff_seconds}")
                sleep(backoff_seconds)
                last_error = exc
                continue
            raise FortuneError("Request ke OpenAI timeout.") from exc
        except Exception as exc:
            if debug_log:
                debug_log(
                    "post_chat_completion:unexpected_exception "
                    f"attempt={attempt_index}/{DEFAULT_OPENAI_RETRY_COUNT} "
                    f"error_type={type(exc).__name__} error={exc}"
                )
            raise FortuneError(f"Request ke OpenAI gagal: {exc}") from exc
    else:
        raise FortuneError(f"Request ke OpenAI gagal setelah retry: {last_error}")

    try:
        response_payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        if debug_log:
            debug_log(f"post_chat_completion:invalid_json snippet={raw[:200]}")
        raise FortuneError("Respons OpenAI bukan JSON valid.") from exc

    try:
        message = response_payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        if debug_log:
            debug_log(
                "post_chat_completion:unexpected_response_shape "
                f"snippet={str(response_payload)[:200]}"
            )
        raise FortuneError(f"Format respons OpenAI tidak dikenali: {str(response_payload)[:300]}") from exc

    if isinstance(message, str):
        if debug_log:
            debug_log(f"post_chat_completion:message_ready type=str chars={len(message)}")
        return message.strip()
    if isinstance(message, list):
        texts: list[str] = []
        for item in message:
            if isinstance(item, dict) and item.get("text"):
                texts.append(str(item["text"]))
        if debug_log:
            debug_log(
                "post_chat_completion:message_ready "
                f"type=list text_parts={len(texts)} chars={len(''.join(texts))}"
            )
        return "\n".join(texts).strip()
    if debug_log:
        debug_log(f"post_chat_completion:message_ready type={type(message).__name__}")
    return str(message).strip()


def clean_json_payload(content: str) -> str:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def build_birth_context(
    *,
    birth_date: date,
    birth_time: time | None,
    is_birth_time_known: bool,
    birth_place: str,
) -> BirthContext:
    timezone_name, timezone_source, coordinates = resolve_timezone(birth_place)
    local_zone = ZoneInfo(timezone_name)
    local_dt = None
    utc_dt = None
    if birth_time is not None:
        local_dt = datetime.combine(birth_date, birth_time).replace(tzinfo=local_zone)
        utc_dt = local_dt.astimezone(ZoneInfo("UTC"))

    lunar_date = estimate_lunar_date(birth_date)
    western_sign = detect_western_sign(birth_date)
    vedic_sign_estimate = detect_vedic_sign_estimate(birth_date)
    life_path = calculate_life_path_number(birth_date)
    personal_year = calculate_personal_year_number(birth_date, date.today().year)
    bazi_estimate = estimate_bazi(birth_date=birth_date, local_dt=local_dt)
    zi_wei_estimate = estimate_zi_wei(local_dt=local_dt, lunar_date=lunar_date)

    return BirthContext(
        birth_local_iso=local_dt.isoformat() if local_dt else f"{birth_date.isoformat()}Tunknown",
        birth_utc_iso=utc_dt.isoformat() if utc_dt else "unknown",
        birth_time_source="input pengguna" if is_birth_time_known else "unknown / tidak diketahui",
        timezone_name=timezone_name,
        timezone_source=timezone_source,
        birth_place=birth_place,
        coordinates=coordinates,
        lunar_date=lunar_date,
        western_sign=western_sign,
        vedic_sign_estimate=vedic_sign_estimate,
        life_path_number=life_path,
        personal_year_number=personal_year,
        bazi_estimate=bazi_estimate,
        zi_wei_estimate=zi_wei_estimate,
    )


def build_user_prompt(*, context: BirthContext, period_label: str, period_key: str, question_focus: str) -> str:
    return f"""Berikut konteks yang sudah dinormalisasi untuk dipakai secara internal.

Input pengguna:
- Tanggal dan waktu lahir lokal: {context.birth_local_iso}
- Waktu UTC hasil normalisasi: {context.birth_utc_iso}
- Sumber jam lahir: {context.birth_time_source}
- Tempat lahir: {context.birth_place}
- Zona waktu: {context.timezone_name} ({context.timezone_source})
- Koordinat estimasi: {context.coordinates}
- Periode ramalan: {period_label} ({period_key})
- Fokus pertanyaan pengguna: {question_focus}

Konversi dan estimasi internal:
- Tanggal lunisolar estimasi: {context.lunar_date}
- BaZi estimasi: {context.bazi_estimate}
- Zodiak Western tropical: {context.western_sign}
- Life path numerologi: {context.life_path_number}
- Personal year numerologi untuk tahun berjalan: {context.personal_year_number}

Instruksi output:
- Keluarkan JSON object valid saja.
- Gunakan tepat empat key berikut:
  "BaZi", "Western Astrology", "Numerologi", "Intinya"
- Nilai tiap key berupa satu paragraf singkat berbahasa Indonesia.
- Maksimal 50 kata per bagian.
- Jangan tampilkan teori, perhitungan, atau disclaimer teknis.
- Semua bagian harus konsisten terhadap periode {period_label}.
- Semua bagian harus menyesuaikan fokus pertanyaan {question_focus}. Jika fokusnya "Umum", jaga tetap luas dan seimbang.
- Jika jam lahir tidak diketahui, jangan mengarang detail yang seolah sangat presisi dari posisi jam.
- Tiga bagian pertama boleh saling beda sudut pandang dan tidak harus terasa sepenuhnya harmonis.
- Untuk key "Intinya", rangkum tiga bagian sebelumnya dalam satu paragraf maksimal 50 kata, dengan tone sangat uplifting dan cheeky, terasa menyatukan semuanya.
"""


def resolve_timezone(place: str) -> tuple[str, str, str]:
    return _resolve_timezone_cached(place.strip())


@lru_cache(maxsize=256)
def _resolve_timezone_cached(place: str) -> tuple[str, str, str]:
    geolocator = Nominatim(user_agent="madame-damn-space", timeout=8)

    try:
        location = geolocator.geocode(place, addressdetails=True)
        if location:
            timezone_name = estimate_timezone_name(
                latitude=location.latitude,
                longitude=location.longitude,
                address=(location.raw or {}).get("address", {}),
            )
            if timezone_name:
                coordinates = f"{location.latitude:.4f}, {location.longitude:.4f}"
                return timezone_name, "estimated from geocoded place", coordinates
    except Exception:
        pass

    return "UTC", "fallback", "unknown"


def estimate_timezone_name(*, latitude: float, longitude: float, address: dict) -> str:
    country_code = str(address.get("country_code", "")).lower()
    state = str(address.get("state", "")).lower()

    if country_code == "id":
        if longitude < 112:
            return "Asia/Jakarta"
        if longitude < 127:
            return "Asia/Makassar"
        return "Asia/Jayapura"

    if country_code == "my":
        return "Asia/Kuala_Lumpur"
    if country_code == "sg":
        return "Asia/Singapore"
    if country_code == "ph":
        return "Asia/Manila"
    if country_code == "th":
        return "Asia/Bangkok"
    if country_code == "vn":
        return "Asia/Ho_Chi_Minh"
    if country_code == "jp":
        return "Asia/Tokyo"
    if country_code == "kr":
        return "Asia/Seoul"
    if country_code == "cn":
        return "Asia/Shanghai"
    if country_code == "in":
        return "Asia/Kolkata"
    if country_code == "ae":
        return "Asia/Dubai"
    if country_code == "gb":
        return "Europe/London"
    if country_code == "fr":
        return "Europe/Paris"
    if country_code == "de":
        return "Europe/Berlin"
    if country_code == "nl":
        return "Europe/Amsterdam"
    if country_code == "au":
        if "western australia" in state or longitude < 129:
            return "Australia/Perth"
        if "northern territory" in state:
            return "Australia/Darwin"
        if "south australia" in state:
            return "Australia/Adelaide"
        if "queensland" in state:
            return "Australia/Brisbane"
        if "new south wales" in state or "victoria" in state or "tasmania" in state or longitude >= 141:
            return "Australia/Sydney"
    if country_code == "us":
        if state == "alaska" or longitude <= -141:
            return "America/Anchorage"
        if state == "hawaii" or longitude <= -151:
            return "Pacific/Honolulu"
        if longitude <= -115:
            return "America/Los_Angeles"
        if longitude <= -101:
            return "America/Denver"
        if longitude <= -85:
            return "America/Chicago"
        return "America/New_York"
    if country_code == "ca":
        if longitude <= -120:
            return "America/Vancouver"
        if longitude <= -105:
            return "America/Edmonton"
        if longitude <= -90:
            return "America/Winnipeg"
        if longitude <= -67:
            return "America/Toronto"
        return "America/Halifax"
    if country_code == "br":
        if longitude <= -50:
            return "America/Manaus"
        if longitude <= -35:
            return "America/Sao_Paulo"
        return "America/Recife"

    offset_hours = max(-12, min(14, round(longitude / 15)))
    if offset_hours == 0:
        return "UTC"

    etc_sign = "-" if offset_hours > 0 else "+"
    return f"Etc/GMT{etc_sign}{abs(offset_hours)}"


def estimate_lunar_date(value: date) -> str:
    if LunarDate is None:
        return "estimasi tidak tersedia"

    try:
        lunar = LunarDate.fromSolarDate(value.year, value.month, value.day)
        return f"Tahun {lunar.year}, Bulan {lunar.month}, Hari {lunar.day}"
    except Exception:
        return "estimasi tidak tersedia"


def detect_western_sign(value: date) -> str:
    month_day = (value.month, value.day)
    boundaries = [
        ((1, 20), "Capricorn", "Aquarius"),
        ((2, 19), "Aquarius", "Pisces"),
        ((3, 21), "Pisces", "Aries"),
        ((4, 20), "Aries", "Taurus"),
        ((5, 21), "Taurus", "Gemini"),
        ((6, 21), "Gemini", "Cancer"),
        ((7, 23), "Cancer", "Leo"),
        ((8, 23), "Leo", "Virgo"),
        ((9, 23), "Virgo", "Libra"),
        ((10, 23), "Libra", "Scorpio"),
        ((11, 22), "Scorpio", "Sagittarius"),
        ((12, 22), "Sagittarius", "Capricorn"),
    ]
    for cutoff, before_sign, after_sign in boundaries:
        if month_day < cutoff:
            return before_sign
    return "Capricorn"


def detect_vedic_sign_estimate(value: date) -> str:
    shifted_ordinal = value.toordinal() - 24
    shifted = date.fromordinal(shifted_ordinal)
    month_day = (shifted.month, shifted.day)
    boundaries = [
        ((1, 20), "Capricorn", "Aquarius"),
        ((2, 19), "Aquarius", "Pisces"),
        ((3, 21), "Pisces", "Aries"),
        ((4, 20), "Aries", "Taurus"),
        ((5, 21), "Taurus", "Gemini"),
        ((6, 21), "Gemini", "Cancer"),
        ((7, 23), "Cancer", "Leo"),
        ((8, 23), "Leo", "Virgo"),
        ((9, 23), "Virgo", "Libra"),
        ((10, 23), "Libra", "Scorpio"),
        ((11, 22), "Scorpio", "Sagittarius"),
        ((12, 22), "Sagittarius", "Capricorn"),
    ]
    for cutoff, before_sign, after_sign in boundaries:
        if month_day < cutoff:
            return before_sign
    return "Capricorn"


def calculate_life_path_number(value: date) -> int:
    digits = [int(ch) for ch in value.strftime("%Y%m%d")]
    return reduce_number(sum(digits))


def calculate_personal_year_number(value: date, current_year: int) -> int:
    total = sum(int(ch) for ch in value.strftime("%m%d")) + sum(int(ch) for ch in str(current_year))
    return reduce_number(total)


def reduce_number(number: int) -> int:
    while number > 9 and number not in {11, 22, 33}:
        number = sum(int(ch) for ch in str(number))
    return number


def estimate_bazi(*, birth_date: date, local_dt: datetime | None) -> str:
    heavenly_stems = ["Jia", "Yi", "Bing", "Ding", "Wu", "Ji", "Geng", "Xin", "Ren", "Gui"]
    earthly_branches = ["Zi", "Chou", "Yin", "Mao", "Chen", "Si", "Wu", "Wei", "Shen", "You", "Xu", "Hai"]

    year_index = (birth_date.year - 4) % 60
    year_stem = heavenly_stems[year_index % 10]
    year_branch = earthly_branches[year_index % 12]
    month_branch = earthly_branches[(birth_date.month + 1) % 12]
    day_stem = heavenly_stems[(birth_date.toordinal() + 4) % 10]

    if local_dt is None:
        return (
            f"Tahun {year_stem}-{year_branch}, "
            f"Bulan cabang {month_branch}, "
            f"Hari batang {day_stem}, "
            "Jam tidak diketahui"
        )

    hour_branch = earthly_branches[((local_dt.hour + 1) // 2) % 12]
    return (
        f"Tahun {year_stem}-{year_branch}, "
        f"Bulan cabang {month_branch}, "
        f"Hari batang {day_stem}, "
        f"Jam cabang {hour_branch}"
    )


def estimate_zi_wei(*, local_dt: datetime | None, lunar_date: str) -> str:
    if local_dt is None:
        return f"Struktur estimasi dari {lunar_date} tanpa blok jam spesifik"
    hour_block = ((local_dt.hour + 1) // 2) % 12
    return f"Struktur estimasi dari {lunar_date} dengan blok jam ke-{hour_block}"


def trim_words(text: str, *, limit: int) -> str:
    words = text.split()
    if len(words) <= limit:
        return text
    return " ".join(words[:limit]).rstrip(".,;:") + "..."
