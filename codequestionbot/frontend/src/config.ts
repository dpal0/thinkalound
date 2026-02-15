const rawBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const normalizedBaseUrl = rawBaseUrl.replace(/\/+$/, "");

export const CONFIG = {
  apiBaseUrl: normalizedBaseUrl,
  useMocks: (import.meta.env.VITE_USE_MOCKS ?? "false") === "true",
  mockQuestionCount: Number(import.meta.env.VITE_MOCK_QUESTION_COUNT ?? "5"),
};
