import { useState } from "react";

const USERNAME_MIN_LENGTH = 3;
const PASSWORD_MIN_LENGTH = 8;
const USERNAME_MAX_LENGTH = 80;
const PASSWORD_MAX_LENGTH = 256;

function splitDegrees(text) {
  return text
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}

function formatFieldLabel(field) {
  const labels = {
    username: "Username",
    password: "Password",
    display_name: "Full name",
    training_level: "Level of training",
    year_in_program: "Year in program",
    degrees: "Degrees",
  };
  return labels[field] || field;
}

function normalizeValidationMessage(message) {
  if (!message) return "Invalid value.";
  return message
    .replace("String should have at least", "Must have at least")
    .replace("String should have at most", "Must have at most")
    .replace("characters", "characters");
}

function readErrorMessage(data, fallback) {
  if (!data) return fallback;
  if (typeof data.detail === "string" && data.detail.trim()) return data.detail;
  if (Array.isArray(data.detail) && data.detail.length) {
    return data.detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item?.msg) {
          const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : "";
          const label = field ? formatFieldLabel(field) : "";
          const message = normalizeValidationMessage(item.msg);
          return label ? `${label}: ${message}` : message;
        }
        return null;
      })
      .filter(Boolean)
      .join(" | ");
  }
  return fallback;
}

function validateRegisterForm(form) {
  const errors = [];
  const displayName = form.display_name.trim();
  const username = form.username.trim();
  const password = form.password;

  if (!displayName) {
    errors.push("Full name is required.");
  }
  if (!username) {
    errors.push("Username is required.");
  } else {
    if (username.length < USERNAME_MIN_LENGTH) {
      errors.push(`Username must be at least ${USERNAME_MIN_LENGTH} characters.`);
    }
    if (username.length > USERNAME_MAX_LENGTH) {
      errors.push(`Username must be at most ${USERNAME_MAX_LENGTH} characters.`);
    }
  }
  if (!password) {
    errors.push("Password is required.");
  } else {
    if (password.length < PASSWORD_MIN_LENGTH) {
      errors.push(`Password must be at least ${PASSWORD_MIN_LENGTH} characters.`);
    }
    if (password.length > PASSWORD_MAX_LENGTH) {
      errors.push(`Password must be at most ${PASSWORD_MAX_LENGTH} characters.`);
    }
  }

  return errors;
}

export default function AuthPage({ dark, onToggleDark, onLogin }) {
  const [mode, setMode] = useState("login");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const [loginForm, setLoginForm] = useState({
    username: "",
    password: "",
  });

  const [registerForm, setRegisterForm] = useState({
    display_name: "",
    username: "",
    password: "",
    training_level: "",
    year_in_program: "",
    degrees: "",
  });

  async function submitLogin(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(loginForm),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(readErrorMessage(data, "Unable to sign in"));
      onLogin(data.user);
    } catch (err) {
      setError(err.message || "Unable to sign in");
    } finally {
      setLoading(false);
    }
  }

  async function submitRegister(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setMessage("");
    const validationErrors = validateRegisterForm(registerForm);
    if (validationErrors.length) {
      setError(validationErrors.join(" "));
      setLoading(false);
      return;
    }
    try {
      const response = await fetch("/api/v1/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...registerForm,
          degrees: splitDegrees(registerForm.degrees),
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(readErrorMessage(data, "Unable to create account"));
      setMessage("Account created. An admin can promote reviewer/admin roles later if needed.");
      setMode("login");
      setLoginForm((current) => ({ ...current, username: registerForm.username }));
      setRegisterForm({
        display_name: "",
        username: "",
        password: "",
        training_level: "",
        year_in_program: "",
        degrees: "",
      });
    } catch (err) {
      setError(err.message || "Unable to create account");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", background: "var(--surface-0)", fontFamily: "var(--font-sans)" }}>
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: "14px 24px", borderBottom: "1px solid var(--border)", background: "var(--surface-1)",
      }}>
        <span style={{ fontSize: 17, fontWeight: 600, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>docent.ID</span>
        <button onClick={onToggleDark} style={headerButton}>{dark ? "Light" : "Dark"}</button>
      </div>

      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
        <div style={{ width: "100%", maxWidth: 460, display: "grid", gap: 16 }}>
          <div style={{
            background: "var(--modal-bg)",
            border: "1px solid var(--modal-border)",
            borderRadius: 14,
            padding: "28px 28px 24px",
            boxShadow: "0 8px 32px rgba(0,0,0,0.08)",
          }}>
            <div style={{ display: "flex", gap: 8, marginBottom: 18 }}>
              {[
                { id: "login", label: "Sign in" },
                { id: "register", label: "New user intake" },
              ].map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => { setMode(tab.id); setError(""); setMessage(""); }}
                  style={{
                    flex: 1,
                    padding: "9px 12px",
                    borderRadius: 10,
                    border: "1px solid var(--border-strong)",
                    background: mode === tab.id ? "var(--bg-accent)" : "var(--surface-0)",
                    color: mode === tab.id ? "var(--text-accent)" : "var(--text-secondary)",
                    cursor: "pointer",
                    fontSize: 13,
                    fontWeight: 600,
                  }}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <h2 style={{ fontSize: 22, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 4px" }}>
              {mode === "login" ? "Sign in" : "New user intake"}
            </h2>
            <p style={{ fontSize: 13, color: "var(--text-muted)", margin: "0 0 20px", lineHeight: 1.6 }}>
              {mode === "login"
                ? "Use your docent.ID credentials. The default seeded admin account is still `admin` / `admin` until you change it."
                : "Create a new student account and fill in the study intake fields. Passwords must be at least 8 characters, and roles can be adjusted later from the admin view."}
            </p>

            {mode === "register" ? (
              <div style={requirementsBox}>
                <div style={requirementsTitle}>Account requirements</div>
                <div style={requirementsItem}>Full name is required.</div>
                <div style={requirementsItem}>Username must be {USERNAME_MIN_LENGTH}-{USERNAME_MAX_LENGTH} characters.</div>
                <div style={requirementsItem}>Password must be {PASSWORD_MIN_LENGTH}-{PASSWORD_MAX_LENGTH} characters.</div>
              </div>
            ) : null}

            {error ? (
              <div style={{ fontSize: 13, color: "var(--text-danger)", padding: "8px 10px", background: "var(--bg-danger)", border: "1px solid var(--border-danger)", borderRadius: 10, marginBottom: 14 }}>
                {error}
              </div>
            ) : null}
            {message ? (
              <div style={{ fontSize: 13, color: "var(--text-success)", padding: "8px 10px", background: "var(--bg-success)", border: "1px solid var(--border-success)", borderRadius: 10, marginBottom: 14 }}>
                {message}
              </div>
            ) : null}

            {mode === "login" ? (
              <form onSubmit={submitLogin} style={{ display: "grid", gap: 14 }}>
                <LabeledInput
                  label="Username"
                  value={loginForm.username}
                  onChange={(value) => setLoginForm((current) => ({ ...current, username: value }))}
                  autoFocus
                  required
                />
                <LabeledInput
                  label="Password"
                  type="password"
                  value={loginForm.password}
                  onChange={(value) => setLoginForm((current) => ({ ...current, password: value }))}
                  required
                />
                <button type="submit" disabled={loading} style={submitButton(loading)}>
                  {loading ? "Signing in..." : "Sign in"}
                </button>
              </form>
            ) : (
              <form onSubmit={submitRegister} style={{ display: "grid", gap: 14 }}>
                <LabeledInput
                  label="Full name"
                  value={registerForm.display_name}
                  onChange={(value) => setRegisterForm((current) => ({ ...current, display_name: value }))}
                  autoFocus
                  required
                  hint="Required."
                />
                <LabeledInput
                  label="Username"
                  value={registerForm.username}
                  onChange={(value) => setRegisterForm((current) => ({ ...current, username: value }))}
                  required
                  minLength={USERNAME_MIN_LENGTH}
                  maxLength={USERNAME_MAX_LENGTH}
                  hint={`${USERNAME_MIN_LENGTH}-${USERNAME_MAX_LENGTH} characters.`}
                />
                <LabeledInput
                  label="Password"
                  type="password"
                  value={registerForm.password}
                  onChange={(value) => setRegisterForm((current) => ({ ...current, password: value }))}
                  required
                  minLength={PASSWORD_MIN_LENGTH}
                  maxLength={PASSWORD_MAX_LENGTH}
                  hint={`At least ${PASSWORD_MIN_LENGTH} characters.`}
                />
                <LabeledInput
                  label="Level of training"
                  value={registerForm.training_level}
                  onChange={(value) => setRegisterForm((current) => ({ ...current, training_level: value }))}
                  placeholder="Medical student, resident, fellow..."
                />
                <LabeledInput
                  label="Year in program"
                  value={registerForm.year_in_program}
                  onChange={(value) => setRegisterForm((current) => ({ ...current, year_in_program: value }))}
                  placeholder="MS2, PGY-1, Fellow year 2..."
                />
                <LabeledInput
                  label="Degrees"
                  value={registerForm.degrees}
                  onChange={(value) => setRegisterForm((current) => ({ ...current, degrees: value }))}
                  placeholder="MD, PhD, MPH"
                />
                <button type="submit" disabled={loading} style={submitButton(loading)}>
                  {loading ? "Creating account..." : "Create account"}
                </button>
              </form>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function LabeledInput({
  label,
  value,
  onChange,
  type = "text",
  autoFocus = false,
  placeholder = "",
  hint = "",
  required = false,
  minLength,
  maxLength,
}) {
  return (
    <div>
      <label style={{ fontSize: 13, color: "var(--text-secondary)", display: "block", marginBottom: 5 }}>{label}</label>
      <input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        autoFocus={autoFocus}
        placeholder={placeholder}
        required={required}
        minLength={minLength}
        maxLength={maxLength}
        style={{
          width: "100%",
          padding: "9px 11px",
          borderRadius: 10,
          border: "1px solid var(--border-strong)",
          background: "var(--surface-0)",
          color: "var(--text-primary)",
          fontSize: 14,
          boxSizing: "border-box",
          outline: "none",
        }}
      />
      {hint ? (
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 5 }}>
          {hint}
        </div>
      ) : null}
    </div>
  );
}

const requirementsBox = {
  marginBottom: 14,
  padding: "10px 12px",
  borderRadius: 10,
  background: "var(--surface-0)",
  border: "1px solid var(--border)",
};

const requirementsTitle = {
  fontSize: 12,
  fontWeight: 700,
  color: "var(--text-primary)",
  marginBottom: 6,
  textTransform: "uppercase",
  letterSpacing: "0.04em",
};

const requirementsItem = {
  fontSize: 12,
  color: "var(--text-secondary)",
  lineHeight: 1.5,
};

const headerButton = {
  padding: "5px 12px",
  border: "1px solid var(--border-strong)",
  borderRadius: "var(--radius)",
  background: "transparent",
  color: "var(--text-secondary)",
  cursor: "pointer",
  fontSize: 13,
};

function submitButton(loading) {
  return {
    padding: "10px",
    background: loading ? "var(--fill-disabled)" : "var(--fill-accent)",
    color: loading ? "var(--text-disabled)" : "var(--on-accent)",
    border: "none",
    borderRadius: "var(--radius)",
    cursor: loading ? "default" : "pointer",
    fontSize: 14,
    fontWeight: 600,
    marginTop: 4,
  };
}
