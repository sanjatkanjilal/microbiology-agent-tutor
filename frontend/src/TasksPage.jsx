import { useEffect, useState } from "react";

export default function TasksPage({ authToken, onBack }) {
  const [tasks, setTasks] = useState([]);
  const [summary, setSummary] = useState({ pending_count: 0, completed_count: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadTasks() {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/v1/me/tasks", {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail || "Unable to load tasks");
      setTasks(data.tasks || []);
      setSummary(data.summary || { pending_count: 0, completed_count: 0 });
    } catch (err) {
      setError(err.message || "Unable to load tasks");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadTasks();
  }, [authToken]);

  async function updateStatus(taskId, status) {
    try {
      const response = await fetch(`/api/v1/tasks/${taskId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({ status }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail || "Unable to update task");
      await loadTasks();
    } catch (err) {
      setError(err.message || "Unable to update task");
    }
  }

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "24px 24px 60px", fontFamily: "var(--font-sans)" }}>
      <div style={{ maxWidth: 980, margin: "0 auto", display: "grid", gap: 16 }}>
        <button onClick={onBack} style={backButton}>← Back</button>
        <h1 style={{ fontSize: 28, margin: 0, color: "var(--text-primary)", letterSpacing: "-0.03em" }}>Tasks</h1>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
          <SummaryCard label="Pending" value={summary.pending_count} />
          <SummaryCard label="Completed" value={summary.completed_count} />
        </div>

        {error ? <div style={errorBox}>{error}</div> : null}
        {loading ? (
          <div style={mutedBox}>Loading tasks…</div>
        ) : tasks.length === 0 ? (
          <div style={mutedBox}>No tasks assigned right now.</div>
        ) : (
          <div style={{ display: "grid", gap: 12 }}>
            {tasks.map((task) => (
              <div key={task.task_id} style={card}>
                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                  <div>
                    <div style={{ fontSize: 18, fontWeight: 700, color: "var(--text-primary)", marginBottom: 4 }}>{task.title}</div>
                    <div style={{ fontSize: 13, color: "var(--text-accent)", fontWeight: 600 }}>{task.task_type}</div>
                  </div>
                  <TaskStatusPill status={task.status} />
                </div>
                {task.description ? (
                  <div style={{ marginTop: 10, fontSize: 14, color: "var(--text-secondary)", lineHeight: 1.6 }}>{task.description}</div>
                ) : null}
                <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 12, fontSize: 12, color: "var(--text-muted)" }}>
                  {task.case_id ? <span>Case: {task.case_id}</span> : null}
                  {task.scheduled_for ? <span>Scheduled: {task.scheduled_for}</span> : null}
                  {task.due_at ? <span>Due: {task.due_at}</span> : null}
                </div>
                <div style={{ display: "flex", gap: 8, marginTop: 14, flexWrap: "wrap" }}>
                  {["assigned", "in_progress", "completed"].map((status) => (
                    <button
                      key={status}
                      type="button"
                      onClick={() => updateStatus(task.task_id, status)}
                      style={{
                        padding: "7px 10px",
                        borderRadius: 999,
                        border: "1px solid var(--border-strong)",
                        background: task.status === status ? "var(--bg-accent)" : "var(--surface-0)",
                        color: task.status === status ? "var(--text-accent)" : "var(--text-secondary)",
                        cursor: "pointer",
                        fontSize: 12,
                        textTransform: "capitalize",
                      }}
                    >
                      {status.replace("_", " ")}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function SummaryCard({ label, value }) {
  return (
    <div style={card}>
      <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, color: "var(--text-primary)" }}>{value}</div>
    </div>
  );
}

function TaskStatusPill({ status }) {
  const styles = {
    assigned: { background: "var(--bg-accent)", color: "var(--text-accent)", border: "1px solid var(--border-accent)" },
    in_progress: { background: "var(--surface-0)", color: "var(--text-primary)", border: "1px solid var(--border-strong)" },
    completed: { background: "var(--bg-success)", color: "var(--text-success)", border: "1px solid var(--border-success)" },
  };
  return (
    <span style={{ padding: "5px 9px", borderRadius: 999, fontSize: 12, textTransform: "capitalize", ...styles[status] }}>
      {status.replace("_", " ")}
    </span>
  );
}

const card = {
  padding: "16px 18px",
  borderRadius: 14,
  border: "1px solid var(--border)",
  background: "var(--surface-1)",
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

const mutedBox = {
  ...card,
  color: "var(--text-muted)",
  textAlign: "center",
};

const errorBox = {
  ...card,
  color: "var(--text-danger)",
  background: "var(--bg-danger)",
  border: "1px solid var(--border-danger)",
};
