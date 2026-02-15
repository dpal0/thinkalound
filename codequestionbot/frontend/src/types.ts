export type Question = {
  id: string;
  text: string;
  file_path: string;
  line_start: number;
  line_end: number;
  excerpt: string;
};

export type SubmissionResponse = {
  submission_id: string;
  status: "ready" | "pending" | "error";
  questions: Question[];
};

export type AuthMeResponse = {
  authenticated: boolean;
  github_login?: string;
  is_instructor?: boolean;
};

export type RepoVerifyResponse = {
  ok: true;
  owner: string;
  name: string;
};

export type AnswerSubmission = {
  submission_id: string;
  question_id: string;
  answer_text: string;
  time_spent_ms?: number;
  paste_attempts?: number;
  focus_loss_count?: number;
  typing_stats?: Record<string, unknown> | null;
};

export type AnswerResponse = {
  answer_id: string;
  question_id?: string;
  status?: "queued" | "graded";
  grade_id?: string;
  score?: number;
};

export type AnswerBatchResponse = {
  answers: AnswerResponse[];
};

export type Grade = {
  answer_id: string;
  score: number;
  rationale: string;
  confidence: number;
};

export type GradesResponse = {
  grades: Grade[];
};
