import { useEffect, useState, type FormEvent } from "react";
import {
  createSubmission,
  getCsvExportUrl,
  getAuthMe,
  getAuthUrl,
  getGrades,
  logout,
  verifyRepo,
  submitAnswers,
} from "./api";
import type { AnswerSubmission, Grade, SubmissionResponse } from "./types";

type Stage = "submit" | "questions" | "submitted";
type AuthStatus = "loading" | "authenticated" | "unauthenticated";

const isValidRepoUrl = (value: string): boolean => {
  return /^https:\/\/github\.com\/[^/]+\/[^/]+\/?$/.test(value);
};

export default function App() {
  const [repoUrl, setRepoUrl] = useState("");
  const [authStatus, setAuthStatus] = useState<AuthStatus>("loading");
  const [authLogin, setAuthLogin] = useState<string | null>(null);
  const [isInstructor, setIsInstructor] = useState(false);
  const [stage, setStage] = useState<Stage>("submit");
  const [submission, setSubmission] = useState<SubmissionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitPhase, setSubmitPhase] = useState<
    "idle" | "verifying" | "generating"
  >("idle");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [isSubmittingAnswers, setIsSubmittingAnswers] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [pasteCounts, setPasteCounts] = useState<Record<string, number>>({});
  const [focusLossCount, setFocusLossCount] = useState(0);
  const [timeSpent, setTimeSpent] = useState<Record<string, number>>({});
  const [activeTimers, setActiveTimers] = useState<Record<string, number | null>>(
    {}
  );
  const [invalidAnswers, setInvalidAnswers] = useState<Set<string>>(new Set());
  const [grades, setGrades] = useState<Grade[]>([]);
  const [isLoadingGrades, setIsLoadingGrades] = useState(false);

  useEffect(() => {
    let mounted = true;
    getAuthMe()
      .then((response) => {
        if (!mounted) {
          return;
        }
        if (response.authenticated) {
          setAuthStatus("authenticated");
          setAuthLogin(response.github_login ?? null);
          setIsInstructor(Boolean(response.is_instructor));
        } else {
          setAuthStatus("unauthenticated");
        }
      })
      .catch(() => {
        if (mounted) {
          setAuthStatus("unauthenticated");
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);

    if (!isValidRepoUrl(repoUrl)) {
      setError("Enter a valid GitHub repo URL (https://github.com/user/repo).");
      return;
    }

    try {
      setSubmitPhase("verifying");
      await verifyRepo(repoUrl);
      setSubmitPhase("generating");
      const result = await createSubmission(repoUrl);
      setSubmission(result);
      setStage("questions");
      const seededAnswers = result.questions.reduce<Record<string, string>>(
        (acc, question) => {
          acc[question.id] = "";
          return acc;
        },
        {}
      );
      setAnswers(seededAnswers);
      const seededTimers = result.questions.reduce<Record<string, number>>(
        (acc, question) => {
          acc[question.id] = 0;
          return acc;
        },
        {}
      );
      setTimeSpent(seededTimers);
      setPasteCounts(
        result.questions.reduce<Record<string, number>>((acc, question) => {
          acc[question.id] = 0;
          return acc;
        }, {})
      );
      setActiveTimers(
        result.questions.reduce<Record<string, number | null>>((acc, question) => {
          acc[question.id] = null;
          return acc;
        }, {})
      );
      setFocusLossCount(0);
      setInvalidAnswers(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to submit repo.");
    } finally {
      setSubmitPhase("idle");
    }
  };

  const handleReset = () => {
    setRepoUrl("");
    setSubmission(null);
    setStage("submit");
    setError(null);
    setAnswers({});
    setSubmitError(null);
    setPasteCounts({});
    setFocusLossCount(0);
    setTimeSpent({});
    setActiveTimers({});
    setSubmitPhase("idle");
    setInvalidAnswers(new Set());
    setGrades([]);
    setIsLoadingGrades(false);
  };

  const handleLogout = async () => {
    try {
      await logout();
    } finally {
      setAuthStatus("unauthenticated");
      setAuthLogin(null);
      setIsInstructor(false);
      handleReset();
    }
  };

  const handleAnswerChange = (questionId: string, value: string) => {
    setAnswers((current) => ({
      ...current,
      [questionId]: value,
    }));
    setInvalidAnswers((current) => {
      if (!current.has(questionId)) {
        return current;
      }
      const next = new Set(current);
      next.delete(questionId);
      return next;
    });
  };

  const handleSubmitAnswers = async () => {
    if (!submission) {
      return;
    }
    setSubmitError(null);

    const emptyIds = submission.questions
      .filter((question) => !answers[question.id]?.trim())
      .map((question) => question.id);

    if (emptyIds.length > 0) {
      setInvalidAnswers(new Set(emptyIds));
      setSubmitError("Please answer all questions before submitting.");
      return;
    }

    const now = Date.now();
    const effectiveTimeSpent = { ...timeSpent };
    Object.entries(activeTimers).forEach(([questionId, start]) => {
      if (start) {
        effectiveTimeSpent[questionId] =
          (effectiveTimeSpent[questionId] ?? 0) + (now - start);
      }
    });

    const payload: AnswerSubmission[] = submission.questions.map((question) => ({
      submission_id: submission.submission_id,
      question_id: question.id,
      answer_text: answers[question.id] ?? "",
      time_spent_ms: effectiveTimeSpent[question.id] ?? 0,
      paste_attempts: pasteCounts[question.id] ?? 0,
      focus_loss_count: focusLossCount,
      typing_stats: null,
    }));

    setIsSubmittingAnswers(true);
    localStorage.removeItem(`cqbot:answers:${repoUrl}`);

    try {
      await submitAnswers(payload);
      setStage("submitted");
      setIsLoadingGrades(true);

      // Poll for grades
      let attempts = 0;
      const maxAttempts = 60;
      const poll = () => {
        if (attempts >= maxAttempts) {
          setIsLoadingGrades(false);
          return;
        }
        attempts++;
        getGrades(submission.submission_id)
          .then((gradesList) => {
            if (gradesList.length >= submission.questions.length) {
              setGrades(gradesList);
              setIsLoadingGrades(false);
            } else {
              setTimeout(poll, 2000);
            }
          })
          .catch(() => {
            setTimeout(poll, 2000);
          });
      };
      setTimeout(poll, 3000);
    } catch (err) {
      console.error("Answer submission failed:", err);
      setSubmitError(
        err instanceof Error ? err.message : "Unable to submit answers."
      );
    } finally {
      setIsSubmittingAnswers(false);
    }
  };

  const handlePaste = (questionId: string) => {
    setPasteCounts((current) => ({
      ...current,
      [questionId]: (current[questionId] ?? 0) + 1,
    }));
  };

  const handleFocus = (questionId: string) => {
    setActiveTimers((current) => {
      if (current[questionId]) {
        return current;
      }
      return {
        ...current,
        [questionId]: Date.now(),
      };
    });
  };

  const handleBlur = (questionId: string) => {
    setActiveTimers((current) => {
      const start = current[questionId];
      if (!start) {
        return current;
      }
      const elapsed = Date.now() - start;
      setTimeSpent((prev) => ({
        ...prev,
        [questionId]: (prev[questionId] ?? 0) + elapsed,
      }));
      return {
        ...current,
        [questionId]: null,
      };
    });
  };

  const syncKey = stage === "questions" ? `cqbot:answers:${repoUrl}` : null;

  useEffect(() => {
    if (!syncKey || !submission) {
      return;
    }
    const cached = localStorage.getItem(syncKey);
    if (!cached) {
      return;
    }
    try {
      const parsed = JSON.parse(cached) as {
        answers?: Record<string, string>;
        timeSpent?: Record<string, number>;
      };
      if (parsed.answers) {
        setAnswers((current) => ({ ...current, ...parsed.answers }));
      }
      if (parsed.timeSpent) {
        setTimeSpent((current) => ({ ...current, ...parsed.timeSpent }));
      }
    } catch {
      localStorage.removeItem(syncKey);
    }
  }, [syncKey, submission]);

  useEffect(() => {
    if (!syncKey) {
      return;
    }
    localStorage.setItem(
      syncKey,
      JSON.stringify({
        answers,
        timeSpent,
      })
    );
  }, [answers, timeSpent, syncKey]);

  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === "hidden") {
        setFocusLossCount((count) => count + 1);
      }
    };
    window.addEventListener("blur", handleVisibility);
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      window.removeEventListener("blur", handleVisibility);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, []);


  const exportUrl = getCsvExportUrl();
  const isSubmitting = submitPhase !== "idle";
  const submitLabel =
    submitPhase === "verifying"
      ? "Verifying repo..."
      : submitPhase === "generating"
      ? "Preparing questions..."
      : "Generate questions";

  if (authStatus === "loading") {
    return (
      <main className="app">
        <section className="panel auth-panel">
          <h1>Checking your session…</h1>
          <p className="subhead">Verifying GitHub sign-in status.</p>
        </section>
      </main>
    );
  }

  if (authStatus === "unauthenticated") {
    return (
      <main className="app">
        <section className="panel auth-panel">
          <p className="eyebrow">CodeQuestionBot</p>
          <h1>Sign in to continue.</h1>
          <p className="subhead">
            We use GitHub to confirm your identity and request read access to the
            repo you submit.
          </p>
          <a className="primary link-button" href={getAuthUrl()}>
            Sign in with GitHub
          </a>
        </section>
      </main>
    );
  }

  return (
    <main className="app">
      <header className="hero">
        <div className="hero-top">
          <div>
            <p className="eyebrow">CodeQuestionBot</p>
            {authLogin ? (
              <p className="subhead">Signed in as {authLogin}</p>
            ) : null}
          </div>
          <button className="ghost" type="button" onClick={handleLogout}>
            Sign out
          </button>
        </div>
        <h1>Explain your code with confidence.</h1>
        <p className="subhead">
          Submit a GitHub repo and get a focused, code-specific question set.
        </p>
      </header>

      <section className="panel">
        {stage === "submit" ? (
          <form className="repo-form" onSubmit={handleSubmit}>
            <label htmlFor="repo-url">GitHub repository URL</label>
            <input
              id="repo-url"
              name="repo-url"
              type="url"
              placeholder="https://github.com/yourname/your-repo"
              value={repoUrl}
              onChange={(event) => {
                setRepoUrl(event.target.value);
                setError(null);
              }}
              required
            />
            {error ? <p className="error">{error}</p> : null}
            <button className="primary" type="submit" disabled={isSubmitting}>
              {submitLabel}
            </button>
          </form>
        ) : null}

        {stage === "questions" && submission ? (
          <div className="question-state">
            <div className="question-header">
              <div>
                <p className="eyebrow">Questions ready</p>
                <h2>Answer each prompt in your own words.</h2>
                <p className="subhead">
                  Repo: <span className="mono">{repoUrl}</span>
                </p>
              </div>
              <div className="question-summary">
                <p>Be precise and reference the code shown.</p>
                {focusLossCount > 0 ? (
                  <p className="warning">
                    Keep this tab active. Focus lost {focusLossCount}{" "}
                    {focusLossCount === 1 ? "time" : "times"}.
                  </p>
                ) : null}
              </div>
            </div>

            <div className="question-list">
              {submission.questions.map((question, index) => (
                <article className="question-card" key={question.id}>
                  <header className="question-meta">
                    <span className="badge">Q{index + 1}</span>
                    <span className="mono">
                      {question.file_path}:{question.line_start}-
                      {question.line_end}
                    </span>
                  </header>
                  <h3>{question.text}</h3>
                  <pre className="snippet">{question.excerpt}</pre>
                  <label htmlFor={`answer-${question.id}`}>Your answer</label>
                  <textarea
                    id={`answer-${question.id}`}
                    name={`answer-${question.id}`}
                    value={answers[question.id] ?? ""}
                    onChange={(event) =>
                      handleAnswerChange(question.id, event.target.value)
                    }
                    onPaste={(event) => {
                      event.preventDefault();
                      handlePaste(question.id);
                    }}
                    onFocus={() => handleFocus(question.id)}
                    onBlur={() => handleBlur(question.id)}
                    rows={5}
                    placeholder="Explain your reasoning here..."
                    className={
                      invalidAnswers.has(question.id) ? "textarea-error" : undefined
                    }
                  />
                  {pasteCounts[question.id] ? (
                    <p className="warning">
                      Paste is disabled for responses.
                    </p>
                  ) : null}
                </article>
              ))}
            </div>

            {submitError ? <p className="error">{submitError}</p> : null}

            <div className="actions">
              <button className="ghost" type="button" onClick={handleReset}>
                Start over
              </button>
              <button
                className="primary"
                type="button"
                onClick={handleSubmitAnswers}
                disabled={isSubmittingAnswers}
              >
                {isSubmittingAnswers ? "Submitting answers..." : "Submit answers"}
              </button>
            </div>
          </div>
        ) : null}

        {stage === "submitted" ? (
          <div className="ready-state">
            <div>
              <h2>Answers submitted.</h2>
              {isLoadingGrades ? (
                <p className="subhead">Grading in progress… please wait.</p>
              ) : grades.length > 0 && submission ? (() => {
                const totalScore = grades.reduce((sum, g) => sum + g.score, 0);
                const maxScore = grades.length * 5;
                const pct = Math.round((totalScore / maxScore) * 100);
                const avgConfidence = Math.round(
                  (grades.reduce((sum, g) => sum + g.confidence, 0) / grades.length) * 100
                );
                const level =
                  pct >= 80 ? "Excellent" :
                  pct >= 60 ? "Good" :
                  pct >= 40 ? "Needs Improvement" :
                  "Insufficient";
                const levelClass =
                  pct >= 80 ? "level-excellent" :
                  pct >= 60 ? "level-good" :
                  pct >= 40 ? "level-fair" :
                  "level-low";

                return (
                  <div className="grades-section">
                    <div className="score-summary">
                      <div className="score-ring-wrap">
                        <div className={`score-ring ${levelClass}`}>
                          <span className="score-pct">{pct}%</span>
                        </div>
                      </div>
                      <div className="score-details">
                        <h3 className="score-level">{level}</h3>
                        <p className="subhead">
                          {totalScore} / {maxScore} points across {grades.length} questions
                        </p>
                        <p className="subhead" style={{fontSize: "0.85rem"}}>
                          Average grading confidence: {avgConfidence}%
                        </p>
                      </div>
                    </div>

                    <div className="question-list">
                      {submission.questions.map((question, index) => {
                        const grade = grades[index];
                        return (
                          <article className="question-card" key={question.id}>
                            <header className="question-meta">
                              <span className="badge">Q{index + 1}</span>
                              {grade ? (
                                <span className={`badge score-badge ${grade.score >= 4 ? "score-high" : grade.score >= 3 ? "score-mid" : "score-low"}`}>
                                  {grade.score} / 5
                                </span>
                              ) : null}
                            </header>
                            <h3>{question.text}</h3>
                            <pre className="snippet">{question.excerpt}</pre>
                            <p><strong>Your answer:</strong> {answers[question.id]}</p>
                            {grade ? (
                              <div className="grade-feedback">
                                <p><strong>Feedback:</strong> {grade.rationale}</p>
                              </div>
                            ) : null}
                          </article>
                        );
                      })}
                    </div>
                  </div>
                );
              })() : (
                <p className="subhead">
                  Thanks for completing the question set. Your responses are now
                  being graded.
                </p>
              )}
            </div>
            <div className="actions">
              <button className="primary" type="button" onClick={handleReset}>
                Submit another repo
              </button>
            </div>
          </div>
        ) : null}
      </section>

      {isInstructor ? (
        <section className="panel instructor-panel">
          <div>
            <p className="eyebrow">Instructor tools</p>
            <h2>Export grades as CSV.</h2>
            <p className="subhead">
              Download a current snapshot of submissions, scores, and integrity flags.
            </p>
          </div>
          <a className="ghost link-button" href={exportUrl}>
            Download CSV export
          </a>
        </section>
      ) : null}
    </main>
  );
}
