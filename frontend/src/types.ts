export type StageStatus = "pending" | "active" | "done" | "failed";

export interface StageInfo {
  id: string;
  label: string;
  status: StageStatus;
}

export interface DocumentaryJob {
  job_id: string;
  topic: string;
  stage: string;
  stage_label: string;
  progress: number;
  stages: StageInfo[];
  message: string;
  stream_url?: string | null;
  player_url?: string | null;
  collection_id?: string | null;
  capture_session_id?: string | null;
  error?: string | null;
  metadata?: Record<string, unknown>;
}
