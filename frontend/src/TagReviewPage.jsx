import { useEffect, useState } from "react";

const FILTERS = [
  { id: "needs_review", label: "Needs review" },
  { id: "all", label: "All cases" },
  { id: "reviewed", label: "Reviewed" },
  { id: "no_organism", label: "No organism" },
  { id: "no_syndrome", label: "No syndrome" },
  { id: "no_host", label: "No host" },
];

const CASE_SECTIONS = [
  { key: "history", label: "History" },
  { key: "exam_studies", label: "Exam / Studies" },
  { key: "diagnosis", label: "Diagnosis" },
  { key: "more_info", label: "More info" },
];

function matchesFilter(item, filterId) {
  if (filterId === "all") return true;
  if (filterId === "needs_review") return item.needs_review;
  if (filterId === "reviewed") return !item.needs_review;
  if (filterId === "no_organism") return item.machine_answer_counts.organisms === 0;
  if (filterId === "no_syndrome") return item.machine_answer_counts.syndromes === 0;
  if (filterId === "no_host") return item.machine_answer_counts.hosts === 0;
  return true;
}

function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function pillStyle(tone = "default") {
  const tones = {
    default: {
      background: "var(--surface-0)",
      color: "var(--text-secondary)",
      border: "1px solid var(--border)",
    },
    accent: {
      background: "var(--bg-accent)",
      color: "var(--text-accent)",
      border: "1px solid var(--border-accent)",
    },
    success: {
      background: "var(--bg-success)",
      color: "var(--text-success)",
      border: "1px solid var(--border-success)",
    },
  };
  return {
    display: "inline-flex",
    alignItems: "center",
    padding: "4px 9px",
    borderRadius: 999,
    fontSize: 12,
    lineHeight: 1.2,
    whiteSpace: "nowrap",
    ...tones[tone],
  };
}

function QueueItem({ item, selected, onSelect }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      style={{
        width: "100%",
        border: "none",
        borderLeft: selected ? "3px solid var(--border-accent)" : "3px solid transparent",
        background: selected ? "var(--bg-accent)" : "transparent",
        padding: "12px 14px 12px 12px",
        textAlign: "left",
        cursor: "pointer",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 6 }}>
        <span style={{ fontFamily: "monospace", fontSize: 11, color: "var(--text-accent)", fontWeight: 700 }}>{item.id}</span>
        <span style={pillStyle(item.needs_review ? "accent" : "success")}>
          {item.reviewer_count} review{item.reviewer_count === 1 ? "" : "s"}
        </span>
      </div>
      <div style={{ fontSize: 13, lineHeight: 1.45, color: "var(--text-primary)", marginBottom: 8 }}>{item.title}</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        <span style={pillStyle()}>Org {item.machine_answer_counts.organisms}</span>
        <span style={pillStyle()}>Syn {item.machine_answer_counts.syndromes}</span>
        <span style={pillStyle()}>Host {item.machine_answer_counts.hosts}</span>
      </div>
    </button>
  );
}

function FigureGallery({ caseId, figures }) {
  if (!figures?.length) return null;
  return (
    <section style={caseSectionCard}>
      <div style={caseSectionHeader}>Images</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
        {figures.map((figure) => (
          <a
            key={figure}
            href={`/case-images/${caseId}/${figure}`}
            target="_blank"
            rel="noreferrer"
            style={{ display: "block", borderRadius: 12, overflow: "hidden", border: "1px solid var(--border)", background: "var(--surface-0)" }}
          >
            <img
              src={`/case-images/${caseId}/${figure}`}
              alt={`${caseId} ${figure}`}
              style={{ width: "100%", height: 180, objectFit: "cover", display: "block" }}
            />
            <div style={{ padding: "8px 10px", fontSize: 12, color: "var(--text-secondary)" }}>{figure}</div>
          </a>
        ))}
      </div>
    </section>
  );
}

function CaseSection({ label, text }) {
  return (
    <section style={caseSectionCard}>
      <div style={caseSectionHeader}>{label}</div>
      <div style={{ whiteSpace: "pre-wrap", fontSize: 14, lineHeight: 1.75, color: "var(--text-primary)" }}>
        {text || "No text available."}
      </div>
    </section>
  );
}

function SuggestedTags({ values }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
      {values.length > 0 ? (
        values.map((value) => (
          <span key={value} style={pillStyle("accent")}>{value}</span>
        ))
      ) : (
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>No machine suggestion</span>
      )}
    </div>
  );
}

function ChipInput({ label, values, suggestions, onChange, placeholder }) {
  const [inputValue, setInputValue] = useState("");

  function addValue(rawValue) {
    const candidate = rawValue.trim().replace(/,$/, "");
    if (!candidate) return;
    const next = [...values];
    if (!next.some((value) => value.toLowerCase() === candidate.toLowerCase())) {
      next.push(candidate);
      onChange(next);
    }
    setInputValue("");
  }

  function removeValue(target) {
    onChange(values.filter((value) => value !== target));
  }

  return (
    <div style={reviewFieldCard}>
      <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>Suggested tags</div>
      <SuggestedTags values={suggestions} />
      <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)", margin: "14px 0 8px" }}>{label}</div>
      <div style={chipWrap}>
        {values.map((value) => (
          <span key={value} style={chipStyle}>
            {value}
            <button
              type="button"
              onClick={() => removeValue(value)}
              style={chipRemoveButton}
              aria-label={`Remove ${value}`}
            >
              ×
            </button>
          </span>
        ))}
        <input
          value={inputValue}
          onChange={(event) => setInputValue(event.target.value)}
          onBlur={() => addValue(inputValue)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === ",") {
              event.preventDefault();
              addValue(inputValue);
            } else if (event.key === "Backspace" && !inputValue && values.length > 0) {
              removeValue(values[values.length - 1]);
            }
          }}
          placeholder={placeholder}
          style={chipInput}
        />
      </div>
    </div>
  );
}

function PriorReviewCard({ review }) {
  return (
    <div style={{ ...reviewFieldCard, gap: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>{review.reviewer_name}</div>
        <span style={pillStyle(review.decision === "accepted" ? "success" : "accent")}>{review.decision}</span>
      </div>
      <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{formatDateTime(review.updated_at || review.created_at)}</div>
      {review.comments ? (
        <div style={{ fontSize: 13, lineHeight: 1.6, color: "var(--text-secondary)", whiteSpace: "pre-wrap" }}>{review.comments}</div>
      ) : null}
    </div>
  );
}

export default function TagReviewPage({ onBack, authToken, currentUser }) {
  const [queue, setQueue] = useState([]);
  const [summary, setSummary] = useState(null);
  const [queueLoading, setQueueLoading] = useState(true);
  const [queueError, setQueueError] = useState("");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("needs_review");
  const [selectedCaseId, setSelectedCaseId] = useState(null);
  const [detailByCaseId, setDetailByCaseId] = useState({});
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [selectedReviewerId, setSelectedReviewerId] = useState(currentUser?.user_id || "");
  const [draft, setDraft] = useState({
    reviewer_user_id: currentUser?.user_id || "",
    organisms: [],
    syndromes: [],
    hosts: [],
    comments: "",
  });
  const [saveState, setSaveState] = useState({ tone: "", message: "" });
  const [hasLocalEdits, setHasLocalEdits] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  function authHeaders(extra = {}) {
    return {
      Authorization: `Bearer ${authToken}`,
      ...extra,
    };
  }

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: authHeaders(options.headers || {}),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data?.detail || "Request failed");
    return data;
  }

  async function loadQueue() {
    setQueueLoading(true);
    setQueueError("");
    try {
      const data = await fetchJson("/api/v1/tag-review/cases");
      setQueue(data.cases || []);
      setSummary(data.summary || null);
    } catch (err) {
      setQueueError(err.message || "Unable to load review queue");
    } finally {
      setQueueLoading(false);
    }
  }

  async function loadDetail(caseId, reviewerUserId) {
    if (!caseId) return null;
    setDetailLoading(true);
    setDetailError("");
    try {
      const data = await fetchJson(`/api/v1/tag-review/cases/${caseId}?reviewer_user_id=${encodeURIComponent(reviewerUserId)}`);
      setDetailByCaseId((current) => ({ ...current, [caseId]: data }));
      return data;
    } catch (err) {
      setDetailError(err.message || "Unable to load case detail");
      return null;
    } finally {
      setDetailLoading(false);
    }
  }

  useEffect(() => {
    loadQueue();
  }, []);

  const filteredQueue = queue
    .filter((item) => matchesFilter(item, filter))
    .filter((item) => {
      const query = search.trim().toLowerCase();
      if (!query) return true;
      return (
        item.id.toLowerCase().includes(query)
        || item.title.toLowerCase().includes(query)
        || [...item.machine_answers.organisms, ...item.machine_answers.syndromes, ...item.machine_answers.hosts].join(" ").toLowerCase().includes(query)
      );
    });

  useEffect(() => {
    if (!filteredQueue.length) {
      setSelectedCaseId(null);
      return;
    }
    if (!selectedCaseId || !filteredQueue.some((item) => item.id === selectedCaseId)) {
      setSelectedCaseId(filteredQueue[0].id);
    }
  }, [filteredQueue, selectedCaseId]);

  useEffect(() => {
    if (!selectedCaseId || !selectedReviewerId) return;
    loadDetail(selectedCaseId, selectedReviewerId).then((data) => {
      if (!data) return;
      const source = data.current_draft || data.reviews.find((review) => review.reviewer_user_id === selectedReviewerId) || data.machine_answers;
      setDraft({
        reviewer_user_id: selectedReviewerId,
        organisms: [...(source.organisms || [])],
        syndromes: [...(source.syndromes || [])],
        hosts: [...(source.hosts || [])],
        comments: source.comments || "",
      });
      setHasLocalEdits(false);
      setSaveState({ tone: "", message: "" });
    });
  }, [selectedCaseId, selectedReviewerId]);

  useEffect(() => {
    if (!selectedCaseId || !selectedReviewerId || !hasLocalEdits) return undefined;
    const timeoutId = window.setTimeout(async () => {
      try {
        const data = await fetchJson(`/api/v1/tag-review/cases/${selectedCaseId}/draft`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(draft),
        });
        setSaveState({
          tone: "success",
          message: `Autosaved ${formatDateTime(data.draft?.updated_at)} · UUID ${data.draft?.watermark_uuid || "—"}`,
        });
        setHasLocalEdits(false);
      } catch (err) {
        setSaveState({ tone: "error", message: err.message || "Autosave failed" });
      }
    }, 700);
    return () => window.clearTimeout(timeoutId);
  }, [draft, hasLocalEdits, selectedCaseId, selectedReviewerId]);

  const selectedDetail = selectedCaseId ? detailByCaseId[selectedCaseId] : null;

  async function submitReview() {
    if (!selectedCaseId) return;
    setSubmitting(true);
    try {
      const data = await fetchJson(`/api/v1/tag-review/cases/${selectedCaseId}/reviews`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      });
      setSaveState({
        tone: "success",
        message: `Review submitted · UUID ${data.review?.watermark_uuid || "—"} · ${formatDateTime(data.review?.updated_at || data.review?.created_at)}`,
      });
      await Promise.all([loadQueue(), loadDetail(selectedCaseId, selectedReviewerId)]);
      setHasLocalEdits(false);
    } catch (err) {
      setSaveState({ tone: "error", message: err.message || "Unable to submit review" });
    } finally {
      setSubmitting(false);
    }
  }

  function updateDraft(patch) {
    setDraft((current) => ({ ...current, ...patch, reviewer_user_id: selectedReviewerId }));
    setHasLocalEdits(true);
  }

  const saveTone = saveState.tone === "error"
    ? { color: "var(--text-danger)" }
    : saveState.tone === "success"
      ? { color: "var(--text-success)" }
      : { color: "var(--text-muted)" };

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", background: "var(--surface-0)", fontFamily: "var(--font-sans)" }}>
      <div style={{
        padding: "10px 18px",
        borderBottom: "1px solid var(--border)",
        background: "var(--surface-1)",
        display: "flex",
        alignItems: "center",
        gap: 10,
        flexWrap: "wrap",
      }}>
        <button onClick={onBack} style={smallButton}>← Back</button>
        <span style={{ ...pillStyle("accent"), fontWeight: 700 }}>Pending {summary?.pending_cases ?? "—"}</span>
        <span style={pillStyle()}>Reviewed {summary?.reviewed_cases ?? "—"}</span>
        <span style={pillStyle()}>Total {summary?.total_cases ?? "—"}</span>
        <span style={pillStyle()}>Submitted reviews {summary?.total_reviews ?? "—"}</span>
      </div>

      <div style={{ flex: 1, minHeight: 0, display: "grid", gridTemplateColumns: "320px minmax(0, 1fr) 360px", overflow: "hidden" }}>
        <aside style={{ borderRight: "1px solid var(--border)", background: "var(--surface-1)", display: "flex", flexDirection: "column", minHeight: 0 }}>
          <div style={{ padding: "14px 14px 12px", borderBottom: "1px solid var(--border)" }}>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search case title or tags..."
              style={searchInput}
            />
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 10 }}>
              {FILTERS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setFilter(item.id)}
                  style={{
                    padding: "5px 9px",
                    borderRadius: 999,
                    border: "1px solid var(--border-strong)",
                    background: filter === item.id ? "var(--bg-accent)" : "var(--surface-0)",
                    color: filter === item.id ? "var(--text-accent)" : "var(--text-secondary)",
                    cursor: "pointer",
                    fontSize: 12,
                  }}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 10 }}>
              {queueLoading ? "Loading queue..." : `${filteredQueue.length} visible of ${queue.length}`}
            </div>
          </div>
          <div style={{ flex: 1, overflowY: "auto" }}>
            {queueError ? (
              <div style={{ padding: 16, color: "var(--text-danger)", fontSize: 13 }}>{queueError}</div>
            ) : queueLoading ? (
              <div style={{ padding: 16, color: "var(--text-muted)", fontSize: 13 }}>Loading cases...</div>
            ) : filteredQueue.length === 0 ? (
              <div style={{ padding: 16, color: "var(--text-muted)", fontSize: 13 }}>No cases match this filter.</div>
            ) : (
              filteredQueue.map((item) => (
                <QueueItem
                  key={item.id}
                  item={item}
                  selected={item.id === selectedCaseId}
                  onSelect={() => setSelectedCaseId(item.id)}
                />
              ))
            )}
          </div>
        </aside>

        <main style={{ overflowY: "auto", padding: "18px 18px 40px" }}>
          {!selectedDetail ? (
            <div style={emptyStateCard}>
              {detailLoading ? "Loading case..." : "Choose a case from the left to review."}
            </div>
          ) : (
            <div style={{ display: "grid", gap: 14 }}>
              <section style={{ ...caseSectionCard, background: "linear-gradient(135deg, var(--surface-1), var(--surface-0))" }}>
                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 14, flexWrap: "wrap" }}>
                  <div>
                    <div style={{ fontFamily: "monospace", fontSize: 12, color: "var(--text-accent)", fontWeight: 700, marginBottom: 8 }}>
                      {selectedDetail.case.id}
                    </div>
                    <h1 style={{ fontSize: 24, lineHeight: 1.2, margin: 0, color: "var(--text-primary)", letterSpacing: "-0.03em" }}>
                      {selectedDetail.case.title}
                    </h1>
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <span style={pillStyle(selectedDetail.review_summary.needs_review ? "accent" : "success")}>
                      {selectedDetail.review_summary.needs_review ? "Needs review" : "Reviewed"}
                    </span>
                    <span style={pillStyle()}>{selectedDetail.review_summary.reviewer_count} reviewers</span>
                    <span style={pillStyle()}>{selectedDetail.case.figures?.length || 0} images</span>
                  </div>
                </div>
                <div style={{ marginTop: 12, display: "flex", gap: 12, flexWrap: "wrap", fontSize: 12, color: "var(--text-secondary)" }}>
                  <span>Last reviewed: {formatDateTime(selectedDetail.review_summary.last_reviewed_at)}</span>
                  <span>Required reviewers: {selectedDetail.review_summary.required_reviews_per_case}</span>
                </div>
              </section>

              {selectedDetail.case.figures?.length ? (
                <FigureGallery caseId={selectedDetail.case.id} figures={selectedDetail.case.figures} />
              ) : null}

              {CASE_SECTIONS.map((section) => (
                <CaseSection key={section.key} label={section.label} text={selectedDetail.case[section.key]} />
              ))}
            </div>
          )}
        </main>

        <aside style={{ borderLeft: "1px solid var(--border)", background: "var(--surface-1)", overflowY: "auto", padding: "18px 16px 40px" }}>
          {!selectedDetail ? (
            <div style={emptyStateCard}>Pick a case to start reviewing.</div>
          ) : (
            <div style={{ display: "grid", gap: 14 }}>
              <section style={reviewPanelCard}>
                <div style={{ fontSize: 18, fontWeight: 700, color: "var(--text-primary)", marginBottom: 12 }}>Expert review</div>
                <label style={{ display: "grid", gap: 6, marginBottom: 12 }}>
                  <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Reviewer</span>
                  <select
                    value={selectedReviewerId}
                    onChange={(event) => setSelectedReviewerId(event.target.value)}
                    disabled={currentUser?.role !== "admin"}
                    style={selectStyle}
                  >
                    {(selectedDetail.reviewer_directory || []).map((reviewer) => (
                      <option key={reviewer.user_id} value={reviewer.user_id}>
                        {reviewer.display_name} ({reviewer.role})
                      </option>
                    ))}
                  </select>
                </label>

                <ChipInput
                  label="Organism(s)"
                  values={draft.organisms}
                  suggestions={selectedDetail.machine_answers.organisms || []}
                  onChange={(values) => updateDraft({ organisms: values })}
                  placeholder="Type organism and press Enter"
                />
                <ChipInput
                  label="Syndrome(s)"
                  values={draft.syndromes}
                  suggestions={selectedDetail.machine_answers.syndromes || []}
                  onChange={(values) => updateDraft({ syndromes: values })}
                  placeholder="Type syndrome and press Enter"
                />
                <ChipInput
                  label="Host characteristic(s)"
                  values={draft.hosts}
                  suggestions={selectedDetail.machine_answers.hosts || []}
                  onChange={(values) => updateDraft({ hosts: values })}
                  placeholder="Type host characteristic and press Enter"
                />

                <div style={reviewFieldCard}>
                  <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>Comments</div>
                  <textarea
                    value={draft.comments}
                    onChange={(event) => updateDraft({ comments: event.target.value })}
                    placeholder="Comments, rationale, or uncertainty"
                    style={commentBox}
                  />
                </div>

                <div style={{ fontSize: 12, ...saveTone }}>
                  {saveState.message || "Autosave is on. Each draft and submitted review gets a backend UUID watermark and timestamp."}
                </div>
                <button
                  type="button"
                  onClick={submitReview}
                  disabled={submitting}
                  style={{
                    padding: "10px 14px",
                    borderRadius: 10,
                    border: "1px solid var(--border-accent)",
                    background: submitting ? "var(--fill-disabled)" : "var(--fill-accent)",
                    color: "var(--on-accent)",
                    cursor: submitting ? "not-allowed" : "pointer",
                    fontSize: 14,
                    fontWeight: 700,
                  }}
                >
                  {submitting ? "Submitting..." : "Submit review"}
                </button>
              </section>

              <section style={reviewPanelCard}>
                <div style={{ fontSize: 16, fontWeight: 700, color: "var(--text-primary)", marginBottom: 10 }}>Prior reviews</div>
                <div style={{ display: "grid", gap: 10 }}>
                  {selectedDetail.reviews.length > 0 ? (
                    selectedDetail.reviews.map((review) => (
                      <PriorReviewCard key={review.review_id || `${review.reviewer_user_id}-${review.updated_at}`} review={review} />
                    ))
                  ) : (
                    <div style={{ fontSize: 13, color: "var(--text-muted)" }}>No submitted reviews yet.</div>
                  )}
                </div>
              </section>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

const caseSectionCard = {
  padding: "16px 18px",
  border: "1px solid var(--border)",
  borderRadius: 14,
  background: "var(--surface-1)",
};

const caseSectionHeader = {
  fontSize: 15,
  fontWeight: 800,
  color: "var(--text-primary)",
  textTransform: "uppercase",
  letterSpacing: "0.08em",
  marginBottom: 12,
};

const reviewPanelCard = {
  padding: "16px 16px 18px",
  border: "1px solid var(--border)",
  borderRadius: 14,
  background: "var(--surface-1)",
  display: "grid",
  gap: 12,
};

const reviewFieldCard = {
  padding: "12px 12px 14px",
  border: "1px solid var(--border)",
  borderRadius: 12,
  background: "var(--surface-0)",
  display: "grid",
  gap: 8,
};

const searchInput = {
  width: "100%",
  padding: "9px 11px",
  borderRadius: 10,
  border: "1px solid var(--border-strong)",
  background: "var(--surface-0)",
  color: "var(--text-primary)",
  fontSize: 13,
  boxSizing: "border-box",
};

const chipWrap = {
  display: "flex",
  flexWrap: "wrap",
  gap: 8,
  padding: "9px 10px",
  borderRadius: 12,
  border: "1px solid var(--border-strong)",
  background: "var(--surface-1)",
  minHeight: 52,
};

const chipStyle = {
  display: "inline-flex",
  alignItems: "center",
  gap: 8,
  padding: "6px 10px",
  borderRadius: 999,
  background: "var(--bg-accent)",
  color: "var(--text-accent)",
  border: "1px solid var(--border-accent)",
  fontSize: 13,
};

const chipRemoveButton = {
  border: "none",
  background: "transparent",
  color: "var(--text-accent)",
  cursor: "pointer",
  fontSize: 16,
  lineHeight: 1,
  padding: 0,
};

const chipInput = {
  flex: 1,
  minWidth: 160,
  border: "none",
  outline: "none",
  background: "transparent",
  color: "var(--text-primary)",
  fontSize: 13,
};

const commentBox = {
  width: "100%",
  minHeight: 110,
  padding: "10px 12px",
  borderRadius: 12,
  border: "1px solid var(--border-strong)",
  background: "var(--surface-1)",
  color: "var(--text-primary)",
  fontSize: 13,
  lineHeight: 1.6,
  resize: "vertical",
  boxSizing: "border-box",
};

const selectStyle = {
  width: "100%",
  padding: "9px 11px",
  borderRadius: 10,
  border: "1px solid var(--border-strong)",
  background: "var(--surface-0)",
  color: "var(--text-primary)",
  fontSize: 13,
  boxSizing: "border-box",
};

const smallButton = {
  padding: "5px 12px",
  borderRadius: "var(--radius)",
  border: "1px solid var(--border-strong)",
  background: "transparent",
  color: "var(--text-secondary)",
  cursor: "pointer",
  fontSize: 13,
};

const emptyStateCard = {
  padding: "30px 24px",
  borderRadius: 14,
  border: "1px dashed var(--border-strong)",
  background: "var(--surface-1)",
  color: "var(--text-muted)",
  textAlign: "center",
};
