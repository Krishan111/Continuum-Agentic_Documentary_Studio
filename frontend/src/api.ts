import type { DocumentaryJob } from "./types";

export async function createDocumentary(
  topic: string,
  useDemoSources: boolean
): Promise<DocumentaryJob> {
  const res = await fetch("/api/documentaries", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, use_demo_sources: useDemoSources }),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || "Failed to start documentary");
  }
  return res.json();
}

export type OptimizePromptResult = {
  original: string;
  optimized: string;
  word_count: number;
  char_count: number;
};

/** Matches backend CreateDocumentaryRequest.topic max_length */
export const TOPIC_MAX_CHARS = 499;

export async function optimizePrompt(prompt: string): Promise<OptimizePromptResult> {
  const res = await fetch("/api/optimize-prompt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
  if (!res.ok) {
    let detail = "Failed to optimize prompt";
    try {
      const data = await res.json();
      if (typeof data.detail === "string") detail = data.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function getDocumentary(jobId: string): Promise<DocumentaryJob> {
  const res = await fetch(`/api/documentaries/${jobId}`);
  if (!res.ok) {
    throw new Error("Job not found");
  }
  return res.json();
}
