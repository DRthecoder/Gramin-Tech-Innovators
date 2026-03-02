"""
Lakhpati-Didi AI — Voice-First Business Coach for Rural Indian Women
=====================================================================
Streamlit MVP with:
  - Product image analysis via Amazon Bedrock (Claude 3.5 Sonnet v2)
  - Voice input via Amazon Transcribe (Speech-to-Text)
  - Voice output via Amazon Polly (Text-to-Speech)
"""

import base64
import json
import io
import os
import time
import uuid

import boto3
import requests as http_requests
import streamlit as st
from botocore.exceptions import (
    NoCredentialsError,
    PartialCredentialsError,
    ClientError,
    NoRegionError,
)
from dotenv import load_dotenv
from PIL import Image

load_dotenv()


def _secret(key: str, default: str = "") -> str:
    """Read from Streamlit Cloud secrets first, then fall back to .env."""
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        return os.getenv(key, default)


BEDROCK_MODEL_ID = "us.anthropic.claude-sonnet-4-20250514-v1:0"

# ── Bilingual UI strings ───────────────────────────────────────────
UI_TEXT = {
    "Hindi": {
        "hero_title": "लखपति-दीदी AI",
        "hero_subtitle": "आपका AI बिज़नेस कोच — सही दाम, स्मार्ट मार्केटिंग",
        "hero_tagline": "फ़ोटो लें, मुनाफ़ा जानें!",
        "step1_title": "फ़ोटो लें",
        "step1_desc": "अपने प्रोडक्ट की फ़ोटो कैमरे से लें",
        "step2_title": "AI विश्लेषण",
        "step2_desc": "बटन दबाएँ और AI से जवाब पाएँ",
        "step3_title": "मुनाफ़ा कमाएँ",
        "step3_desc": "सही दाम लगाएँ और WhatsApp पर बेचें",
        "feat1_title": "मूल्य निर्धारण",
        "feat1_desc": "AI आपके प्रोडक्ट की लागत और सही बिक्री मूल्य बताएगा",
        "feat2_title": "WhatsApp मार्केटिंग",
        "feat2_desc": "तैयार मार्केटिंग मैसेज जो आप सीधे भेज सकती हैं",
        "feat3_title": "आवाज़ से बात करें",
        "feat3_desc": "बोलकर सवाल पूछें, सुनकर जवाब पाएँ",
        "camera_header": "अपने प्रोडक्ट की फ़ोटो लें",
        "camera_help": "कैमरा खोलने के लिए नीचे क्लिक करें। अच्छी रोशनी में फ़ोटो लें।",
        "camera_label": "📸 कैमरा खोलें",
        "voice_header": "अपना सवाल बोलें (वैकल्पिक)",
        "voice_help": "प्रोडक्ट के बारे में कोई सवाल रिकॉर्ड करें — AI उसका भी जवाब देगा।",
        "voice_label": "🎤 अपना सवाल रिकॉर्ड करें",
        "transcribe_btn": "🔄 आवाज़ को टेक्स्ट में बदलें",
        "transcribing": "आवाज़ समझ रहे हैं… कृपया रुकें 🎧",
        "transcribe_done": "आपका सवाल:",
        "transcribe_fail": "आवाज़ समझ नहीं पाए। कृपया दोबारा बोलें।",
        "analyse_btn": "✨ प्रोडक्ट का विश्लेषण करें",
        "result_header": "आपकी AI रिपोर्ट",
        "spinner": "दीदी, आपका प्रोडक्ट समझ रही हूँ… कृपया रुकें 🙏",
        "no_photo_warn": "कृपया पहले प्रोडक्ट की फ़ोटो लें।",
        "no_input_warn": "कृपया पहले फ़ोटो लें या अपनी आवाज़ रिकॉर्ड करें।",
        "listen_btn": "🔊 रिपोर्ट सुनें",
        "listen_spinner": "ऑडियो बना रहे हैं…",
        "prompt": (
            "आप एक विशेषज्ञ बिज़नेस कोच हैं जो भारतीय ग्रामीण महिला उद्यमियों की "
            "मदद करती हैं। इस प्रोडक्ट इमेज को देखें और हिंदी में निम्नलिखित बताएं:\n"
            "1. प्रोडक्ट की पहचान और विवरण\n"
            "2. अनुमानित लागत और सुझाई गई बिक्री कीमत (₹ में)\n"
            "3. प्रॉफ़िट मार्जिन गणना\n"
            "4. WhatsApp के लिए एक आकर्षक मार्केटिंग मैसेज (इमोजी के साथ)\n"
            "5. बिक्री बढ़ाने के 2-3 सुझाव\n"
            "कृपया सरल हिंदी में जवाब दें जो एक ग्रामीण महिला आसानी से समझ सके।"
        ),
        "sidebar_about": (
            "**लखपति-दीदी AI** ग्रामीण महिला उद्यमियों को सही दाम तय करने, "
            "मार्केटिंग करने और सरकारी योजनाओं तक पहुँचने में मदद करती है।"
        ),
        "sidebar_steps": [
            "अपने प्रोडक्ट की फ़ोटो लें",
            "(वैकल्पिक) अपना सवाल बोलें",
            "'विश्लेषण करें' बटन दबाएँ",
            "AI रिपोर्ट पढ़ें या सुनें",
        ],
        "footer": "भारत की महिलाओं के लिए, प्यार से बनाया गया 🇮🇳",
    },
    "English": {
        "hero_title": "Lakhpati-Didi AI",
        "hero_subtitle": "Your AI Business Coach — Right Price, Smart Marketing",
        "hero_tagline": "Snap a photo, know your profit!",
        "step1_title": "Take Photo",
        "step1_desc": "Capture your product with camera",
        "step2_title": "AI Analysis",
        "step2_desc": "Press the button and get AI insights",
        "step3_title": "Earn Profit",
        "step3_desc": "Set the right price & sell on WhatsApp",
        "feat1_title": "Smart Pricing",
        "feat1_desc": "AI estimates your production cost and ideal selling price",
        "feat2_title": "WhatsApp Marketing",
        "feat2_desc": "Ready-to-send marketing messages for your customers",
        "feat3_title": "Talk with Voice",
        "feat3_desc": "Ask questions by speaking, hear answers read aloud",
        "camera_header": "Capture Your Product",
        "camera_help": "Click below to open the camera. Use good lighting for best results.",
        "camera_label": "📸 Open Camera",
        "voice_header": "Ask a Question by Voice (Optional)",
        "voice_help": "Record a question about your product — AI will answer it too.",
        "voice_label": "🎤 Record your question",
        "transcribe_btn": "🔄 Convert Speech to Text",
        "transcribing": "Converting your speech to text… please wait 🎧",
        "transcribe_done": "Your question:",
        "transcribe_fail": "Could not understand the audio. Please try again.",
        "analyse_btn": "✨ Analyse Product",
        "result_header": "Your AI Report",
        "spinner": "Analysing your product… please wait 🙏",
        "no_photo_warn": "Please take a product photo first.",
        "no_input_warn": "Please take a photo or record your voice first.",
        "listen_btn": "🔊 Listen to Report",
        "listen_spinner": "Generating audio…",
        "prompt": (
            "You are an expert business coach helping rural Indian women "
            "entrepreneurs. Look at this product image and provide:\n"
            "1. Product identification and description\n"
            "2. Estimated cost of production and suggested selling price (in ₹)\n"
            "3. Profit margin calculation\n"
            "4. An engaging WhatsApp marketing message (with emojis)\n"
            "5. 2-3 tips to boost sales\n"
            "Keep the language simple and encouraging."
        ),
        "sidebar_about": (
            "**Lakhpati-Didi AI** helps rural women entrepreneurs set the "
            "right price, market their products, and discover government schemes."
        ),
        "sidebar_steps": [
            "Capture a photo of your product",
            "(Optional) Record a voice question",
            "Press the 'Analyse' button",
            "Read or listen to the AI report",
        ],
        "footer": "Built with love for the women building Bharat 🇮🇳",
    },
}


# ── Page config ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="Lakhpati-Didi AI",
    page_icon="🪷",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── Session state defaults ──────────────────────────────────────────
if "transcript" not in st.session_state:
    st.session_state.transcript = ""
if "analysis" not in st.session_state:
    st.session_state.analysis = ""
if "lang" not in st.session_state:
    st.session_state.lang = "English"

# ── Custom CSS ──────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700;800&display=swap');

:root {
    --saffron: #FF9933;
    --green: #138808;
    --green-dark: #0a5c04;
    --green-light: #e8f5e9;
    --gold: #FFD700;
    --cream: #FFFDF7;
    --brown: #5D4037;
    --brown-light: #8D6E63;
}

.stApp {
    background: var(--cream);
    font-family: 'Poppins', sans-serif;
}
#MainMenu, footer, header {visibility: hidden;}

/* ── Force ALL Streamlit text dark (targets internal elements) ── */
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] span,
[data-testid="stMarkdownContainer"] strong,
[data-testid="stMarkdownContainer"] em,
[data-testid="stMarkdownContainer"] td,
[data-testid="stMarkdownContainer"] th,
[data-testid="stMarkdownContainer"] ol,
[data-testid="stMarkdownContainer"] ul,
[data-testid="stMarkdownContainer"] div {
    color: #1a1a1a !important;
}
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3,
[data-testid="stMarkdownContainer"] h4,
[data-testid="stMarkdownContainer"] h5 {
    color: #0a5c04 !important;
}
/* ── Code blocks: light text on dark bg ── */
[data-testid="stMarkdownContainer"] pre {
    background: #1e1e2e !important;
    border-radius: 10px !important;
    padding: 1rem !important;
}
[data-testid="stMarkdownContainer"] pre code,
[data-testid="stMarkdownContainer"] pre span {
    color: #e0e0e0 !important;
}
[data-testid="stMarkdownContainer"] code {
    color: #d63384 !important;
    background: #f1f1f1 !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
}
[data-testid="stMarkdownContainer"] pre code {
    background: transparent !important;
    padding: 0 !important;
    color: #e0e0e0 !important;
}
/* Restore white text where needed */
.hero-banner [data-testid="stMarkdownContainer"] *,
.hero-banner, .hero-banner * { color: #fff !important; }
.result-banner, .result-banner * { color: #fff !important; }
.step-desc { color: #6d4c41 !important; }
.feat-desc { color: #6d4c41 !important; }
.input-help { color: #6d4c41 !important; }
.app-footer { color: #8D6E63 !important; }
.audio-section-label { color: var(--green) !important; }
.transcript-label { color: var(--saffron) !important; }
.stButton > button, .stButton > button * { color: #fff !important; }

/* ── Language pills — centered toggle ── */
div.lang-toggle-wrap {
    display: flex;
    justify-content: center;
    margin: 1rem auto 1.5rem;
}
div.lang-toggle-wrap [data-testid="stPills"],
div.lang-toggle-wrap [data-testid="stPills"] > div,
div.lang-toggle-wrap [data-testid="stPills"] > div > div {
    display: flex !important;
    justify-content: center !important;
    width: auto !important;
}
div.lang-toggle-wrap [data-testid="stPills"] [role="tablist"] {
    justify-content: center !important;
    gap: 0 !important;
    background: #fff !important;
    border-radius: 50px !important;
    padding: 4px !important;
    box-shadow: 0 2px 12px rgba(0,0,0,0.07) !important;
    border: 1px solid #e8e8e8 !important;
}
div.lang-toggle-wrap [data-testid="stPills"] button {
    border-radius: 50px !important;
    padding: 0.5rem 2rem !important;
    font-weight: 700 !important;
    font-size: 0.95rem !important;
    border: none !important;
    background: transparent !important;
    color: #5D4037 !important;
    box-shadow: none !important;
    transition: all 0.25s ease !important;
    min-width: 120px !important;
}
div.lang-toggle-wrap [data-testid="stPills"] button[aria-checked="true"] {
    background: linear-gradient(135deg, #FF9933, #e07c00) !important;
    color: #fff !important;
    box-shadow: 0 3px 10px rgba(255,153,51,0.35) !important;
}

/* ── Hero Banner ── */
.hero-banner {
    background: linear-gradient(135deg, #FF9933 0%, #FF8019 40%, #138808 100%);
    border-radius: 0 0 2rem 2rem;
    padding: 2.5rem 1.5rem 2rem;
    text-align: center;
    margin: -1rem -1rem 0 -1rem;
    position: relative;
    overflow: hidden;
}
.hero-banner::before {
    content: '';
    position: absolute;
    top: -50%; left: -50%;
    width: 200%; height: 200%;
    background: radial-gradient(circle, rgba(255,255,255,0.08) 0%, transparent 70%);
    animation: shimmer 6s ease-in-out infinite;
}
@keyframes shimmer {
    0%, 100% { transform: translateX(-30%) translateY(-30%); }
    50% { transform: translateX(30%) translateY(30%); }
}
.hero-title {
    font-size: 2.6rem;
    font-weight: 800;
    color: #fff;
    margin: 0;
    text-shadow: 0 2px 12px rgba(0,0,0,0.18);
    position: relative;
    letter-spacing: -0.5px;
}
.hero-subtitle {
    font-size: 1.05rem;
    color: rgba(255,255,255,0.92);
    margin: 0.3rem 0 0;
    font-weight: 500;
    position: relative;
}
.hero-tagline {
    display: inline-block;
    margin-top: 1rem;
    background: rgba(255,255,255,0.2);
    backdrop-filter: blur(4px);
    padding: 0.4rem 1.4rem;
    border-radius: 2rem;
    color: #fff;
    font-weight: 600;
    font-size: 0.95rem;
    border: 1px solid rgba(255,255,255,0.3);
    position: relative;
}

/* ── Language Switch ── */
.lang-switch-wrapper {
    display: flex;
    justify-content: center;
    margin: 1.2rem 0 1.5rem;
}
.lang-switch {
    display: inline-flex;
    background: #fff;
    border-radius: 50px;
    padding: 5px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    border: 1px solid #e8e8e8;
    gap: 0;
}
.lang-btn {
    padding: 0.5rem 1.8rem;
    border-radius: 50px;
    font-weight: 700;
    font-size: 0.88rem;
    cursor: pointer;
    transition: all 0.25s ease;
    border: none;
    font-family: 'Poppins', sans-serif;
    letter-spacing: 0.3px;
}
.lang-btn.active {
    background: linear-gradient(135deg, var(--saffron), #e07c00);
    color: #fff;
    box-shadow: 0 3px 10px rgba(255,153,51,0.35);
}
.lang-btn.inactive {
    background: transparent;
    color: var(--brown-light);
}

/* ── Step Flow ── */
.steps-row {
    display: flex;
    justify-content: center;
    gap: 0.5rem;
    margin-bottom: 2rem;
    flex-wrap: wrap;
}
.step-card {
    flex: 1;
    min-width: 120px;
    max-width: 180px;
    text-align: center;
    padding: 1rem 0.6rem;
}
.step-num {
    width: 38px; height: 38px;
    background: linear-gradient(135deg, var(--saffron), #e07c00);
    color: #fff;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 1rem;
    margin-bottom: 0.5rem;
    box-shadow: 0 3px 10px rgba(255,153,51,0.35);
}
.step-title {
    font-weight: 700;
    font-size: 0.85rem;
    color: var(--brown);
    margin-bottom: 0.15rem;
}
.step-desc {
    font-size: 0.72rem;
    color: var(--brown-light);
    line-height: 1.3;
}
.step-arrow {
    display: flex;
    align-items: center;
    color: var(--saffron);
    font-size: 1.3rem;
    font-weight: bold;
    padding-top: 0.7rem;
}

/* ── Feature Cards ── */
.features-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.75rem;
    margin-bottom: 2rem;
}
@media (max-width: 600px) {
    .features-grid { grid-template-columns: 1fr; }
}
.feat-card {
    background: #fff;
    border-radius: 14px;
    padding: 1.2rem 1rem;
    text-align: center;
    border: 1px solid #f0ece4;
    box-shadow: 0 2px 10px rgba(0,0,0,0.04);
    transition: transform 0.2s, box-shadow 0.2s;
}
.feat-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 6px 20px rgba(0,0,0,0.08);
}
.feat-icon { font-size: 2rem; margin-bottom: 0.5rem; }
.feat-title {
    font-weight: 700;
    font-size: 0.9rem;
    color: var(--brown);
    margin-bottom: 0.25rem;
}
.feat-desc {
    font-size: 0.78rem;
    color: var(--brown-light);
    line-height: 1.4;
}

/* ── Section Headers ── */
.section-header {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin: 1.5rem 0 0.8rem;
}
.section-icon {
    width: 40px; height: 40px;
    background: linear-gradient(135deg, var(--green), var(--green-dark));
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.2rem;
    box-shadow: 0 3px 10px rgba(19,136,8,0.25);
}
.section-icon.saffron {
    background: linear-gradient(135deg, var(--saffron), #e07c00);
    box-shadow: 0 3px 10px rgba(255,153,51,0.25);
}
.section-label {
    font-size: 1.15rem;
    font-weight: 700;
    color: var(--brown);
}

/* ── Camera / Voice Box ── */
.input-box {
    background: #fff;
    border: 2px dashed #c8e6c9;
    border-radius: 16px;
    padding: 1rem;
    margin-bottom: 1rem;
    transition: border-color 0.3s;
}
.input-box:hover { border-color: var(--green); }
.input-box.voice { border-color: #ffe0b2; }
.input-box.voice:hover { border-color: var(--saffron); }
.input-help {
    text-align: center;
    font-size: 0.82rem;
    color: var(--brown-light);
    margin-bottom: 0.5rem;
}

/* ── Transcript Box ── */
.transcript-box {
    background: #FFF8E1;
    border-left: 4px solid var(--saffron);
    border-radius: 0 10px 10px 0;
    padding: 0.8rem 1rem;
    margin: 0.5rem 0 1rem;
    font-size: 0.9rem;
    color: var(--brown);
}
.transcript-label {
    font-weight: 700;
    font-size: 0.78rem;
    color: var(--saffron);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 0.25rem;
}

/* ── Buttons ── */
.stButton > button {
    background: linear-gradient(135deg, var(--green), var(--green-dark)) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 14px !important;
    padding: 0.75rem 2rem !important;
    font-size: 1.1rem !important;
    font-weight: 700 !important;
    font-family: 'Poppins', sans-serif !important;
    width: 100%;
    box-shadow: 0 4px 15px rgba(19,136,8,0.3) !important;
    transition: all 0.25s ease !important;
    letter-spacing: 0.3px;
}
.stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px rgba(19,136,8,0.4) !important;
}
.stButton > button:active {
    transform: translateY(0) !important;
}

/* ── Result Area ── */
.result-banner {
    background: linear-gradient(135deg, var(--green), var(--green-dark));
    color: #fff;
    padding: 1rem 1.2rem;
    border-radius: 14px 14px 0 0;
    font-weight: 700;
    font-size: 1.1rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
/* ── Result container (native Streamlit border container) ── */
.result-banner + div [data-testid="stVerticalBlockBorderWrapper"] {
    border-color: #c8e6c9 !important;
    border-radius: 0 0 14px 14px !important;
    border-top: none !important;
    background: #fff !important;
}
[data-testid="stVerticalBlockBorderWrapper"] {
    background: #fff !important;
}

/* ── Audio Player ── */
.audio-section {
    background: linear-gradient(135deg, #e8f5e9, #fff);
    border: 1px solid #c8e6c9;
    border-radius: 14px;
    padding: 1rem 1.2rem;
    margin-top: 1rem;
    text-align: center;
}
.audio-section-label {
    font-weight: 700;
    font-size: 0.85rem;
    color: var(--green);
    margin-bottom: 0.5rem;
}

/* ── Image Preview ── */
.preview-container {
    background: #fff;
    border-radius: 14px;
    padding: 0.5rem;
    box-shadow: 0 2px 10px rgba(0,0,0,0.06);
    margin-bottom: 1rem;
    border: 1px solid #f0ece4;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #FFFDF7 0%, #e8f5e9 100%);
}

/* ── Footer ── */
.app-footer {
    text-align: center;
    padding: 2rem 0 1rem;
    color: var(--brown-light);
    font-size: 0.82rem;
    border-top: 1px solid #ece8e0;
    margin-top: 2.5rem;
}

/* ── Divider ── */
.soft-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, #e0d8cc, transparent);
    margin: 1.5rem 0;
}

/* ── Hide default camera / audio labels ── */
.stCameraInput > label { display: none; }
</style>
""", unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AWS CLIENT HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _aws_kwargs() -> dict:
    return dict(
        region_name=_secret("AWS_DEFAULT_REGION", "us-east-1"),
        aws_access_key_id=_secret("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=_secret("AWS_SECRET_ACCESS_KEY"),
    )


@st.cache_resource(show_spinner=False)
def get_bedrock_client():
    return boto3.client("bedrock-runtime", **_aws_kwargs())


@st.cache_resource(show_spinner=False)
def get_polly_client():
    return boto3.client("polly", **_aws_kwargs())


@st.cache_resource(show_spinner=False)
def get_transcribe_client():
    return boto3.client("transcribe", **_aws_kwargs())


@st.cache_resource(show_spinner=False)
def get_s3_client():
    return boto3.client("s3", **_aws_kwargs())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  IMAGE HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def image_to_jpeg_bytes(uploaded_image) -> bytes:
    """Convert a Streamlit camera capture to compact JPEG bytes."""
    img = Image.open(uploaded_image)
    if img.mode == "RGBA":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AMAZON TRANSCRIBE  (Speech → Text)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def transcribe_audio(audio_bytes: bytes, lang: str) -> str | None:
    """Upload audio to S3, run a Transcribe batch job, poll for the
    result, then clean up temporary objects."""
    bucket = _secret("S3_BUCKET_NAME")
    if not bucket:
        return "S3_BUCKET_NAME not set — voice input requires an S3 bucket."

    s3 = get_s3_client()
    transcribe = get_transcribe_client()

    job_id = uuid.uuid4().hex[:12]
    job_name = f"lakhpati-{job_id}"
    s3_key = f"temp-audio/{job_name}.wav"
    lang_code = "hi-IN" if lang == "Hindi" else "en-US"

    try:
        s3.put_object(Bucket=bucket, Key=s3_key, Body=audio_bytes, ContentType="audio/wav")

        transcribe.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={"MediaFileUri": f"s3://{bucket}/{s3_key}"},
            MediaFormat="wav",
            LanguageCode=lang_code,
        )

        for _ in range(40):
            resp = transcribe.get_transcription_job(TranscriptionJobName=job_name)
            status = resp["TranscriptionJob"]["TranscriptionJobStatus"]
            if status == "COMPLETED":
                uri = resp["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
                text = http_requests.get(uri, timeout=10).json()
                transcript = text["results"]["transcripts"][0]["transcript"]
                _transcribe_cleanup(s3, transcribe, bucket, s3_key, job_name)
                return transcript
            if status == "FAILED":
                _transcribe_cleanup(s3, transcribe, bucket, s3_key, job_name)
                return None
            time.sleep(1.5)

        _transcribe_cleanup(s3, transcribe, bucket, s3_key, job_name)
        return None

    except ClientError as exc:
        return f"Transcribe error: {exc.response['Error']['Message']}"
    except Exception as exc:
        return f"Transcribe error: {exc}"


def _transcribe_cleanup(s3, transcribe, bucket, s3_key, job_name):
    try:
        s3.delete_object(Bucket=bucket, Key=s3_key)
    except Exception:
        pass
    try:
        transcribe.delete_transcription_job(TranscriptionJobName=job_name)
    except Exception:
        pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AMAZON POLLY  (Text → Speech)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def text_to_speech(text: str, lang: str) -> bytes | None:
    """Convert text to MP3 audio using Amazon Polly."""
    polly = get_polly_client()
    text_chunk = text[:2900]

    if lang == "Hindi":
        voice_id, engine, lang_code = "Aditi", "standard", "hi-IN"
    else:
        voice_id, engine, lang_code = "Joanna", "neural", "en-US"

    try:
        resp = polly.synthesize_speech(
            Text=text_chunk,
            OutputFormat="mp3",
            VoiceId=voice_id,
            Engine=engine,
            LanguageCode=lang_code,
        )
        return resp["AudioStream"].read()

    except ClientError as exc:
        st.error(f"Polly error: {exc.response['Error']['Message']}")
        return None
    except Exception as exc:
        st.error(f"Polly error: {exc}")
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AMAZON BEDROCK — Claude Sonnet 4 via Converse API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def analyse_product(text_prompt: str, image_bytes: bytes | None = None) -> str:
    """Send prompt (and optional product image) to Claude via Bedrock Converse API."""
    client = get_bedrock_client()

    content_blocks: list[dict] = []
    if image_bytes:
        content_blocks.append({
            "image": {
                "format": "jpeg",
                "source": {"bytes": image_bytes},
            }
        })
    content_blocks.append({"text": text_prompt})

    try:
        response = client.converse(
            modelId=BEDROCK_MODEL_ID,
            messages=[{"role": "user", "content": content_blocks}],
            inferenceConfig={"maxTokens": 2048},
        )
        return response["output"]["message"]["content"][0]["text"]

    except (NoCredentialsError, PartialCredentialsError):
        return (
            "**AWS credentials not found.**\n\n"
            "Add `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` to `.env` and restart."
        )
    except NoRegionError:
        return "**AWS region not configured.**\n\nSet `AWS_DEFAULT_REGION` in `.env`."
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        msg = exc.response["Error"]["Message"]
        return f"**AWS API Error** (`{code}`)\n\n{msg}"
    except Exception as exc:
        return f"**Unexpected error:** {exc}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SIDEBAR  (kept for extra info, but language is now on main page)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with st.sidebar:
    st.markdown("### 🪷 Lakhpati-Didi AI")
    t_side = UI_TEXT[st.session_state.lang]
    st.markdown("---")
    st.markdown(t_side["sidebar_about"])
    st.markdown("**" + ("कैसे इस्तेमाल करें:" if st.session_state.lang == "Hindi" else "How to use:") + "**")
    for i, step in enumerate(t_side["sidebar_steps"], 1):
        st.markdown(f"{i}. {step}")
    st.markdown("---")
    st.caption(t_side["footer"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  HERO BANNER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
t = UI_TEXT[st.session_state.lang]

st.markdown(f"""
<div class="hero-banner">
    <div class="hero-title">🪷 {t['hero_title']}</div>
    <div class="hero-subtitle">{t['hero_subtitle']}</div>
    <div class="hero-tagline">📸 {t['hero_tagline']}</div>
</div>
""", unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  LANGUAGE SWITCH (pill toggle on main page)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_lang_options = {"🇬🇧  English": "English", "🇮🇳  हिंदी": "Hindi"}
_default = "🇬🇧  English" if st.session_state.lang == "English" else "🇮🇳  हिंदी"

with st.container():
    st.markdown('<div class="lang-toggle-wrap">', unsafe_allow_html=True)
    selected = st.pills(
        "lang_switch",
        options=list(_lang_options.keys()),
        default=_default,
        label_visibility="collapsed",
    )
    st.markdown('</div>', unsafe_allow_html=True)

if selected and _lang_options[selected] != st.session_state.lang:
    st.session_state.lang = _lang_options[selected]
    st.rerun()

t = UI_TEXT[st.session_state.lang]
lang = st.session_state.lang


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  3-STEP FLOW
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.markdown(f"""
<div class="steps-row">
    <div class="step-card">
        <div class="step-num">1</div>
        <div class="step-title">{t['step1_title']}</div>
        <div class="step-desc">{t['step1_desc']}</div>
    </div>
    <div class="step-arrow">→</div>
    <div class="step-card">
        <div class="step-num">2</div>
        <div class="step-title">{t['step2_title']}</div>
        <div class="step-desc">{t['step2_desc']}</div>
    </div>
    <div class="step-arrow">→</div>
    <div class="step-card">
        <div class="step-num">3</div>
        <div class="step-title">{t['step3_title']}</div>
        <div class="step-desc">{t['step3_desc']}</div>
    </div>
</div>
""", unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FEATURE CARDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.markdown(f"""
<div class="features-grid">
    <div class="feat-card">
        <div class="feat-icon">💰</div>
        <div class="feat-title">{t['feat1_title']}</div>
        <div class="feat-desc">{t['feat1_desc']}</div>
    </div>
    <div class="feat-card">
        <div class="feat-icon">📱</div>
        <div class="feat-title">{t['feat2_title']}</div>
        <div class="feat-desc">{t['feat2_desc']}</div>
    </div>
    <div class="feat-card">
        <div class="feat-icon">🎙️</div>
        <div class="feat-title">{t['feat3_title']}</div>
        <div class="feat-desc">{t['feat3_desc']}</div>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown('<div class="soft-divider"></div>', unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CAMERA INPUT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.markdown(f"""
<div class="section-header">
    <div class="section-icon">📸</div>
    <div class="section-label">{t['camera_header']}</div>
</div>
""", unsafe_allow_html=True)

st.markdown(f'<div class="input-help">{t["camera_help"]}</div>', unsafe_allow_html=True)

st.markdown('<div class="input-box">', unsafe_allow_html=True)
captured_image = st.camera_input(t["camera_label"])
st.markdown('</div>', unsafe_allow_html=True)

if captured_image:
    st.markdown('<div class="preview-container">', unsafe_allow_html=True)
    st.image(captured_image, width="stretch")
    st.markdown('</div>', unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  VOICE INPUT  (Amazon Transcribe)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.markdown(f"""
<div class="section-header">
    <div class="section-icon saffron">🎤</div>
    <div class="section-label">{t['voice_header']}</div>
</div>
""", unsafe_allow_html=True)

st.markdown(f'<div class="input-help">{t["voice_help"]}</div>', unsafe_allow_html=True)

st.markdown('<div class="input-box voice">', unsafe_allow_html=True)
recorded_audio = st.audio_input(t["voice_label"])
st.markdown('</div>', unsafe_allow_html=True)

if recorded_audio:
    st.audio(recorded_audio, format="audio/wav")

    if st.button(t["transcribe_btn"], key="transcribe_btn"):
        with st.spinner(t["transcribing"]):
            result = transcribe_audio(recorded_audio.getvalue(), lang)

        if result and "error" not in result.lower() and "not set" not in result.lower():
            st.session_state.transcript = result
        elif result:
            st.warning(result)
        else:
            st.warning(t["transcribe_fail"])

if st.session_state.transcript:
    st.markdown(f"""
    <div class="transcript-box">
        <div class="transcript-label">{t['transcribe_done']}</div>
        {st.session_state.transcript}
    </div>
    """, unsafe_allow_html=True)

st.markdown('<div class="soft-divider"></div>', unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ANALYSE BUTTON  (Amazon Bedrock)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if st.button(t["analyse_btn"], type="primary", key="analyse_btn"):
    has_image = captured_image is not None
    has_voice = bool(st.session_state.transcript)

    if not has_image and not has_voice:
        st.warning(t["no_input_warn"])
    else:
        prompt = t["prompt"]
        if has_voice:
            prompt += f"\n\nUser's voice description / question: {st.session_state.transcript}"
        if not has_image:
            prompt += "\n\n(No product image was provided. Generate the report based on the voice description above.)"

        img_bytes = image_to_jpeg_bytes(captured_image) if has_image else None

        with st.spinner(t["spinner"]):
            st.session_state.analysis = analyse_product(prompt, img_bytes)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  RESULT + LISTEN  (Amazon Polly)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if st.session_state.analysis:
    st.markdown(f'<div class="result-banner">📊 {t["result_header"]}</div>',
                unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown(st.session_state.analysis)

    st.markdown("")
    if st.button(t["listen_btn"], key="listen_btn"):
        with st.spinner(t["listen_spinner"]):
            audio_bytes = text_to_speech(st.session_state.analysis, lang)
        if audio_bytes:
            st.audio(audio_bytes, format="audio/mp3")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FOOTER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.markdown(f'<div class="app-footer">{t["footer"]}</div>', unsafe_allow_html=True)
