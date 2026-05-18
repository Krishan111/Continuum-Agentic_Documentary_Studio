# Continuum — Architecture

This document describes how Continuum is structured end to end: client, API, agent layer, pipeline stages, **pluggable voice generation**, and VideoDB integration.

For setup and runtime instructions, see [README.md](./README.md).  
For switching narration backends (OpenAI TTS vs VideoDB Sandbox vs hosted voice), see [README — Voice generation](./README.md#voice-generation-switch-provider).

### How to view the flowcharts

The diagrams are **[Mermaid](https://mermaid.js.org)** code inside ` ```mermaid ` blocks. If you only see text like `flowchart LR` and arrows (`-->`), you are in **source view**, not rendered preview.

| Where you open the file | What to do |
|-------------------------|------------|
| **Cursor / VS Code** | Open `ARCHITECTURE.md` → **Markdown: Open Preview** (`Ctrl+Shift+V` on Windows, `Cmd+Shift+V` on Mac). If charts still don’t render, install the extension **“Markdown Preview Mermaid Support”** and preview again. |
| **GitHub** | Push the repo and open the file on github.com — Mermaid renders automatically in `.md` files. |
| **Browser (any)** | Copy one ` ```mermaid ` … ` ``` ` block → paste at [mermaid.live](https://mermaid.live) → export PNG/SVG. |

---


## 1. System overview

Continuum is a **three-tier** system: a React UI polls a FastAPI backend, which orchestrates OpenAI agents and the VideoDB SDK to produce a streamed documentary.

```mermaid
flowchart LR
  subgraph Client
    UI[React + Vite\nlocalhost:5173]
  end

  subgraph Server
    API[FastAPI\nlocalhost:8000]
    Store[(In-memory\njob store)]
    Orch[Pipeline\norchestrator]
  end

  subgraph External
    OAI[OpenAI API]
    YT[YouTube Data API\noptional]
    VDB[VideoDB Cloud]
  end

  UI -->|POST /api/documentaries\nGET poll job| API
  UI -->|POST /api/optimize-prompt| API
  API --> Store
  API --> Orch
  Orch --> OAI
  Orch --> YT
  Orch --> VDB
  Store -->|stage, progress, stream_url| API
```

| Layer | Responsibility |
|-------|----------------|
| **Frontend** | Topic input, prompt optimization, stage progress, video player |
| **API** | REST endpoints, background task scheduling, CORS |
| **Orchestrator** | Single linear pipeline per `job_id` |
| **Agents** | Creative planning and narration **scripts** (OpenAI) |
| **`app/voice/`** | Pluggable TTS: produces VideoDB `audio_id` per chapter (see §5) |
| **Pipeline modules** | Ingest, index, search, compose (VideoDB SDK) |

**Important:** `VIDEO_DB_API_KEY` is always required for video ingest, index, search, and timeline. **Narration** is a separate switch (`CONTINUUM_VOICE_PROVIDER`) — it does not replace the API key.

---

## 2. Component architecture

```mermaid
flowchart TB
  subgraph frontend ["frontend/"]
    App[App.tsx]
    ApiTs[api.ts]
    App --> ApiTs
  end

  subgraph backend ["backend/app/"]
    Main[main.py]
    Jobs[jobs.py]
    Orch[orchestrator.py]

    subgraph agents_pkg ["agents/"]
      Director[director.py]
      Scriptwriter[scriptwriter.py]
      Planner[planner.py]
      ClipSel[clip_selector.py]
      Narrator[narrator.py]
      PromptOpt[prompt_optimizer.py]
    end

    subgraph pipeline_pkg ["pipeline/"]
      Ingest[ingest.py]
      Index[index_media.py]
      Search[search_clips.py]
      Compose[compose.py]
    end

    subgraph voice_pkg ["voice/ — CONTINUUM_VOICE_PROVIDER"]
      VoiceReg["__init__.py\nregistry"]
      VDef[videodb_default.py]
      VSand[videodb_sandbox.py]
      VOAI[openai_tts.py]
    end

    Discovery[discovery/youtube.py]
    Config[config.py]
    VDBClient[videodb_client.py]
  end

  ApiTs --> Main
  Main --> Jobs
  Main --> Orch
  Main --> PromptOpt
  Main --> Config
  Orch --> Discovery
  Orch --> Ingest
  Orch --> Index
  Orch --> Planner
  Orch --> ClipSel
  Orch --> Narrator
  Orch --> Compose
  Planner --> Director
  Planner --> Scriptwriter
  ClipSel --> Search
  Narrator --> VoiceReg
  VoiceReg --> VDef
  VoiceReg --> VSand
  VoiceReg --> VOAI
  Config --> VoiceReg
  Ingest --> VDBClient
  Index --> VDBClient
  Search --> VDBClient
  Compose --> VDBClient
  VDef --> VDBClient
  VSand --> VDBClient
  VOAI --> VDBClient
```

---

## 3. Documentary pipeline (sequence)

Each job runs **one background thread** through these stages. Progress and `stage` are written to the job store after each step.

```mermaid
sequenceDiagram
  autonumber
  participant U as User / UI
  participant API as FastAPI
  participant O as Orchestrator
  participant D as YouTube discovery
  participant V as VideoDB
  participant P as Planner (Director + Scriptwriter)
  participant C as Clip selector
  participant N as narrator.py
  participant Voice as app/voice
  participant OAI as OpenAI API

  U->>API: POST /api/documentaries (topic)
  API->>O: run_documentary_pipeline(job_id)
  API-->>U: job_id (poll)

  Note over O,V: CAPTURING
  O->>V: create_collection(job)
  O->>V: create_capture_session(metadata)

  Note over O,D: DISCOVERING
  O->>D: discover_sources(topic)
  D-->>O: YouTube URLs[]

  Note over O,V: UPLOADING
  O->>V: upload URLs → IngestedVideo[]

  Note over O,V: INDEXING
  loop each source
    O->>V: index_spoken_words
    O->>V: index_visuals (scene)
    O->>V: index_audio
  end

  Note over O,P: PLANNING
  O->>P: plan_documentary(topic, sources)
  P-->>O: blueprint + ChapterPlan[]

  Note over O,C: SELECTING_CLIPS
  O->>C: select_clips_for_chapters
  C->>V: search per chapter / per video
  C-->>O: (chapter, ClipCandidate)[]

  Note over O,Voice: NARRATING
  loop each chapter
    O->>N: generate_narration(chapter)
    N->>Voice: generate_chapter_narration(text)
    alt provider is openai_tts
      Voice->>OAI: audio.speech.create
      Voice->>V: collection.upload MP3
    else provider is videodb_sandbox
      Voice->>V: ensure sandbox then OmniVoice
    else provider is videodb_default
      Voice->>V: hosted generate_voice Default
    end
    Voice-->>N: NarrationAudio
    N-->>O: audio_id, duration
  end

  Note over O,V: COMPOSING
  O->>V: Timeline + tracks + generate_stream
  V-->>O: stream_url, player_url

  O->>API: stage=ready, stream_url
  U->>API: GET /api/documentaries by job id
  API-->>U: player + metadata
```

### Pipeline stages (UI labels)

```mermaid
flowchart LR
  Q[queued] --> CAP[capturing]
  CAP --> DIS[discovering]
  DIS --> UPL[uploading]
  UPL --> IDX[indexing]
  IDX --> PLN[planning]
  PLN --> SEL[selecting_clips]
  SEL --> NAR[narrating]
  NAR --> COM[composing]
  COM --> RDY[ready]

  Q -.->|error| FAIL[failed]
  CAP -.-> FAIL
  DIS -.-> FAIL
  UPL -.-> FAIL
  IDX -.-> FAIL
  PLN -.-> FAIL
  SEL -.-> FAIL
  NAR -.-> FAIL
  COM -.-> FAIL
```

---

## 4. Creative agent flow

Planning is intentionally **split** and runs **after** indexing so scripts reference real source titles.

```mermaid
flowchart TB
  Topic[User topic]
  Sources[Ingested sources\nwith titles + lengths]

  Topic --> Director
  Sources --> Director

  Director[Director agent\nDocumentaryBlueprint]
  Director -->|logline, tone, arc, hook| Scriptwriter

  Sources --> Scriptwriter
  Scriptwriter[Scriptwriter agent\nProductionScript scenes]

  Scriptwriter --> Chapters[ChapterPlan per scene\ntitle, narration,\nsearch_query, visual_direction,\npause_after_sec, preferred_source]

  Chapters --> ClipSel[Clip selector]
  Chapters --> NarrGen[narrator.py]

  ClipSel --> Search[VideoDB search\nspoken + scene/visual]
  Search --> Clips[ClipCandidate\nvideo_id, start, end]

  Clips --> Compose
  NarrGen --> VoiceMod[app/voice\npluggable TTS]
  VoiceMod --> Compose[compose.py\nTimeline uses audio_id]

```

| Agent / module | Input | Output |
|----------------|-------|--------|
| **Director** | Topic + source summaries | `DocumentaryBlueprint` |
| **Scriptwriter** | Blueprint + topic + sources | Scenes with narration & search hints |
| **Planner** | Orchestrates director → scriptwriter | `ChapterPlan[]` |
| **Clip selector** | Chapters + collection + sources | Best non-overlapping clip per chapter |
| **`narrator.py`** | `ChapterPlan` | Delegates to `app/voice/` |
| **`app/voice/`** | Narration text + collection | `NarrationAudio` (`audio_id`, duration, provider) |

---

## 5. Voice generation (pluggable providers)

Narration is **not** hard-wired to a single `collection.generate_voice` call. The orchestrator always ends up with a VideoDB **`audio_id`** for timeline compose; **how** that audio is created is selected by `CONTINUUM_VOICE_PROVIDER` in `continuum/.env` (resolved in `config.py` → `app/voice/__init__.py`).

### Three providers (one active at a time)

| Provider ID | Module | What it does |
|-------------|--------|----------------|
| `openai_tts` | `voice/openai_tts.py` | OpenAI Speech API → temp MP3 → `collection.upload` → `audio_id` |
| `videodb_sandbox` | `voice/videodb_sandbox.py` | OmniVoice on **VideoDB Sandbox** GPU pool (`SandboxModel.OMNIVOICE`, `sandbox_id=...`) |
| `videodb_default` | `voice/videodb_default.py` | VideoDB **hosted** voice (`voice_name=Default`, plan GenAI quota) |

Verify at runtime: `GET /health` → `voice_provider`, `voice_provider_label`.

### Sandbox vs API key vs OpenAI (common reviewer question)

```mermaid
flowchart TB
  subgraph Always["Always required"]
    KEY["VIDEO_DB_API_KEY"]
    KEY --> Ingest["upload / index / search"]
    KEY --> TL["Timeline + generate_stream"]
  end

  subgraph VoiceSwitch["CONTINUUM_VOICE_PROVIDER — narration only"]
    P{provider?}
    P -->|openai_tts| OAI["OpenAI TTS API\n(not VideoDB voice quota)"]
    OAI --> Up["upload audio to collection"]
    P -->|videodb_sandbox| SB["Sandbox compute pool\nconn.create_sandbox"]
    SB --> OV["generate_voice\nOmniVoice + sandbox_id"]
    P -->|videodb_default| HV["hosted generate_voice\nDefault voice"]
  end

  Up --> AudioId["audio_id in collection"]
  OV --> AudioId
  HV --> AudioId
  AudioId --> TL
```

| Concept | Meaning |
|---------|---------|
| **VideoDB API key** | Authenticates all SDK calls (collections, indexing, search, timeline, uploads). |
| **Sandbox** | Optional **GPU compute rental** inside VideoDB for self-hosted models (OmniVoice, FLUX, VLMs). Created via `conn.create_sandbox()`; pass `sandbox_id` into `generate_voice`. **Not** a substitute for the API key. |
| **Hosted `videodb_default`** | VideoDB runs TTS on their side; subject to plan voice caps. |
| **`openai_tts`** | TTS happens on OpenAI; Continuum only **stores** the result in VideoDB for the same compose path. |

**Hackathon demo path:** `videodb_sandbox` (deep VideoDB + bypasses default voice caps).  
**Evaluation / no VideoDB voice credits:** `openai_tts`.

### Code path (read order for reviewers)

```text
orchestrator.py
  → agents/narrator.py::generate_narration()
  → voice/__init__.py::generate_chapter_narration()
  → voice/<provider>.py::generate()
  → returns NarrationAudio(audio_id, duration_sec, provider)
  → compose.py uses narration_audio_id on Timeline
```

Sandbox-specific logic (`ensure_sandbox_id`, `wait_for_ready`, cached sandbox ID) lives only in `voice/videodb_sandbox.py`. Helper script: `scripts/create_sandbox.py`.

---

## 6. VideoDB integration map

```mermaid
flowchart TB
  subgraph Job["Per-job VideoDB resources"]
    Coll["Collection per job<br/>continuum plus job id"]
    Cap["Capture session"]
    Vids["Uploaded videos"]
    Coll --> Cap
    Coll --> Vids
  end

  subgraph Index["Triple index per video"]
    SW["index_spoken_words"]
    VIS["index_visuals<br/>scene index"]
    AUD["index_audio semantics"]
    Vids --> SW
    Vids --> VIS
    Vids --> AUD
  end

  subgraph Retrieve["Per chapter"]
    SRCH["search and search_inside_video<br/>spoken plus scene"]
    SW --> SRCH
    VIS --> SRCH
  end

  subgraph Voice["Narration per chapter"]
    VP["app/voice provider"]
    VP --> AID["audio_id in collection"]
  end

  subgraph Output["Final render"]
    TL["Timeline API<br/>video, text, audio tracks"]
    STR["generate_stream"]
    SRCH --> TL
    AID --> TL
    TL --> STR
  end

  STR --> Player["Browser or VideoDB player URL"]
```

Narration enters the timeline as a normal VideoDB audio asset regardless of provider; only the **creation path** differs (see §5).

---

## 7. Timeline composition (one scene block)

The composer builds **sequential scene blocks** so narration never overlaps between chapters.

```mermaid
flowchart LR
  subgraph Block["Single chapter timeline block"]
    direction LR
    L[B-roll lead\n~1.5s]
    V[Narration audio\nstarts after lead]
    T[B-roll tail\n~0.7s]
    P["Pause min 0.8s"]
    L --> V --> T --> P
  end

  B1[Block 1] --> B2[Block 2]
  B2 --> B3[Block N]
  B3 --> Outro[Outro + titles]

  subgraph Tracks["Timeline tracks"]
    VT[Video track\nmuted B-roll clips]
    TT[Text track\nchapter titles]
    AT[Audio track\nvoiceover]
  end

  Block --> VT
  Block --> AT
```

**Design intent:** B-roll plays under narration with controlled lead-in/out; a gap (`pause_after_sec`) separates chapters before the next block starts.

---

## 8. Request / data flow (optimize vs create)

```mermaid
flowchart TB
  subgraph OptimizePath["Optional: refine topic"]
    T1[Short user prompt]
    T1 --> OptAPI[POST /api/optimize-prompt]
    OptAPI --> OptAgent[prompt_optimizer.py]
    OptAgent --> T2["Structured topic max 499 chars"]
  end

  subgraph CreatePath["Create documentary"]
    T2 --> CreateAPI[POST /api/documentaries]
    T1 --> CreateAPI
    CreateAPI --> Job[JobRecord\ntopic, stage, progress]
    Job --> BG[BackgroundTasks\npipeline thread]
    BG --> Pipeline["Full pipeline section 3"]
    Pipeline --> Meta[Job metadata\nfilm_title, clips, voice_provider]
  end

  subgraph PollPath["Poll until ready"]
    CreateAPI --> Poll[GET /api/documentaries/id]
    Poll --> Job
    Job -->|stage=ready| Stream[stream_url + player_url]
  end
```

---

## 9. Deployment view (local dev)

```mermaid
flowchart TB
  Browser[Browser :5173]
  Vite[Vite dev server\nproxy /api → :8000]
  Uvicorn[Uvicorn\nFastAPI :8000]
  Env["continuum/.env\nVIDEO_DB_API_KEY\nCONTINUUM_VOICE_PROVIDER\nOPENAI_API_KEY"]

  Browser --> Vite
  Vite --> Uvicorn
  Uvicorn --> Env
  Uvicorn --> VideoDB[(VideoDB\nvideo + timeline)]
  Uvicorn --> OpenAI[(OpenAI\nplanning + optional TTS)]
  Uvicorn --> YouTube[(YouTube API\noptional)]
```

When `CONTINUUM_VOICE_PROVIDER=openai_tts`, OpenAI is used at **narrating** time only; VideoDB still handles all video operations.

---

## Key architectural decisions (summary)

| Decision | Rationale |
|----------|-----------|
| Plan **after** index | Search queries match real uploaded media |
| One **collection** per job | Isolated corpus; easy debugging in VideoDB console |
| **Triple** index | Different retrieval modes for documentary editing |
| **Sequential** timeline blocks | Avoid overlapping narration and dual-audio issues |
| **Pluggable voice** (`app/voice/`) | Judges can run without VideoDB voice quota; same compose path via `audio_id` |
| **Sandbox for demo** | `videodb_sandbox` routes OmniVoice to dedicated compute, not hosted GenAI caps |
| **In-memory** jobs | Hackathon simplicity; no DB migrations |
| Background **thread** per job | Non-blocking API; UI polls for progress |

---

*Continuum — Give agents eyes and ears. Let them direct something real.*
