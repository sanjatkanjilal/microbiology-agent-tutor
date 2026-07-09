import { useEffect, useMemo, useState } from "react";

const TABS = [
  { id: "users", label: "User management" },
  { id: "usage", label: "Usage" },
  { id: "tasks", label: "Tasks" },
];

export default function AdminPage({ authToken, onBack }) {
  const [tab, setTab] = useState("users");
  const [users, setUsers] = useState([]);
  const [usageSummary, setUsageSummary] = useState(null);
  const [usageEvents, setUsageEvents] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [taskForm, setTaskForm] = useState({
    assignee_user_id: "",
    task_type: "tag_review",
    title: "",
    description: "",
    case_id: "",
    scheduled_for: "",
    due_at: "",
  });

  const eligibleAssignees = useMemo(
    () => users.filter((user) => user.active),
    [users],
  );

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: {
        Authorization: `Bearer ${authToken}`,
        ...(options.headers || {}),
      },
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data?.detail || "Request failed");
    return data;
  }

  async function loadAll() {
    setLoading(true);
    setError("");
    try {
      const [usersData, summaryData, eventsData, tasksData] = await Promise.all([
        fetchJson("/api/v1/admin/users"),
        fetchJson("/api/v1/admin/usage/summary"),
        fetchJson("/api/v1/admin/usage/events"),
        fetchJson("/api/v1/admin/tasks"),
      ]);
      setUsers(usersData.users || []);
      setUsageSummary(summaryData.summary || null);
      setUsageEvents(eventsData.events || []);
      setTasks(tasksData.tasks || []);
      if (!taskForm.assignee_user_id && usersData.users?.length) {
        setTaskForm((current) => ({
          ...current,
          assignee_user_id: usersData.users[0].user_id,
        }));
      }
    } catch (err) {
      setError(err.message || "Unable to load admin data");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
  }, [authToken]);

  async function patchUser(userId, patch) {
    try {
      await fetchJson(`/api/v1/admin/users/${userId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      await loadAll();
    } catch (err) {
      setError(err.message || "Unable to update user");
    }
  }

  async function createTask(event) {
    event.preventDefault();
    try {
      await fetchJson("/api/v1/admin/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...taskForm,
          case_id: taskForm.case_id || null,
          scheduled_for: taskForm.scheduled_for || null,
          due_at: taskForm.due_at || null,
        }),
      });
      setTaskForm((current) => ({
        ...current,
        title: "",
        description: "",
        case_id: "",
        scheduled_for: "",
        due_at: "",
      }));
      await loadAll();
    } catch (err) {
      setError(err.message || "Unable to create task");
    }
  }

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "24px 24px 60px", fontFamily: "var(--font-sans)" }}>
      <div style={{ maxWidth: 1280, margin: "0 auto", display: "grid", gap: 16 }}>
        <button onClick={onBack} style={backButton}>← Back</button>
        <div>
          <h1 style={{ fontSize: 30, margin: 0, color: "var(--text-primary)", letterSpacing: "-0.03em" }}>Admin</h1>
          <p style={{ fontSize: 14, color: "var(--text-secondary)", lineHeight: 1.6, margin: "8px 0 0" }}>
            Manage authorized users, study tasks, and usage analytics. Passwords remain hashed in the backend store and are never exposed in this UI.
          </p>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setTab(item.id)}
              style={{
                padding: "8px 12px",
                borderRadius: 999,
                border: "1px solid var(--border-strong)",
                background: tab === item.id ? "var(--bg-accent)" : "var(--surface-1)",
                color: tab === item.id ? "var(--text-accent)" : "var(--text-secondary)",
                cursor: "pointer",
                fontSize: 13,
                fontWeight: 600,
              }}
            >
              {item.label}
            </button>
          ))}
        </div>

        {error ? <div style={errorBox}>{error}</div> : null}
        {loading ? (
          <div style={mutedBox}>Loading admin data…</div>
        ) : (
          <>
            {tab === "users" && (
              <div style={sectionCard}>
                <div style={sectionTitle}>Authorized users</div>
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                    <thead>
                      <tr style={{ textAlign: "left", color: "var(--text-muted)" }}>
                        {["Name", "Username", "Anonymous ID", "Role", "Training", "Year", "Degrees", "Created", "Last login", "Active"].map((header) => (
                          <th key={header} style={tableHeaderCell}>{header}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {users.map((user) => (
                        <tr key={user.user_id}>
                          <td style={tableBodyCell}>{user.display_name}</td>
                          <td style={tableBodyCell}>{user.username}</td>
                          <td style={tableBodyCell}><code>{user.anonymous_user_id}</code></td>
                          <td style={tableBodyCell}>
                            <select
                              value={user.role}
                              onChange={(event) => patchUser(user.user_id, { role: event.target.value })}
                              style={smallSelect}
                            >
                              <option value="student">student</option>
                              <option value="reviewer">reviewer</option>
                              <option value="admin">admin</option>
                            </select>
                          </td>
                          <td style={tableBodyCell}>{user.training_level || "—"}</td>
                          <td style={tableBodyCell}>{user.year_in_program || "—"}</td>
                          <td style={tableBodyCell}>{(user.degrees || []).join(", ") || "—"}</td>
                          <td style={tableBodyCell}>{formatDate(user.created_at)}</td>
                          <td style={tableBodyCell}>{formatDate(user.last_login_at)}</td>
                          <td style={tableBodyCell}>
                            <label style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                              <input
                                type="checkbox"
                                checked={user.active}
                                onChange={(event) => patchUser(user.user_id, { active: event.target.checked })}
                              />
                              {user.active ? "Yes" : "No"}
                            </label>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {tab === "usage" && (
              <div style={{ display: "grid", gap: 16 }}>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
                  <UsageCard label="Active users" value={usageSummary?.total_users ?? 0} />
                  <UsageCard label="Logged events" value={usageSummary?.total_events ?? 0} />
                  <UsageCard label="Submitted reviews" value={usageSummary?.total_reviews ?? 0} />
                  <UsageCard label="Autosaved drafts" value={usageSummary?.total_drafts ?? 0} />
                </div>
                <div style={sectionCard}>
                  <div style={sectionTitle}>Aggregate event counts</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    {(usageSummary?.events_by_type || []).map((item) => (
                      <span key={item.event_type} style={chip}>{item.event_type}: {item.count}</span>
                    ))}
                  </div>
                </div>
                <div style={sectionCard}>
                  <div style={sectionTitle}>Recent activity</div>
                  <div style={{ display: "grid", gap: 10 }}>
                    {usageEvents.slice(0, 40).map((event) => (
                      <div key={event.event_id} style={eventRow}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>{event.event_type}</div>
                        <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                          {event.username || "anonymous"} · {event.screen || "no screen"} · {formatDate(event.created_at)}
                        </div>
                        {event.case_id ? <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Case: {event.case_id}</div> : null}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {tab === "tasks" && (
              <div style={{ display: "grid", gap: 16 }}>
                <form onSubmit={createTask} style={sectionCard}>
                  <div style={sectionTitle}>Assign task</div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
                    <LabeledField label="Assignee">
                      <select
                        value={taskForm.assignee_user_id}
                        onChange={(event) => setTaskForm((current) => ({ ...current, assignee_user_id: event.target.value }))}
                        style={inputStyle}
                      >
                        {eligibleAssignees.map((user) => (
                          <option key={user.user_id} value={user.user_id}>
                            {user.display_name} ({user.role})
                          </option>
                        ))}
                      </select>
                    </LabeledField>
                    <LabeledField label="Task type">
                      <select
                        value={taskForm.task_type}
                        onChange={(event) => setTaskForm((current) => ({ ...current, task_type: event.target.value }))}
                        style={inputStyle}
                      >
                        <option value="tag_review">tag_review</option>
                        <option value="case_assignment">case_assignment</option>
                      </select>
                    </LabeledField>
                    <LabeledField label="Case ID">
                      <input
                        value={taskForm.case_id}
                        onChange={(event) => setTaskForm((current) => ({ ...current, case_id: event.target.value }))}
                        style={inputStyle}
                        placeholder="Case_01001"
                      />
                    </LabeledField>
                    <LabeledField label="Scheduled for">
                      <input
                        value={taskForm.scheduled_for}
                        onChange={(event) => setTaskForm((current) => ({ ...current, scheduled_for: event.target.value }))}
                        style={inputStyle}
                        placeholder="2026-07-15"
                      />
                    </LabeledField>
                    <LabeledField label="Due at">
                      <input
                        value={taskForm.due_at}
                        onChange={(event) => setTaskForm((current) => ({ ...current, due_at: event.target.value }))}
                        style={inputStyle}
                        placeholder="2026-07-18"
                      />
                    </LabeledField>
                    <LabeledField label="Title">
                      <input
                        value={taskForm.title}
                        onChange={(event) => setTaskForm((current) => ({ ...current, title: event.target.value }))}
                        style={inputStyle}
                        placeholder="Review assigned TB cases"
                      />
                    </LabeledField>
                  </div>
                  <LabeledField label="Description">
                    <textarea
                      value={taskForm.description}
                      onChange={(event) => setTaskForm((current) => ({ ...current, description: event.target.value }))}
                      style={{ ...inputStyle, minHeight: 90, resize: "vertical" }}
                    />
                  </LabeledField>
                  <button type="submit" style={primaryButton}>Create task</button>
                </form>

                <div style={sectionCard}>
                  <div style={sectionTitle}>Assigned tasks</div>
                  <div style={{ display: "grid", gap: 12 }}>
                    {tasks.map((task) => (
                      <div key={task.task_id} style={eventRow}>
                        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                          <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)" }}>{task.title}</div>
                          <span style={chip}>{task.status}</span>
                        </div>
                        <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                          {task.assignee_name} · {task.task_type} {task.case_id ? `· ${task.case_id}` : ""}
                        </div>
                        {task.description ? <div style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 6 }}>{task.description}</div> : null}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function UsageCard({ label, value }) {
  return (
    <div style={sectionCard}>
      <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, color: "var(--text-primary)" }}>{value}</div>
    </div>
  );
}

function LabeledField({ label, children }) {
  return (
    <label style={{ display: "grid", gap: 6 }}>
      <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{label}</span>
      {children}
    </label>
  );
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

const sectionCard = {
  padding: "16px 18px",
  borderRadius: 14,
  border: "1px solid var(--border)",
  background: "var(--surface-1)",
};

const sectionTitle = {
  fontSize: 16,
  fontWeight: 700,
  color: "var(--text-primary)",
  marginBottom: 12,
};

const backButton = {
  padding: "5px 12px",
  borderRadius: "var(--radius)",
  border: "1px solid var(--border-strong)",
  background: "transparent",
  color: "var(--text-secondary)",
  cursor: "pointer",
  fontSize: 13,
  justifySelf: "start",
};

const errorBox = {
  ...sectionCard,
  color: "var(--text-danger)",
  background: "var(--bg-danger)",
  border: "1px solid var(--border-danger)",
};

const mutedBox = {
  ...sectionCard,
  color: "var(--text-muted)",
  textAlign: "center",
};

const chip = {
  display: "inline-flex",
  alignItems: "center",
  padding: "5px 9px",
  borderRadius: 999,
  border: "1px solid var(--border-strong)",
  background: "var(--surface-0)",
  color: "var(--text-secondary)",
  fontSize: 12,
};

const eventRow = {
  padding: "12px 14px",
  borderRadius: 12,
  border: "1px solid var(--border)",
  background: "var(--surface-0)",
};

const inputStyle = {
  width: "100%",
  padding: "9px 11px",
  borderRadius: 10,
  border: "1px solid var(--border-strong)",
  background: "var(--surface-0)",
  color: "var(--text-primary)",
  fontSize: 13,
  boxSizing: "border-box",
};

const smallSelect = {
  ...inputStyle,
  padding: "7px 9px",
  fontSize: 12,
};

const primaryButton = {
  marginTop: 14,
  padding: "10px 14px",
  borderRadius: 10,
  border: "1px solid var(--border-accent)",
  background: "var(--fill-accent)",
  color: "var(--on-accent)",
  cursor: "pointer",
  fontSize: 14,
  fontWeight: 600,
};

const tableHeaderCell = {
  padding: "10px 8px",
  borderBottom: "1px solid var(--border)",
  fontSize: 12,
  textTransform: "uppercase",
  letterSpacing: "0.05em",
};

const tableBodyCell = {
  padding: "10px 8px",
  borderBottom: "1px solid var(--border)",
  color: "var(--text-primary)",
  verticalAlign: "top",
};
