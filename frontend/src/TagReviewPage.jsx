import { useEffect, useState } from "react";

const API_BASE = "/api/v1";
const REVIEWER_STORAGE_KEY = "docent_id_tag_reviewer";

const FILTERS = [
  { id: "needs_review", label: "Needs review" },
  { id: "all", label: "All cases" },
  { id: "reviewed", label: "Reviewed" },
  { id: "no_organism", label: "No organism tag" },
  { id: "no_syndrome", label: "No syndrome tag" },
  { id: "no_host", label: "No host tag" },
];

const CASE_SECTIONS = [
  { key: "history", label: "History" },
  { key: "exam_studies", label: "Exam / Studies" },
  { key: "diagnosis", label: "Diagnosis" },
  { key: "more_info", label: "More info" },
];

function loadStoredReviewer() {
  try {
    return window.localStorage.getItem(REVIEWER_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

function splitTagText(text) {
  const seen = new Set();
  return text
    .split(/\n|,/)
    .map((value) => value.trim())
    .filter(Boolean)
    .filter((value) => {
      const key = value.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function formatTagText(values) {
  return (values || []).join("\n");
}

function formatDateTime(value) {
  if (!value) return "Not yet reviewed";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function getDraftKey(caseId, reviewerName) {
  return `${caseId || ""}::${reviewerName.trim().toLowerCase() || "__anon__"}`;
}

function buildInitialDraft(detail, reviewerName) {
  const reviewerKey = reviewerName.trim().toLowerCase();
  const existingReview = reviewerKey
    ? (detail.reviews || []).find(
        (review) => review.reviewer_name.trim().toLowerCase() === reviewerKey,
      )
    : null;

  const source = existingReview || detail.machine_answers;

  return {
    organismsText: formatTagText(source.organisms || []),
    syndromesText: formatTagText(source.syndromes || []),
    hostsText: formatTagText(source.hosts || []),
    notes: existingReview?.notes || "",
  };
}

function matchesFilter(item, filterId) {
  if (filterId === "all") return true;
  if (filterId === "needs_review") return item.needs_review;
  if (filterId === "reviewed") return !item.needs_review;
  if (filterId === "no_organism") return item.machine_answer_counts.organisms === 0;
  if (filterId === "no_syndrome") return item.machine_answer_counts.syndromes === 0;
  if (filterId === "no_host") return item.machine_answer_counts.hosts === 0;
  return true;
}

function TagPill({ children, tone = "default" }) {
  const tones = {
    default: {
      background: "var(--surface-0)",
      border: "1px solid var(--border)",
      color: "var(--text-secondary)",
    },
    accent: {
      background: "var(--bg-accent)",
      border: "1px solid var(--border-accent)",
      color: "var(--text-accent)",
    },
    success: {
      background: "var(--bg-success)",
      border: "1px solid var(--border-success)",
      color: "var(--text-success)",
    },
  };

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "4px 8px",
        borderRadius: 999,
        fontSize: 12,
        lineHeight: 1.2,
        whiteSpace: "nowrap",
        ...tones[tone],
      }}
    >
      {children}
    </span>
  );
}

function TagGroup({ label, values, emptyLabel = "None suggested" }) {
  return (
    <div
      style={{
        padding: "14px 16px",
        border: "1px solid var(--border)",
        borderRadius: 10,
        background: "var(--surface-1)",
      }}
    >
      <div
        style={{
          fontSize: 11,
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          fontWeight: 700,
          color: "var(--text-muted)",
          marginBottom: 10,
        }}
      >
        {label}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {values.length > 0 ? (
          values.map((value) => <TagPill key={value}>{value}</TagPill>)
        ) : (
          <span style={{ color: "var(--text-muted)", fontSize: 13 }}>{emptyLabel}</span>
        )}
      </div>
    </div>
  );
}

function SummaryCard({ label, value, hint }) {
  return (
    <div
      style={{
        padding: "16px 18px",
        border: "1px solid var(--border)",
        borderRadius: 12,
        background: "var(--surface-1)",
        minWidth: 0,
      }}
    >
      <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.03em" }}>{value}</div>
      <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 4 }}>{hint}</div>
    </div>
  );
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
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 5 }}>
        <span style={{ fontFamily: "monospace", fontSize: 11, color: "var(--text-accent)", fontWeight: 700 }}>{item.id}</span>
        <TagPill tone={item.needs_review ? "accent" : "success"}>
          {item.reviewer_count} reviewer{item.reviewer_count === 1 ? "" : "s"}
        </TagPill>
      </div>
      <div style={{ fontSize: 13, lineHeight: 1.45, color: "var(--text-primary)", marginBottom: 8 }}>{item.title}</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        <TagPill>Org {item.machine_answer_counts.organisms}</TagPill>
        <TagPill>Syn {item.machine_answer_counts.syndromes}</TagPill>
        <TagPill>Host {item.machine_answer_counts.hosts}</TagPill>
      </div>
    </button>
  );
}

function TextSection({ label, text }) {
  return (
    <section
      style={{
        padding: "18px 20px",
        border: "1px solid var(--border)",
        borderRadius: 12,
        background: "var(--surface-1)",
      }}
    >
      <div
        style={{
          fontSize: 11,
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          fontWeight: 700,
          color: "var(--text-muted)",
          marginBottom: 10,
        }}
      >
        {label}
      </div>
      <div style={{ whiteSpace: "pre-wrap", fontSize: 14, lineHeight: 1.7, color: "var(--text-primary)" }}>
        {text || "No text available."}
      </div>
    </section>
  );
}

function ReviewCard({ review }) {
  return (
    <div
      style={{
        padding: "14px 16px",
        border: "1px solid var(--border)",
        borderRadius: 10,
        background: "var(--surface-1)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 8, flexWrap: "wrap" }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>{review.reviewer_name}</div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <TagPill tone={review.decision === "accepted" ? "success" : "accent"}>
            {review.decision === "accepted" ? "Accepted suggestions" : "Modified suggestions"}
          </TagPill>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{formatDateTime(review.submitted_at)}</span>
        </div>
      </div>
      <div style={{ display: "grid", gap: 10 }}>
        <TagGroup label="Organisms" values={review.organisms || []} emptyLabel="No organism tags" />
        <TagGroup label="Syndromes" values={review.syndromes || []} emptyLabel="No syndrome tags" />
        <TagGroup label="Host characteristics" values={review.hosts || []} emptyLabel="No host tags" />
      </div>
      {review.notes ? (
        <div style={{ marginTop: 12, fontSize: 13, lineHeight: 1.6, color: "var(--text-secondary)", whiteSpace: "pre-wrap" }}>
          {review.notes}
        </div>
      ) : null}
    </div>
  );
}

export default function TagReviewPage({ onBack }) {
  const [reviewerName, setReviewerName] = useState(loadStoredReviewer);
  const [queue, setQueue] = useState([]);
  const [summary, setSummary] = useState(null);
  const [queueLoading, setQueueLoading] = useState(true);
  const [queueError, setQueueError] = useState("");
  const [selectedCaseId, setSelectedCaseId] = useState(null);
  const [detailsById, setDetailsById] = useState({});
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("needs_review");
  const [drafts, setDrafts] = useState({});
  const [saveState, setSaveState] = useState({ tone: "", message: "" });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    try {
      window.localStorage.setItem(REVIEWER_STORAGE_KEY, reviewerName);
    } catch {
      // Ignore storage failures in private browsing or locked-down environments.
    }
  }, [reviewerName]);

  async function loadQueue() {
    setQueueLoading(true);
    setQueueError("");
    try {
      const response = await fetch(`${API_BASE}/tag-review/cases`);
      if (!response.ok) throw new Error("Unable to load review queue");
      const data = await response.json();
      setQueue(data.cases || []);
      setSummary(data.summary || null);
    } catch (error) {
      setQueueError(error.message || "Unable to load review queue");
    } finally {
      setQueueLoading(false);
    }
  }

  async function loadDetail(caseId, force = false) {
    if (!caseId) return null;
    if (!force && detailsById[caseId]) return detailsById[caseId];

    setDetailLoading(true);
    setDetailError("");
    try {
      const response = await fetch(`${API_BASE}/tag-review/cases/${caseId}`);
      if (!response.ok) throw new Error("Unable to load case detail");
      const data = await response.json();
      setDetailsById((current) => ({ ...current, [caseId]: data }));
      return data;
    } catch (error) {
      setDetailError(error.message || "Unable to load case detail");
      return null;
    } finally {
      setDetailLoading(false);
    }
  }

  useEffect(() => {
    loadQueue();
  }, []);

  const filteredQueue = [...queue]
    .filter((item) => matchesFilter(item, filter))
    .filter((item) => {
      const query = search.trim().toLowerCase();
      if (!query) return true;
      const machineText = [
        ...(item.machine_answers?.organisms || []),
        ...(item.machine_answers?.syndromes || []),
        ...(item.machine_answers?.hosts || []),
      ]
        .join(" ")
        .toLowerCase();
      return (
        item.id.toLowerCase().includes(query)
        || item.title.toLowerCase().includes(query)
        || machineText.includes(query)
      );
    })
    .sort((a, b) => {
      if (a.needs_review !== b.needs_review) return a.needs_review ? -1 : 1;
      if (a.reviewer_count !== b.reviewer_count) return a.reviewer_count - b.reviewer_count;
      return a.id.localeCompare(b.id);
    });

  useEffect(() => {
    if (filteredQueue.length === 0) {
      setSelectedCaseId(null);
      return;
    }
    if (!selectedCaseId || !filteredQueue.some((item) => item.id === selectedCaseId)) {
      setSelectedCaseId(filteredQueue[0].id);
    }
  }, [filteredQueue, selectedCaseId]);

  useEffect(() => {
    if (!selectedCaseId) return;
    loadDetail(selectedCaseId);
  }, [selectedCaseId]);

  const selectedDetail = selectedCaseId ? detailsById[selectedCaseId] : null;
  const draftKey = getDraftKey(selectedCaseId, reviewerName);

  useEffect(() => {
    if (!selectedDetail || !selectedCaseId) return;
    setDrafts((current) => {
      if (current[draftKey]) return current;
      return {
        ...current,
        [draftKey]: buildInitialDraft(selectedDetail, reviewerName),
      };
    });
  }, [draftKey, reviewerName, selectedCaseId, selectedDetail]);

  const currentDraft = drafts[draftKey] || {
    organismsText: "",
    syndromesText: "",
    hostsText: "",
    notes: "",
  };

  function updateDraft(patch) {
    setDrafts((current) => ({
      ...current,
      [draftKey]: {
        ...(current[draftKey] || currentDraft),
        ...patch,
      },
    }));
  }

  function resetToMachineSuggestions() {
    if (!selectedDetail) return;
    updateDraft({
      organismsText: formatTagText(selectedDetail.machine_answers.organisms),
      syndromesText: formatTagText(selectedDetail.machine_answers.syndromes),
      hostsText: formatTagText(selectedDetail.machine_answers.hosts),
    });
  }

  async function handleSave() {
    if (!selectedCaseId || !selectedDetail) return;
    const trimmedReviewer = reviewerName.trim();
    if (!trimmedReviewer) {
      setSaveState({ tone: "error", message: "Enter your name so reviews can be counted correctly." });
      return;
    }

    const payload = {
      reviewer_name: trimmedReviewer,
      organisms: splitTagText(currentDraft.organismsText),
      syndromes: splitTagText(currentDraft.syndromesText),
      hosts: splitTagText(currentDraft.hostsText),
      notes: currentDraft.notes.trim(),
    };

    setSaving(true);
    setSaveState({ tone: "", message: "" });

    try {
      const response = await fetch(`${API_BASE}/tag-review/cases/${selectedCaseId}/reviews`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.detail || data?.error || "Unable to save review");
      }

      await Promise.all([loadQueue(), loadDetail(selectedCaseId, true)]);
      setDrafts((current) => ({
        ...current,
        [draftKey]: {
          organismsText: formatTagText(payload.organisms),
          syndromesText: formatTagText(payload.syndromes),
          hostsText: formatTagText(payload.hosts),
          notes: payload.notes,
        },
      }));
      setSaveState({ tone: "success", message: "Review saved to the shared queue." });
    } catch (error) {
      setSaveState({ tone: "error", message: error.message || "Unable to save review." });
    } finally {
      setSaving(false);
    }
  }

  const saveToneStyle = saveState.tone === "success"
    ? { color: "var(--text-success)" }
    : saveState.tone === "error"
      ? { color: "var(--text-danger)" }
      : { color: "var(--text-muted)" };

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", background: "var(--surface-0)", fontFamily: "var(--font-sans)" }}>
      <div style={{ padding: "22px 24px 18px", borderBottom: "1px solid var(--border)", background: "var(--surface-0)" }}>
        <div style={{ maxWidth: 1440, margin: "0 auto" }}>
          <button
            type="button"
            onClick={onBack}
            style={{
              padding: "5px 12px",
              borderRadius: "var(--radius)",
              border: "1px solid var(--border-strong)",
              background: "transparent",
              color: "var(--text-secondary)",
              cursor: "pointer",
              fontSize: 13,
              marginBottom: 16,
            }}
          >
            ← Back
          </button>

          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 18, flexWrap: "wrap", marginBottom: 18 }}>
            <div style={{ minWidth: 280 }}>
              <h1 style={{ fontSize: 28, lineHeight: 1.1, margin: 0, color: "var(--text-primary)", letterSpacing: "-0.03em" }}>Tag review queue</h1>
              <p style={{ fontSize: 14, color: "var(--text-secondary)", lineHeight: 1.6, margin: "10px 0 0" }}>
                Review organism, syndrome, and host tags against the full case text. The current suggestions are seeded from the repo&apos;s existing auto-parsed case tags.
              </p>
            </div>

            <div style={{ width: "min(420px, 100%)" }}>
              <label style={{ display: "block", fontSize: 12, color: "var(--text-muted)", marginBottom: 6 }}>Reviewer name</label>
              <input
                type="text"
                value={reviewerName}
                onChange={(event) => setReviewerName(event.target.value)}
                placeholder="Enter your name"
                style={{
                  width: "100%",
                  padding: "10px 12px",
                  borderRadius: 10,
                  border: "1px solid var(--border-strong)",
                  background: "var(--surface-1)",
                  color: "var(--text-primary)",
                  fontSize: 14,
                  boxSizing: "border-box",
                }}
              />
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 6 }}>
                Re-using the same name updates your prior review instead of creating a duplicate count.
              </div>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
            <SummaryCard
              label="Cases still requiring review"
              value={summary?.pending_cases ?? "—"}
              hint={`Threshold: ${summary?.required_reviews_per_case ?? 1} reviewer${summary?.required_reviews_per_case === 1 ? "" : "s"} per case`}
            />
            <SummaryCard
              label="Reviewed cases"
              value={summary?.reviewed_cases ?? "—"}
              hint="Cases that already cleared the review threshold"
            />
            <SummaryCard
              label="Total cases"
              value={summary?.total_cases ?? "—"}
              hint="Full MGH case corpus loaded into the queue"
            />
            <SummaryCard
              label="Submitted reviews"
              value={summary?.total_reviews ?? "—"}
              hint="Unique reviewer submissions saved so far"
            />
          </div>
        </div>
      </div>

      <div style={{ flex: 1, minHeight: 0, display: "grid", gridTemplateColumns: "360px minmax(0, 1fr)", overflow: "hidden" }}>
        <aside style={{ borderRight: "1px solid var(--border)", background: "var(--surface-1)", display: "flex", flexDirection: "column", minHeight: 0 }}>
          <div style={{ padding: "14px 14px 12px", borderBottom: "1px solid var(--border)" }}>
            <input
              type="text"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search title, case ID, or suggested tags…"
              style={{
                width: "100%",
                padding: "9px 11px",
                borderRadius: 10,
                border: "1px solid var(--border-strong)",
                background: "var(--surface-0)",
                color: "var(--text-primary)",
                fontSize: 13,
                boxSizing: "border-box",
                marginBottom: 10,
              }}
            />
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
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
              {queueLoading ? "Loading queue…" : `${filteredQueue.length} visible of ${queue.length} total cases`}
            </div>
          </div>

          <div style={{ flex: 1, overflowY: "auto" }}>
            {queueError ? (
              <div style={{ padding: 16, color: "var(--text-danger)", fontSize: 13 }}>{queueError}</div>
            ) : queueLoading ? (
              <div style={{ padding: 16, color: "var(--text-muted)", fontSize: 13 }}>Loading cases…</div>
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

        <main style={{ minWidth: 0, overflowY: "auto", padding: "20px 24px 56px" }}>
          <div style={{ maxWidth: 980, margin: "0 auto", display: "grid", gap: 18 }}>
            {!selectedCaseId ? (
              <div
                style={{
                  padding: "44px 24px",
                  border: "1px dashed var(--border-strong)",
                  borderRadius: 16,
                  background: "var(--surface-1)",
                  color: "var(--text-muted)",
                  textAlign: "center",
                }}
              >
                Choose a case from the queue to start reviewing.
              </div>
            ) : detailError ? (
              <div style={{ color: "var(--text-danger)", fontSize: 14 }}>{detailError}</div>
            ) : detailLoading && !selectedDetail ? (
              <div style={{ color: "var(--text-muted)", fontSize: 14 }}>Loading case detail…</div>
            ) : selectedDetail ? (
              <>
                <section
                  style={{
                    padding: "18px 20px",
                    border: "1px solid var(--border)",
                    borderRadius: 14,
                    background: "var(--surface-1)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontFamily: "monospace", fontSize: 12, color: "var(--text-accent)", fontWeight: 700, marginBottom: 8 }}>
                        {selectedDetail.case.id}
                      </div>
                      <h2 style={{ fontSize: 24, lineHeight: 1.2, margin: 0, color: "var(--text-primary)", letterSpacing: "-0.03em" }}>
                        {selectedDetail.case.title}
                      </h2>
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                      <TagPill tone={selectedDetail.review_summary.needs_review ? "accent" : "success"}>
                        {selectedDetail.review_summary.needs_review ? "Needs review" : "Reviewed"}
                      </TagPill>
                      <TagPill>{selectedDetail.case.figures?.length || 0} figures</TagPill>
                      <TagPill>
                        {selectedDetail.review_summary.reviewer_count} reviewer{selectedDetail.review_summary.reviewer_count === 1 ? "" : "s"}
                      </TagPill>
                    </div>
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginTop: 12, fontSize: 13, color: "var(--text-secondary)" }}>
                    <span>Last reviewed: {formatDateTime(selectedDetail.review_summary.last_reviewed_at)}</span>
                    <span>
                      Reviewers: {selectedDetail.review_summary.reviewers.length > 0 ? selectedDetail.review_summary.reviewers.join(", ") : "None yet"}
                    </span>
                  </div>
                </section>

                <section
                  style={{
                    padding: "18px 20px",
                    border: "1px solid var(--border)",
                    borderRadius: 14,
                    background: "var(--surface-1)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap", marginBottom: 14 }}>
                    <div>
                      <div style={{ fontSize: 18, fontWeight: 700, color: "var(--text-primary)" }}>Machine / LLM starting point</div>
                      <div style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 4 }}>
                        These values are pulled from the current auto-parsed tags in <code>case_library.json</code>.
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={resetToMachineSuggestions}
                      style={{
                        padding: "7px 12px",
                        borderRadius: 10,
                        border: "1px solid var(--border-strong)",
                        background: "transparent",
                        color: "var(--text-secondary)",
                        cursor: "pointer",
                        fontSize: 13,
                      }}
                    >
                      Reset form to machine suggestions
                    </button>
                  </div>
                  <div style={{ display: "grid", gap: 12 }}>
                    <TagGroup label="Organisms" values={selectedDetail.machine_answers.organisms || []} />
                    <TagGroup label="Syndromes" values={selectedDetail.machine_answers.syndromes || []} />
                    <TagGroup label="Host characteristics" values={selectedDetail.machine_answers.hosts || []} />
                  </div>
                </section>

                <section
                  style={{
                    padding: "18px 20px",
                    border: "1px solid var(--border)",
                    borderRadius: 14,
                    background: "var(--surface-1)",
                  }}
                >
                  <div style={{ fontSize: 18, fontWeight: 700, color: "var(--text-primary)", marginBottom: 12 }}>Full case text</div>
                  <div style={{ display: "grid", gap: 12 }}>
                    {CASE_SECTIONS.map((section) => (
                      <TextSection
                        key={section.key}
                        label={section.label}
                        text={selectedDetail.case[section.key]}
                      />
                    ))}
                  </div>
                </section>

                <section
                  style={{
                    padding: "18px 20px",
                    border: "1px solid var(--border)",
                    borderRadius: 14,
                    background: "var(--surface-1)",
                  }}
                >
                  <div style={{ fontSize: 18, fontWeight: 700, color: "var(--text-primary)", marginBottom: 12 }}>Expert review</div>
                  <div style={{ display: "grid", gap: 14 }}>
                    <div>
                      <label style={{ display: "block", fontSize: 12, color: "var(--text-muted)", marginBottom: 6 }}>Organisms</label>
                      <textarea
                        value={currentDraft.organismsText}
                        onChange={(event) => updateDraft({ organismsText: event.target.value })}
                        placeholder="One organism per line"
                        style={textareaStyle}
                      />
                    </div>
                    <div>
                      <label style={{ display: "block", fontSize: 12, color: "var(--text-muted)", marginBottom: 6 }}>Syndromes</label>
                      <textarea
                        value={currentDraft.syndromesText}
                        onChange={(event) => updateDraft({ syndromesText: event.target.value })}
                        placeholder="One syndrome per line"
                        style={textareaStyle}
                      />
                    </div>
                    <div>
                      <label style={{ display: "block", fontSize: 12, color: "var(--text-muted)", marginBottom: 6 }}>Host characteristics</label>
                      <textarea
                        value={currentDraft.hostsText}
                        onChange={(event) => updateDraft({ hostsText: event.target.value })}
                        placeholder="One host characteristic per line"
                        style={textareaStyle}
                      />
                    </div>
                    <div>
                      <label style={{ display: "block", fontSize: 12, color: "var(--text-muted)", marginBottom: 6 }}>Notes for the team</label>
                      <textarea
                        value={currentDraft.notes}
                        onChange={(event) => updateDraft({ notes: event.target.value })}
                        placeholder="Optional context, uncertainty, or rationale"
                        style={{ ...textareaStyle, minHeight: 96 }}
                      />
                    </div>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 14, flexWrap: "wrap" }}>
                      <div style={{ fontSize: 12, ...saveToneStyle }}>{saveState.message || "One tag per line. Commas also work if you paste a list."}</div>
                      <button
                        type="button"
                        disabled={saving}
                        onClick={handleSave}
                        style={{
                          padding: "10px 16px",
                          borderRadius: 10,
                          border: "1px solid var(--border-accent)",
                          background: saving ? "var(--fill-disabled)" : "var(--fill-accent)",
                          color: "var(--on-accent)",
                          cursor: saving ? "not-allowed" : "pointer",
                          fontSize: 14,
                          fontWeight: 600,
                        }}
                      >
                        {saving ? "Saving…" : "Save review"}
                      </button>
                    </div>
                  </div>
                </section>

                <section
                  style={{
                    padding: "18px 20px",
                    border: "1px solid var(--border)",
                    borderRadius: 14,
                    background: "var(--surface-1)",
                  }}
                >
                  <div style={{ fontSize: 18, fontWeight: 700, color: "var(--text-primary)", marginBottom: 12 }}>Prior reviews</div>
                  {selectedDetail.reviews.length === 0 ? (
                    <div style={{ fontSize: 14, color: "var(--text-muted)" }}>No one has reviewed this case yet.</div>
                  ) : (
                    <div style={{ display: "grid", gap: 12 }}>
                      {selectedDetail.reviews.map((review) => (
                        <ReviewCard key={`${review.reviewer_name}-${review.submitted_at}`} review={review} />
                      ))}
                    </div>
                  )}
                </section>
              </>
            ) : null}
          </div>
        </main>
      </div>
    </div>
  );
}

const textareaStyle = {
  width: "100%",
  minHeight: 84,
  padding: "10px 12px",
  borderRadius: 10,
  border: "1px solid var(--border-strong)",
  background: "var(--surface-0)",
  color: "var(--text-primary)",
  fontSize: 14,
  lineHeight: 1.55,
  resize: "vertical",
  boxSizing: "border-box",
  fontFamily: "var(--font-sans)",
};
