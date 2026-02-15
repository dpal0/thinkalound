import { CONFIG } from "./config";
import type {
  AnswerBatchResponse,
  AnswerResponse,
  AnswerSubmission,
  AuthMeResponse,
  Grade,
  GradesResponse,
  Question,
  RepoVerifyResponse,
  SubmissionResponse,
} from "./types";

const buildMockQuestions = (count: number): Question[] => {
  return Array.from({ length: count }, (_, index) => ({
    id: `mock-question-${index + 1}`,
    text: `Mock question ${index + 1}: What does this function do?`,
    file_path: "src/example.py",
    line_start: 1,
    line_end: 12,
    excerpt: "def example():\n    return 'hello'\n",
  }));
};

const parseErrorMessage = async (response: Response): Promise<string> => {
  try {
    const data = (await response.json()) as { error?: string };
    if (data && typeof data.error === "string") {
      return data.error;
    }
  } catch {
    // ignore JSON parse errors
  }
  return response.statusText || "Request failed";
};

const fetchJson = async <T>(url: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(url, {
    credentials: "include",
    ...init,
  });
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }
  return (await response.json()) as T;
};

export const getAuthMe = async (): Promise<AuthMeResponse> => {
  if (CONFIG.useMocks) {
    return { authenticated: true, github_login: "mock-user", is_instructor: false };
  }
  return fetchJson<AuthMeResponse>(`${CONFIG.apiBaseUrl}/auth/me`);
};

export const logout = async (): Promise<void> => {
  if (CONFIG.useMocks) {
    return;
  }
  await fetchJson(`${CONFIG.apiBaseUrl}/auth/logout`, { method: "POST" });
};

export const verifyRepo = async (repoUrl: string): Promise<RepoVerifyResponse> => {
  if (CONFIG.useMocks) {
    return { ok: true, owner: "mock-user", name: "mock-repo" };
  }

  return fetchJson<RepoVerifyResponse>(`${CONFIG.apiBaseUrl}/repos/verify`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ repo_url: repoUrl }),
  });
};

export const createSubmission = async (
  repoUrl: string
): Promise<SubmissionResponse> => {
  if (CONFIG.useMocks) {
    return {
      submission_id: "mock-submission",
      status: "ready",
      questions: buildMockQuestions(CONFIG.mockQuestionCount),
    };
  }

  return fetchJson<SubmissionResponse>(`${CONFIG.apiBaseUrl}/submissions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ repo_url: repoUrl }),
  });
};

export const submitAnswers = async (
  answers: AnswerSubmission[]
): Promise<AnswerResponse[]> => {
  if (CONFIG.useMocks) {
    return answers.map((_, index) => ({
      answer_id: `mock-answer-${index + 1}`,
      grade_id: `mock-grade-${index + 1}`,
      score: 4,
    }));
  }

  const payload = await fetchJson<AnswerBatchResponse>(
    `${CONFIG.apiBaseUrl}/answers`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ answers }),
    }
  );

  return payload.answers;
};

export const getGrades = async (submissionId: string): Promise<Grade[]> => {
  if (CONFIG.useMocks) {
    return [
      { answer_id: "mock-1", score: 4, rationale: "Good explanation.", confidence: 0.85 },
    ];
  }
  const response = await fetchJson<GradesResponse>(
    `${CONFIG.apiBaseUrl}/submissions/${submissionId}/grades`
  );
  return response.grades;
};

export const getCsvExportUrl = (): string => {
  return `${CONFIG.apiBaseUrl}/exports/submissions.csv`;
};

export const getAuthUrl = (): string => {
  return `${CONFIG.apiBaseUrl}/auth/github`;
};
