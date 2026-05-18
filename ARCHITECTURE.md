# Continuum — Architecture

This document describes how Continuum is structured end to end: client, API, agent layer, pipeline stages, and VideoDB integration.

For setup and runtime instructions, see [README.md](./README.md).

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
| **Agents** | Creative planning and narration copy (OpenAI) |
| **Pipeline modules** | Ingest, index, search, compose (VideoDB SDK) |

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

    Discovery[discovery/youtube.py]
    VDBClient[videodb_client.py]
  end

  ApiTs --> Main
  Main --> Jobs
  Main --> Orch
  Main --> PromptOpt
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
  Ingest --> VDBClient
  Index --> VDBClient
  Search --> VDBClient
  Compose --> VDBClient
  Narrator --> VDBClient
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
  participant N as Narrator

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

  Note over O,N: NARRATING
  loop each chapter
    O->>N: generate_narration
    N->>V: generate_voice
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
  Chapters --> NarrGen[Narrator\nvoice script → VideoDB voice]

  ClipSel --> Search[VideoDB search\nspoken + scene/visual]
  Search --> Clips[ClipCandidate\nvideo_id, start, end]

  Clips --> Compose
  NarrGen --> Compose[compose.py\nTimeline assembly]
```

| Agent / module | Input | Output |
|----------------|-------|--------|
| **Director** | Topic + source summaries | `DocumentaryBlueprint` |
| **Scriptwriter** | Blueprint + topic + sources | Scenes with narration & search hints |
| **Planner** | Orchestrates director → scriptwriter | `ChapterPlan[]` |
| **Clip selector** | Chapters + collection + sources | Best non-overlapping clip per chapter |
| **Narrator** | Chapter narration text | VideoDB `audio_id` + duration |

---

## 5. VideoDB integration map

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

  subgraph Output["Final render"]
    VO["generate_voice"]
    TL["Timeline API<br/>video, text, audio tracks"]
    STR["generate_stream"]
    SRCH --> TL
    VO --> TL
    TL --> STR
  end

  STR --> Player["Browser or VideoDB player URL"]
```

---

## 6. Timeline composition (one scene block)

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

## 7. Request / data flow (optimize vs create)

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
    Pipeline --> Meta[Job metadata\nfilm_title, clips, duration]
  end

  subgraph PollPath["Poll until ready"]
    CreateAPI --> Poll[GET /api/documentaries/id]
    Poll --> Job
    Job -->|stage=ready| Stream[stream_url + player_url]
  end
```

---

## 8. Deployment view (local dev)

```mermaid
flowchart TB
  Browser[Browser :5173]
  Vite[Vite dev server\nproxy /api → :8000]
  Uvicorn[Uvicorn\nFastAPI :8000]
  Env[continuum/.env\nAPI keys]

  Browser --> Vite
  Vite --> Uvicorn
  Uvicorn --> Env
  Uvicorn --> VideoDB[(VideoDB)]
  Uvicorn --> OpenAI[(OpenAI)]
  Uvicorn --> YouTube[(YouTube API\noptional)]
```

---

## Key architectural decisions (summary)

| Decision | Rationale |
|----------|-----------|
| Plan **after** index | Search queries match real uploaded media |
| One **collection** per job | Isolated corpus; easy debugging in VideoDB console |
| **Triple** index | Different retrieval modes for documentary editing |
| **Sequential** timeline blocks | Avoid overlapping narration and dual-audio issues |
| **In-memory** jobs | Hackathon simplicity; no DB migrations |
| Background **thread** per job | Non-blocking API; UI polls for progress |

---

*Continuum — Give agents eyes and ears. Let them direct something real.*
