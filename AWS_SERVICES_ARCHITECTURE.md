# Lakhpati-Didi AI — AWS Services Architecture Document

> Technical deep-dive into the 5 AWS services powering the hackathon MVP.

---

## Architecture Overview

```
                         ┌──────────────────────────────────┐
                         │        STREAMLIT FRONTEND         │
                         │     (Python · localhost:8501)     │
                         └──────┬───────┬───────┬───────────┘
                                │       │       │
                     ┌──────────┘       │       └──────────┐
                     ▼                  ▼                  ▼
              ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
              │  📸 IMAGE   │   │  🎤 VOICE   │   │  🔊 AUDIO  │
              │   ANALYSIS  │   │    INPUT    │   │   OUTPUT   │
              └──────┬──────┘   └──────┬──────┘   └──────┬──────┘
                     │                 │                  │
                     ▼                 ▼                  ▼
        ┌────────────────────┐ ┌─────────────┐  ┌──────────────┐
        │  AMAZON BEDROCK    │ │  AMAZON S3  │  │ AMAZON POLLY │
        │  Claude 3 Sonnet   │ │  (temp WAV) │  │  (TTS MP3)   │
        │  (Multimodal LLM)  │ └──────┬──────┘  └──────────────┘
        └────────────────────┘        │
                                      ▼
                              ┌──────────────┐
                              │   AMAZON     │
                              │  TRANSCRIBE  │
                              │  (STT Text)  │
                              └──────────────┘
```

**Data Flow Summary:**

| Flow | Path | Latency |
|:-----|:-----|:--------|
| Image → Analysis | Camera → Base64 → Bedrock → Markdown report | 5–10 sec |
| Voice → Text | Mic → WAV → S3 → Transcribe → Transcript | 8–15 sec |
| Text → Speech | Report text → Polly → MP3 → Audio player | 2–4 sec |

---

## Service 1: Amazon Bedrock (AI Brain)

### What it does
Bedrock hosts foundation models (FMs) from leading AI companies. We use **Anthropic Claude 3 Sonnet** — a multimodal model that can understand both images and text simultaneously.

### Why Claude 3 Sonnet
| Criteria | Claude 3 Sonnet | Why it fits |
|:---------|:----------------|:------------|
| Vision | Accepts Base64 images natively | Analyses product photos without a separate vision pipeline |
| Multilingual | Strong Hindi + English | Responds in the user's chosen language |
| Cost | $0.003 / 1K input tokens | 10x cheaper than GPT-4V for similar quality |
| Speed | ~5 sec for image + 2K token response | Fast enough for real-time demo |

### How it's integrated

```python
# 1. Image captured via Streamlit camera
captured_image = st.camera_input("Take a photo")

# 2. Converted to Base64 JPEG (compact payload)
img = Image.open(captured_image)
img.save(buffer, format="JPEG", quality=85)
b64 = base64.standard_b64encode(buffer.getvalue()).decode("utf-8")

# 3. Sent to Bedrock via Messages API
payload = {
    "anthropic_version": "bedrock-2023-10-16",
    "max_tokens": 2048,
    "messages": [{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": b64
                }
            },
            {
                "type": "text",
                "text": "Analyse this product..."
            }
        ]
    }]
}

response = bedrock_client.invoke_model(
    modelId="anthropic.claude-3-sonnet-20240229-v1:0",
    body=json.dumps(payload)
)
```

### What the model returns
For each product photo, Claude provides:
1. Product identification and description
2. Estimated production cost and suggested selling price (in ₹)
3. Profit margin calculation
4. A ready-to-send WhatsApp marketing message
5. 2–3 tips to boost sales

### IAM Permission
```
AmazonBedrockFullAccess
```

### API Endpoint
```
bedrock-runtime.us-east-1.amazonaws.com
```

---

## Service 2: Amazon S3 (Temporary Audio Storage)

### What it does
S3 (Simple Storage Service) acts as a **temporary staging area** for audio files. When a user records a voice question, the WAV audio is uploaded to S3 so that Amazon Transcribe can process it.

### Why S3 is needed
Amazon Transcribe's batch API requires audio files to be stored in S3 — it cannot accept raw audio bytes directly via the API. The flow is:

```
Microphone → WAV bytes → S3 upload → Transcribe reads from S3 → Result
                                          ↓
                              S3 object auto-deleted after use
```

### How it's integrated

```python
# Upload recorded audio to a temp location in S3
s3_key = f"temp-audio/lakhpati-{uuid}.wav"
s3_client.put_object(
    Bucket="lakhpati-didi-audio",
    Key=s3_key,
    Body=audio_bytes,
    ContentType="audio/wav"
)

# After transcription completes — cleanup
s3_client.delete_object(Bucket=bucket, Key=s3_key)
```

### Bucket Structure
```
lakhpati-didi-audio/
└── temp-audio/
    ├── lakhpati-a1b2c3d4e5f6.wav   ← uploaded, then deleted
    ├── lakhpati-f7g8h9i0j1k2.wav   ← uploaded, then deleted
    └── (auto-cleaned after each transcription)
```

### Security Notes
- Audio files exist for **~10–30 seconds** (only during transcription)
- Files are deleted immediately after the transcript is retrieved
- No user data is permanently stored
- Bucket should have **"Block all public access"** enabled (default)

### IAM Permission
```
AmazonS3FullAccess
```

### Cost
Effectively **$0.00** — temp files are deleted before any storage charges apply.

---

## Service 3: Amazon Transcribe (Voice → Text)

### What it does
Transcribe converts spoken audio into text. It supports **Hindi (hi-IN)** and **English (en-US)** — the two languages our app uses.

### Why Transcribe
| Feature | Benefit |
|:--------|:--------|
| Hindi support (`hi-IN`) | Understands rural Hindi accents |
| Automatic punctuation | Clean transcripts without post-processing |
| Speaker diarization | Can separate speakers (future: group discussions) |
| Noise handling | Filters background noise common in rural settings |

### How it's integrated

```python
# 1. Start a batch transcription job
transcribe_client.start_transcription_job(
    TranscriptionJobName=job_name,
    Media={"MediaFileUri": f"s3://{bucket}/{s3_key}"},
    MediaFormat="wav",
    LanguageCode="hi-IN"   # or "en-US"
)

# 2. Poll until complete (typically 5–15 seconds for short clips)
while True:
    resp = transcribe_client.get_transcription_job(
        TranscriptionJobName=job_name
    )
    status = resp["TranscriptionJob"]["TranscriptionJobStatus"]
    if status == "COMPLETED":
        transcript_uri = resp["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
        transcript = requests.get(transcript_uri).json()
        text = transcript["results"]["transcripts"][0]["transcript"]
        break
    time.sleep(1.5)

# 3. Cleanup: delete S3 audio + Transcribe job
s3_client.delete_object(Bucket=bucket, Key=s3_key)
transcribe_client.delete_transcription_job(TranscriptionJobName=job_name)
```

### End-to-End Voice Flow
```
User speaks → st.audio_input() captures WAV
    → Upload WAV to S3
    → Transcribe reads from S3
    → Returns JSON with transcript text
    → Text appended to Claude prompt as "User's additional question"
    → Claude answers with image analysis + voice question together
```

### IAM Permission
```
AmazonTranscribeFullAccess
```

### Supported Languages
| Code | Language | Voice Quality |
|:-----|:---------|:--------------|
| `hi-IN` | Hindi | Good — handles common dialects |
| `en-US` | English | Excellent |
| `en-IN` | Indian English | Good (future option) |
| `ta-IN` | Tamil | Available (future expansion) |
| `bn-IN` | Bengali | Available (future expansion) |

---

## Service 4: Amazon Polly (Text → Speech)

### What it does
Polly converts the AI analysis report into natural-sounding speech so that users who are **less comfortable reading** can listen to their business advice.

### Why Polly
- **Critical for the target audience:** Many rural women entrepreneurs are more comfortable with spoken language
- **Hindi voice (Aditi):** Natural-sounding female voice — matches the "Didi" persona
- **Low latency:** Returns MP3 audio in 2–4 seconds for a typical report
- **No training needed:** Works out of the box, no custom models required

### Voice Selection

| Language | Voice ID | Engine | Gender | Quality |
|:---------|:---------|:-------|:-------|:--------|
| Hindi | **Aditi** | Standard | Female | Natural Hindi pronunciation |
| English | **Joanna** | Neural | Female | High-quality neural voice |

### How it's integrated

```python
# Convert analysis text to speech
response = polly_client.synthesize_speech(
    Text=report_text[:2900],     # Polly limit: 3000 chars per call
    OutputFormat="mp3",
    VoiceId="Aditi",             # Hindi voice
    Engine="standard",
    LanguageCode="hi-IN"
)

audio_bytes = response["AudioStream"].read()

# Play in Streamlit
st.audio(audio_bytes, format="audio/mp3")
```

### Character Limit Handling
Polly's `SynthesizeSpeech` API has a **3,000 character** limit per request. Our approach:
- Typical Claude analysis report: ~800–1500 characters (well within limit)
- Safety truncation at 2,900 characters (leaves buffer for encoding overhead)
- For production: chunk long texts and concatenate audio (future enhancement)

### IAM Permission
```
AmazonPollyFullAccess
```

### All Available Hindi Voices
| Voice | Engine | Gender | Use Case |
|:------|:-------|:-------|:---------|
| **Aditi** | Standard | Female | Current (general purpose) |
| **Kajal** | Neural | Female | Future upgrade (more natural) |

---

## Service 5: Streamlit (Frontend Framework)

### What it does
Streamlit is the Python web framework that ties everything together. It provides the UI, camera input, audio recorder, and renders the AI results — all in a single `app.py` file.

### Why Streamlit (not React/Flask)
| Factor | Streamlit | React + Flask |
|:-------|:----------|:--------------|
| Setup time | 0 config, single file | Hours of boilerplate |
| Camera input | `st.camera_input()` — one line | Complex MediaStream API |
| Audio recorder | `st.audio_input()` — one line | WebRTC + custom UI |
| Deployment | `streamlit run app.py` | Docker + nginx + build step |
| Python-native | Direct `boto3` calls, no API layer | Need REST endpoints |
| Hackathon fit | Perfect for rapid MVP | Overkill for demo |

### Key Streamlit Widgets Used

| Widget | Purpose | AWS Service It Feeds |
|:-------|:--------|:---------------------|
| `st.camera_input()` | Capture product photo | Bedrock (Claude 3 Sonnet) |
| `st.audio_input()` | Record voice question | S3 → Transcribe |
| `st.audio()` | Play Polly TTS output | Polly |
| `st.image()` | Preview captured photo | — |
| `st.button()` | Trigger analysis / transcription / TTS | All services |
| `st.spinner()` | Show loading state during API calls | — |
| `st.session_state` | Persist transcript + analysis across reruns | — |

### Session State Management
```python
# Persists data across Streamlit reruns (button clicks trigger reruns)
st.session_state.transcript = ""    # Voice transcription text
st.session_state.analysis = ""      # Claude's analysis report
```

---

## Complete Request Flow

### Flow A: Image Analysis (Bedrock)
```
1. User clicks camera          → st.camera_input() returns BytesIO (PNG)
2. User clicks "Analyse"       → app.py converts PNG → JPEG → Base64 string
3. Base64 + prompt sent         → boto3 → bedrock-runtime.invoke_model()
4. Claude 3 Sonnet processes    → ~5 sec (image understanding + generation)
5. JSON response parsed         → result["content"][0]["text"]
6. Markdown rendered            → st.markdown(analysis)
```

### Flow B: Voice Input (S3 + Transcribe)
```
1. User clicks record           → st.audio_input() returns BytesIO (WAV)
2. User clicks "Convert"        → app.py uploads WAV to S3
3. Transcribe job started        → start_transcription_job(MediaFileUri=s3://...)
4. Polling loop                  → get_transcription_job() every 1.5 sec
5. Job completes (~8–15 sec)     → transcript URI returned
6. Transcript fetched via HTTP   → JSON parsed → text extracted
7. S3 object + job cleaned up    → delete_object() + delete_transcription_job()
8. Text appended to prompt       → "User's additional question: {transcript}"
```

### Flow C: Listen to Report (Polly)
```
1. User clicks "Listen"         → app.py sends report text to Polly
2. synthesize_speech() called    → VoiceId="Aditi", OutputFormat="mp3"
3. MP3 stream returned (~2 sec)  → response["AudioStream"].read()
4. Audio played in browser       → st.audio(audio_bytes, format="audio/mp3")
```

---

## IAM Policy Summary

All 4 managed policies attached to a single IAM user (`lakhpati-didi-ai`):

| # | Policy | Service | Actions Allowed |
|:--|:-------|:--------|:----------------|
| 1 | `AmazonBedrockFullAccess` | Bedrock | `bedrock:InvokeModel`, model listing |
| 2 | `AmazonPollyFullAccess` | Polly | `polly:SynthesizeSpeech`, voice listing |
| 3 | `AmazonTranscribeFullAccess` | Transcribe | `transcribe:StartTranscriptionJob`, `GetTranscriptionJob`, `DeleteTranscriptionJob` |
| 4 | `AmazonS3FullAccess` | S3 | `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject` |

### Principle of Least Privilege (production upgrade)
For production, replace `AmazonS3FullAccess` with a scoped policy:
```json
{
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
        "Resource": "arn:aws:s3:::lakhpati-didi-audio/temp-audio/*"
    }]
}
```

---

## Environment Variables

```env
AWS_ACCESS_KEY_ID=AKIA...           # IAM user access key
AWS_SECRET_ACCESS_KEY=...           # IAM user secret key
AWS_DEFAULT_REGION=us-east-1        # All services in same region
S3_BUCKET_NAME=lakhpati-didi-audio  # Temp audio bucket
```

All 5 services use the **same credentials and region** — single IAM user, single config.

---

## Cost Analysis (Hackathon Scale)

### Per-Interaction Breakdown

| Step | Service | Input | Cost |
|:-----|:--------|:------|:-----|
| Photo analysis | Bedrock | ~1K input tokens (image) + ~500 output tokens | $0.01 |
| Voice transcription | Transcribe | ~15 sec audio | $0.004 |
| Audio storage | S3 | ~200 KB, deleted in 30 sec | $0.000 |
| Report read-aloud | Polly | ~1000 characters | $0.004 |
| **Total per interaction** | | | **~$0.02** |

### Hackathon Projections

| Scenario | Interactions | Total Cost |
|:---------|:-------------|:-----------|
| Practice runs (10) | 10 | $0.20 |
| Demo to judges (5) | 5 | $0.10 |
| Audience tries it (30) | 30 | $0.60 |
| **Full hackathon day** | **~50** | **~$1.00** |

### AWS Free Tier Coverage
| Service | Free Tier Allowance | Our Usage | Covered? |
|:--------|:-------------------|:----------|:---------|
| Polly | 5 million chars/month (12 months) | ~50K chars | Yes |
| Transcribe | 60 min/month (12 months) | ~12 min | Yes |
| S3 | 5 GB storage | ~10 MB (temp) | Yes |
| Bedrock | No free tier | ~$0.50 | Pay-as-you-go |

> **Bottom line:** A full hackathon day costs **~$1** (only Bedrock charges, rest is free tier).

---

## Security Considerations

| Concern | How We Handle It |
|:--------|:-----------------|
| Credentials in code | Loaded from `.env` via `python-dotenv`, never hardcoded |
| Audio privacy | Temp files deleted within 30 seconds of processing |
| Image privacy | Base64 sent directly to Bedrock, never stored |
| S3 public access | Bucket has "Block all public access" enabled (default) |
| IAM scope | Dedicated user with only required policies |
| `.env` in git | `.gitignore` should exclude `.env` |

---

## Future Scaling Path

| Current (MVP) | Production Upgrade |
|:--------------|:-------------------|
| Streamlit on localhost | ECS Fargate / App Runner behind CloudFront |
| Direct boto3 calls | API Gateway + Lambda (serverless) |
| No persistence | DynamoDB for user profiles + product history |
| Single region | Multi-region (Mumbai `ap-south-1` + Virginia) |
| 1 user at a time | Auto-scaling with ALB |
| No auth | Amazon Cognito (phone OTP login) |
| Batch Transcribe | Transcribe Streaming (real-time) |
| Polly standard | Polly Neural (Kajal voice for Hindi) |

---

*This document covers the complete AWS integration for the Lakhpati-Didi AI hackathon MVP.*
