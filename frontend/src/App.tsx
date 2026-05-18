import { useCallback, useEffect, useState } from "react";
import {
  createDocumentary,
  getDocumentary,
  optimizePrompt,
  TOPIC_MAX_CHARS,
} from "./api";
import type { DocumentaryJob } from "./types";
import "./App.css";

const TOPIC_PLACEHOLDER = "A documentary on indian moon landing";

const DEMO_TOPICS = [
  "A documentary on indian moon landing",
  "history of artificial intelligence",
];

const POLL_MS = 2500;

export default function App() {
  const [topic, setTopic] = useState("");
  const [topicBeforeOptimize, setTopicBeforeOptimize] = useState<string | null>(
    null
  );
  const [useDemo, setUseDemo] = useState(true);
  const [job, setJob] = useState<DocumentaryJob | null>(null);
  const [loading, setLoading] = useState(false);
  const [optimizing, setOptimizing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const poll = useCallback(async (jobId: string) => {
    try {
      const data = await getDocumentary(jobId);
      setJob(data);
      if (data.stage === "failed") {
        setError(data.error || "Pipeline failed");
      }
    } catch {
      setError("Lost connection to server");
    }
  }, []);

  useEffect(() => {
    if (!job?.job_id) return;
    if (job.stage === "ready" || job.stage === "failed") return;

    const id = setInterval(() => poll(job.job_id), POLL_MS);
    return () => clearInterval(id);
  }, [job?.job_id, job?.stage, poll]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    setJob(null);
    try {
      const created = await createDocumentary(topic.trim(), useDemo);
      setJob(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const isRunning =
    job != null && job.stage !== "ready" && job.stage !== "failed";

  const formLocked = loading || optimizing || isRunning;

  const handleOptimize = async () => {
    const trimmed = topic.trim();
    if (trimmed.length < 3) {
      setError("Enter at least 3 characters before optimizing.");
      return;
    }
    setError(null);
    setOptimizing(true);
    try {
      const result = await optimizePrompt(trimmed);
      setTopicBeforeOptimize(trimmed);
      setTopic(result.optimized);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Optimization failed");
    } finally {
      setOptimizing(false);
    }
  };

  const handleUndoOptimize = () => {
    if (topicBeforeOptimize !== null) {
      setTopic(topicBeforeOptimize);
      setTopicBeforeOptimize(null);
    }
  };

  const handleTopicChange = (value: string) => {
    setTopic(value.length > TOPIC_MAX_CHARS ? value.slice(0, TOPIC_MAX_CHARS) : value);
  };

  return (
    <div className="page">
      <header className="hero">
        <p className="eyebrow">Powered by VideoDB</p>
        <h1>Continuum</h1>
        <p className="tagline">
          Type a topic. An agent discovers footage, indexes memory on VideoDB,
          plans chapters with AI, and composes a narrated documentary you can
          stream in minutes.
        </p>
      </header>

      <form className="card form-card" onSubmit={handleSubmit}>
        <div className="topic-field">
          <div className="topic-field-header">
            <label htmlFor="topic">Documentary topic</label>
            <div className="topic-actions">
              {topicBeforeOptimize !== null && (
                <button
                  type="button"
                  className="icon-btn"
                  onClick={handleUndoOptimize}
                  disabled={formLocked}
                  title="Undo optimization"
                  aria-label="Undo optimization"
                >
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden
                  >
                    <path d="M3 10h10a5 5 0 0 1 5 5v2" />
                    <path d="M3 10l4-4M3 10l4 4" />
                  </svg>
                  <span>Undo</span>
                </button>
              )}
              <button
                type="button"
                className="icon-btn icon-btn--accent"
                onClick={handleOptimize}
                disabled={formLocked || topic.trim().length < 3}
                title="Optimize prompt"
                aria-label="Optimize prompt"
              >
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden
                >
                  <path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z" />
                  <path d="M5 19l1 2 2 1-2 1-1 2-2-1-1-2z" />
                  <path d="M19 13l.8 1.6 1.6.8-1.6.8-.8 1.6-.8-1.6-1.6-.8 1.6-.8.8-1.6z" />
                </svg>
                <span>{optimizing ? "Optimizing…" : "Optimize"}</span>
              </button>
            </div>
          </div>
          <textarea
            id="topic"
            rows={3}
            value={topic}
            onChange={(e) => handleTopicChange(e.target.value)}
            placeholder={TOPIC_PLACEHOLDER}
            maxLength={TOPIC_MAX_CHARS}
            disabled={formLocked}
          />
          <p className="topic-hint">
            {topic.length}/{TOPIC_MAX_CHARS} characters
          </p>
        </div>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={useDemo}
            onChange={(e) => setUseDemo(e.target.checked)}
            disabled={formLocked}
          />
          Use pre-validated demo sources (recommended for first run)
        </label>
        <div className="demo-chips">
          {DEMO_TOPICS.map((t) => (
            <button
              key={t}
              type="button"
              className="chip"
              onClick={() => {
                setTopic(t);
                setTopicBeforeOptimize(null);
              }}
              disabled={formLocked}
            >
              {t}
            </button>
          ))}
        </div>
        <button
          type="submit"
          className="primary"
          disabled={loading || isRunning || topic.trim().length < 3}
        >
          {loading ? "Starting…" : isRunning ? "Producing…" : "Create documentary"}
        </button>
        {error && <p className="error">{error}</p>}
      </form>

      {job && (
        <section className="card pipeline-card">
          <div className="pipeline-header">
            <h2>Production pipeline</h2>
            <span className="progress-pill">{Math.round(job.progress)}%</span>
          </div>
          <p className="stage-message">{job.message || job.stage_label}</p>
          <ul className="stages">
            {job.stages.map((s) => (
              <li key={s.id} className={`stage stage--${s.status}`}>
                <span className="stage-dot" aria-hidden />
                <span className="stage-label">{s.label}</span>
              </li>
            ))}
          </ul>
          {typeof job.metadata?.film_title === "string" && (
            <p className="meta">
              <strong>{job.metadata.film_title as string}</strong>
              {typeof job.metadata.logline === "string" && (
                <> — {job.metadata.logline as string}</>
              )}
            </p>
          )}
          {Array.isArray(job.metadata?.scenes) && (
            <p className="meta">
              Scenes: {(job.metadata.scenes as string[]).join(" · ")}
            </p>
          )}
          {typeof job.metadata?.distinct_source_videos === "number" && (
            <p className="meta">
              Source videos used: {job.metadata.distinct_source_videos}
            </p>
          )}
        </section>
      )}

      {job?.stage === "ready" && job.stream_url && (
        <section className="card player-card">
          <h2>
            {(job.metadata?.film_title as string) || "Your documentary"}
          </h2>
          <div className="player-wrap">
            <video
              controls
              playsInline
              src={job.stream_url}
              className="player"
            />
          </div>
          {job.player_url && (
            <a
              href={job.player_url}
              target="_blank"
              rel="noreferrer"
              className="player-link"
            >
              Open in VideoDB player
            </a>
          )}
        </section>
      )}

      <footer className="footer">
        <span>See → Understand → Act</span>
        <a href="https://docs.videodb.io" target="_blank" rel="noreferrer">
          VideoDB docs
        </a>
      </footer>
    </div>
  );
}
