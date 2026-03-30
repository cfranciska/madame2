import base64
import os
import re
import traceback
from datetime import date, datetime, time
from html import escape
from pathlib import Path
from time import perf_counter

import streamlit as st

import fortune_engine

FortuneError = fortune_engine.FortuneError
generate_fortune = fortune_engine.generate_fortune
run_openai_smoke_test = fortune_engine.run_openai_smoke_test


st.set_page_config(
    page_title="madame, help!",
    page_icon="🔮",
    layout="centered",
)


CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Borel&family=Poppins:wght@400;500;600;700&display=swap');

    :root {
        --bg: #fff7f0;
        --ink: #222222;
        --muted: #645b66;
        --card: rgba(255, 247, 240, 0.84);
        --line: rgba(34, 34, 34, 0.10);
        --accent: #ff2e93;
        --accent-2: #7b2ff7;
        --accent-3: #ff8a00;
        --shadow: 0 18px 50px rgba(123, 47, 247, 0.12);
    }

    html, body, [class*="css"], [data-testid="stAppViewContainer"], .stApp, .stMarkdown, p, span, label, input, textarea, button, select, li, div {
        font-family: 'Poppins', sans-serif !important;
    }

    .stApp {
        background:
            radial-gradient(circle at top left, rgba(255, 46, 147, 0.15), transparent 30%),
            radial-gradient(circle at top right, rgba(123, 47, 247, 0.14), transparent 28%),
            radial-gradient(circle at bottom center, rgba(255, 138, 0, 0.10), transparent 34%),
            linear-gradient(180deg, #fff9f4 0%, var(--bg) 100%);
        color: var(--ink);
    }

    .block-container {
        max-width: 840px;
        padding-top: 2.5rem;
        padding-bottom: 3rem;
    }

    h1, h2, h3 {
        font-family: 'Poppins', sans-serif;
        color: var(--ink);
        letter-spacing: -0.03em;
    }

    .hero {
        padding: 1.8rem 1.6rem 1.35rem;
        border: 1px solid var(--line);
        border-radius: 28px;
        background: linear-gradient(145deg, rgba(255, 249, 244, 0.96), rgba(255, 240, 249, 0.9));
        box-shadow: var(--shadow);
        margin-bottom: 1.3rem;
        text-align: center;
    }

    .hero-kicker {
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.18em;
        color: var(--accent-2);
        margin-bottom: 0.72rem;
        font-weight: 700;
        position: relative;
        z-index: 2;
    }

    .hero-title {
        font-family: 'Borel', cursive !important;
        font-size: clamp(1.85rem, 3.6vw, 2.8rem) !important;
        line-height: 0.9 !important;
        margin: 0 auto 0.05rem;
        padding-top: 0.55rem;
        color: #ff2e93 !important;
        font-weight: 400 !important;
        max-width: 100%;
        position: relative;
        z-index: 1;
    }

    .hero-image {
        width: min(290px, 58vw);
        display: block;
        margin: 0.05rem auto 0.8rem;
        filter: drop-shadow(0 10px 20px rgba(24, 33, 38, 0.08));
    }

    .hero-subtitle {
        margin: 0.8rem auto 0;
        color: #ff2e93;
        max-width: 34rem;
        text-align: center;
        display: block;
        font-weight: 500;
        line-height: 1.55;
    }

    .hero-subtitle-wrap {
        width: 100%;
        display: flex;
        justify-content: center;
    }

    div[data-testid="stForm"] {
        padding: 1.1rem;
        border: 1px solid var(--line);
        border-radius: 24px;
        background: linear-gradient(180deg, rgba(255, 248, 243, 0.92), rgba(255, 241, 249, 0.82));
        box-shadow: var(--shadow);
    }

    .section-label {
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.14em;
        color: var(--accent-2);
        font-weight: 700;
        margin-bottom: 0.3rem;
    }

    label[data-testid="stWidgetLabel"] p,
    div[data-testid="stWidgetLabel"] p {
        color: var(--accent-2);
        font-weight: 700;
        opacity: 1;
    }

    .result-card {
        border: 1px solid var(--line);
        border-radius: 22px;
        padding: 1.1rem 1.15rem;
        background: var(--card);
        box-shadow: var(--shadow);
        backdrop-filter: blur(10px);
    }

    .result-title {
        margin: 0 0 0.4rem;
        font-size: 1.05rem;
        font-weight: 700;
    }

    .result-copy {
        margin: 0;
        color: var(--ink);
        line-height: 1.55;
        font-size: 0.98rem;
    }

    .footnote {
        color: var(--muted);
        font-size: 0.9rem;
        margin-top: 1rem;
    }

    div[data-baseweb="notification"] {
        border-radius: 18px;
        border: 1px solid rgba(255, 46, 147, 0.16);
    }

    div[data-baseweb="notification"] div[role="alert"] {
        color: #8f1553;
        font-weight: 600;
    }

    div[data-baseweb="notification"] p {
        color: #8f1553;
    }

    div[data-testid="stFormSubmitButton"] button {
        background: linear-gradient(135deg, var(--accent) 0%, var(--accent-3) 100%);
        color: #fff7f0;
        border: none;
        border-radius: 16px;
        min-height: 3.2rem;
        font-weight: 700;
        font-size: 1rem;
        letter-spacing: 0.01em;
        box-shadow: 0 12px 28px rgba(255, 46, 147, 0.24);
    }

    div[data-testid="stFormSubmitButton"] button:hover {
        background: linear-gradient(135deg, #e52684 0%, #f47d00 100%);
        color: #fffaf5;
    }

    div[data-testid="stFormSubmitButton"] button p {
        color: inherit;
    }

    div[data-testid="stFormSubmitButton"] button:disabled,
    div[data-testid="stFormSubmitButton"] button[disabled] {
        background: linear-gradient(135deg, var(--accent) 0%, var(--accent-3) 100%);
        color: #fff7f0 !important;
        opacity: 1 !important;
        -webkit-text-fill-color: #fff7f0;
        filter: none !important;
    }

    div[data-testid="stFormSubmitButton"] button:disabled *,
    div[data-testid="stFormSubmitButton"] button[disabled] * {
        color: #fff7f0 !important;
        opacity: 1 !important;
        -webkit-text-fill-color: #fff7f0;
        fill: #fff7f0 !important;
        filter: none !important;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.12);
    }

    @media (max-width: 640px) {
        .hero {
            padding: 1.45rem 1rem 1.05rem;
        }

        .hero-kicker {
            font-size: 0.68rem;
            letter-spacing: 0.14em;
            margin-bottom: 0.5rem;
        }

        .hero-title {
            font-size: clamp(1.7rem, 7.4vw, 2.2rem) !important;
            line-height: 0.92 !important;
            margin: 0 auto 0.02rem;
            padding-top: 0.35rem;
        }

        .hero-image {
            width: min(280px, 72vw);
            margin: 0.02rem auto 0.75rem;
        }

        .hero-subtitle {
            margin-top: 0.55rem;
            max-width: 18rem;
        }
    }
</style>
"""


PERIOD_OPTIONS = {
    "Hari ini": "today",
    "Minggu ini": "week",
    "Tahun ini": "year",
}

QUESTION_FOCUS_OPTIONS = [
    "Umum",
    "Keuangan",
    "Karir",
    "Asmara",
    "Kesehatan",
]

TIME_OPTIONS = ["Tidak Tahu"] + [f"{hour:02d}:{minute:02d}" for hour in range(24) for minute in (0, 30)]

SECTION_ORDER = [
    "BaZi",
    "Western Astrology",
    "Numerologi",
    "Intinya",
]


def ensure_app_state() -> None:
    st.session_state.setdefault("forecast_result", None)
    st.session_state.setdefault("forecast_birth_label", "")
    st.session_state.setdefault("forecast_place", "")
    st.session_state.setdefault("forecast_notice", None)
    st.session_state.setdefault("forecast_error_detail", None)
    st.session_state.setdefault("forecast_debug_log", [])


def append_debug_log(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state["forecast_debug_log"].append(f"[{timestamp}] {message}")


def get_setting(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return normalize_setting_value(name, value)

    try:
        secret_value = st.secrets.get(name)
    except Exception:
        secret_value = None

    if secret_value is None:
        return default
    return normalize_setting_value(name, str(secret_value))


def normalize_setting_value(name: str, value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return ""

    if "\n" not in cleaned and "=" not in cleaned:
        return strip_wrapping_quotes(cleaned)

    extracted = extract_named_assignment(cleaned, name)
    if extracted is not None:
        return extracted

    if "\n" not in cleaned:
        return strip_wrapping_quotes(cleaned)

    return cleaned


def extract_named_assignment(blob: str, name: str) -> str | None:
    pattern = re.compile(rf"(?m)^\s*{re.escape(name)}\s*=\s*(.+?)\s*$")
    match = pattern.search(blob)
    if not match:
        return None
    return strip_wrapping_quotes(match.group(1).strip())


def strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1].strip()
    return value


def is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@st.cache_data(show_spinner=False)
def encode_image(path: str) -> str:
    image_bytes = Path(path).read_bytes()
    return base64.b64encode(image_bytes).decode("utf-8")


def validate_inputs(
    *,
    birth_date: date | None,
    birth_time_label: str | None,
    birth_place: str,
    period_label: str | None,
    question_focus: str | None,
) -> list[str]:
    missing_fields: list[str] = []
    if birth_date is None:
        missing_fields.append("tanggal lahir")
    if not birth_time_label:
        missing_fields.append("jam lahir")
    if not birth_place.strip():
        missing_fields.append("tempat lahir")
    if not period_label:
        missing_fields.append("periode ramalan")
    if not question_focus:
        missing_fields.append("mau tanya apa")
    return missing_fields


def parse_birth_time(label: str) -> tuple[time | None, bool]:
    if label == "Tidak Tahu":
        return None, False
    return datetime.strptime(label, "%H:%M").time(), True


def main() -> None:
    ensure_app_state()
    header_image = encode_image("header.png")
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.markdown(
        f"""
        <section class="hero">
            <div class="hero-kicker">Ramalan Multiserver</div>
            <div class="hero-title">Madame, help!</div>
            <img class="hero-image" src="data:image/png;base64,{header_image}" alt="madame, damn! header">
            <div class="hero-subtitle-wrap">
                <p class="hero-subtitle" style="font-size: 10px; line-height: 1.5; color: #ff2e93; font-weight: 500; margin-top: 0.55rem;">
                    Ringkas dan playful. Menghadirkan ramalan menurut BaZi, western astrology, dan numerologi, lalu dirangkum jadi inti yang saling melengkapi.
                </p>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    with st.container():
        st.markdown('<div class="section-label">SPILL SPILL SPILL!</div>', unsafe_allow_html=True)

        with st.form("fortune_form"):
            col1, col2 = st.columns([1.2, 1])
            with col1:
                birth_date = st.date_input(
                    "Tanggal lahir",
                    value=date(1995, 6, 15),
                    min_value=date(1900, 1, 1),
                    max_value=date.today(),
                )
            with col2:
                birth_time_label = st.selectbox(
                    "Jam lahir",
                    options=TIME_OPTIONS,
                    index=TIME_OPTIONS.index("12:00"),
                )

            birth_place = st.text_input(
                "Tempat lahir",
                placeholder="Contoh: Bandung, Indonesia (wajib di isi)",
            )
            period_label = st.selectbox(
                "Ramalan untuk",
                options=list(PERIOD_OPTIONS.keys()),
            )
            question_focus = st.selectbox(
                "Mau tanya apa?",
                options=QUESTION_FOCUS_OPTIONS,
                index=0,
            )

            submitted = st.form_submit_button("Buka ramalannya", use_container_width=True)

    if submitted:
        started_at = perf_counter()
        st.session_state["forecast_result"] = None
        st.session_state["forecast_birth_label"] = ""
        st.session_state["forecast_place"] = ""
        st.session_state["forecast_notice"] = None
        st.session_state["forecast_error_detail"] = None
        st.session_state["forecast_debug_log"] = []
        append_debug_log("submit:start")

        missing_fields = validate_inputs(
            birth_date=birth_date,
            birth_time_label=birth_time_label,
            birth_place=birth_place,
            period_label=period_label,
            question_focus=question_focus,
        )
        if missing_fields:
            append_debug_log(f"submit:validation_failed missing={', '.join(missing_fields)}")
            st.error(
                "Data kurang lengkap. Mohon lengkapi: "
                + ", ".join(missing_fields)
                + "."
            )
        else:
            append_debug_log("submit:validation_ok")
            birth_time, is_birth_time_known = parse_birth_time(birth_time_label)
            append_debug_log(
                f"submit:birth_time_parsed known={is_birth_time_known} value={birth_time_label}"
            )

            api_key = get_setting("OPENAI_API_KEY")
            model = get_setting("OPENAI_MODEL", "gpt-5.4-mini")
            reasoning_effort = get_setting("OPENAI_REASONING_EFFORT", "")
            base_url = get_setting("OPENAI_BASE_URL")
            openai_enabled = is_truthy(get_setting("OPENAI_ENABLED", "false"))
            openai_smoke_test = is_truthy(get_setting("OPENAI_SMOKE_TEST", "false"))
            append_debug_log(
                f"submit:settings_loaded api_key={'yes' if bool(api_key) else 'no'} "
                f"model={model} reasoning={reasoning_effort} base_url={'set' if bool(base_url) else 'default'} "
                f"openai_enabled={openai_enabled} smoke_test={openai_smoke_test}"
            )

            if openai_enabled and not api_key:
                append_debug_log("submit:missing_api_key")
                st.error(
                    "`OPENAI_API_KEY` belum tersedia. Untuk local run, isi `.streamlit/secrets.toml`. "
                    "Untuk Streamlit Community Cloud, tambahkan di Settings > Secrets."
                )
            elif openai_enabled and ("\n" in api_key or api_key.startswith("OPENAI_API_KEY=")):
                append_debug_log("submit:invalid_api_key_format")
                st.error(
                    "`OPENAI_API_KEY` tidak valid. Isi secret hanya dengan nilai key-nya saja, "
                    "misalnya `sk-...`, bukan format `.env` seperti `OPENAI_API_KEY=sk-...`."
                )
            elif not openai_enabled:
                append_debug_log("submit:openai_disabled")
                st.session_state["forecast_notice"] = (
                    "Engine utama sedang dimatikan. Ramalan tidak ditampilkan sampai `OPENAI_ENABLED=true`."
                )
                st.session_state["forecast_error_detail"] = None
            else:
                with st.spinner("Madame sedang menyusun arah energimu..."):
                    try:
                        if openai_smoke_test:
                            append_debug_log("submit:running_smoke_test")
                            run_openai_smoke_test(
                                api_key=api_key,
                                model=model,
                                base_url=base_url or None,
                                debug_log=append_debug_log,
                            )
                            append_debug_log("submit:smoke_test_ok")
                        append_debug_log("submit:calling_generate_fortune")
                        forecast = generate_fortune(
                            api_key=api_key,
                            model=model,
                            reasoning_effort=reasoning_effort,
                            base_url=base_url or None,
                            birth_date=birth_date,
                            birth_time=birth_time,
                            is_birth_time_known=is_birth_time_known,
                            birth_place=birth_place.strip(),
                            period_label=period_label,
                            period_key=PERIOD_OPTIONS[period_label],
                            question_focus=question_focus,
                            debug_log=append_debug_log,
                        )
                    except FortuneError as exc:
                        append_debug_log(f"submit:fortune_error error={exc}")
                        st.session_state["forecast_notice"] = (
                            f"Model utama gagal membuat ramalan. Tidak ada output yang ditampilkan. Detail: {exc}"
                        )
                        st.session_state["forecast_error_detail"] = traceback.format_exc()
                    except Exception:
                        append_debug_log("submit:unexpected_error")
                        st.session_state["forecast_notice"] = (
                            "Koneksi atau proses engine utama gagal. Tidak ada output yang ditampilkan. "
                            "Buka detail error di bawah kalau perlu."
                        )
                        st.session_state["forecast_error_detail"] = traceback.format_exc()
                    else:
                        append_debug_log("submit:generate_fortune_ok")
                        st.session_state["forecast_notice"] = None
                        st.session_state["forecast_error_detail"] = None
                    finally:
                        append_debug_log("submit:spinner_done")

                if "forecast" in locals():
                    if birth_time is not None:
                        local_birth_label = datetime.combine(birth_date, birth_time).strftime("%d %b %Y %H:%M")
                    else:
                        local_birth_label = f"{birth_date.strftime('%d %b %Y')} (jam tidak diketahui)"

                    st.session_state["forecast_result"] = forecast
                    st.session_state["forecast_birth_label"] = local_birth_label
                    st.session_state["forecast_place"] = birth_place.strip()
                    append_debug_log(
                        f"submit:result_saved elapsed={perf_counter() - started_at:.2f}s sections={len(forecast)}"
                    )

    forecast = st.session_state.get("forecast_result")
    notice = st.session_state.get("forecast_notice")
    error_detail = st.session_state.get("forecast_error_detail")
    if not forecast:
        if notice:
            st.warning(notice)
        if error_detail:
            with st.expander("Detail error", expanded=False):
                st.code(error_detail)
        debug_log = st.session_state.get("forecast_debug_log") or []
        if debug_log:
            with st.expander("Debug log", expanded=True):
                st.code("\n".join(debug_log))
        return

    if notice:
        st.warning(notice)

    if error_detail:
        with st.expander("Detail error", expanded=False):
            st.code(error_detail)

    st.markdown('<div class="section-label">SINGKAP RAMALANNYA</div>', unsafe_allow_html=True)
    for section in SECTION_ORDER:
        content = escape(forecast.get(section, "").strip())
        if not content:
            content = "Arah energinya masih blur. Coba kirim ulang untuk pembacaan yang lebih rapi."
        st.markdown(
            f"""
            <section class="result-card">
                <h3 class="result-title">{escape(section)}</h3>
                <p class="result-copy">{content}</p>
            </section>
            """,
            unsafe_allow_html=True,
        )
        st.write("")

    st.markdown(
        (
            f"<p class='footnote'>Input diproses dari waktu lokal kelahiran "
            f"{escape(st.session_state['forecast_birth_label'])} di {escape(st.session_state['forecast_place'])} "
            f"dengan estimasi zona waktu bila diperlukan.</p>"
        ),
        unsafe_allow_html=True,
    )

    debug_log = st.session_state.get("forecast_debug_log") or []
    if debug_log:
        with st.expander("Debug log", expanded=False):
            st.code("\n".join(debug_log))


if __name__ == "__main__":
    main()
