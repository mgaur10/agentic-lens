import React, { useState } from "react";

const TELEMETRY_STORAGE_KEY = "lens_telemetry_submitted";
const TELEMETRY_INACTIVITY_MS = 30 * 60 * 1000;

type TelemetryState = {
  submitted: boolean;
  submittedAt: number;
  lastActivityAt: number;
};

const now = (): number => Date.now();

const readTelemetryState = (): TelemetryState | null => {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(TELEMETRY_STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<TelemetryState>;
    if (
      typeof parsed.submitted !== "boolean" ||
      typeof parsed.submittedAt !== "number" ||
      typeof parsed.lastActivityAt !== "number"
    ) {
      return null;
    }
    return {
      submitted: parsed.submitted,
      submittedAt: parsed.submittedAt,
      lastActivityAt: parsed.lastActivityAt,
    };
  } catch {
    return null;
  }
};

const writeTelemetryState = (state: TelemetryState): void => {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TELEMETRY_STORAGE_KEY, JSON.stringify(state));
};

export function getTelemetrySubmitted(): boolean {
  if (typeof window === "undefined") return false;
  const state = readTelemetryState();
  if (!state?.submitted) return false;
  const currentTs = now();
  const inactiveForMs = currentTs - state.lastActivityAt;
  if (inactiveForMs > TELEMETRY_INACTIVITY_MS) {
    window.localStorage.removeItem(TELEMETRY_STORAGE_KEY);
    return false;
  }
  writeTelemetryState({ ...state, lastActivityAt: currentTs });
  return true;
}

export function setTelemetrySubmitted(): void {
  if (typeof window === "undefined") return;
  const currentTs = now();
  writeTelemetryState({
    submitted: true,
    submittedAt: currentTs,
    lastActivityAt: currentTs,
  });
}

export function touchTelemetryActivity(): void {
  if (typeof window === "undefined") return;
  const state = readTelemetryState();
  if (!state?.submitted) return;
  writeTelemetryState({ ...state, lastActivityAt: now() });
}

type UsageType = "Customer" | "Personal";

interface LandingPageProps {
  onSuccess: () => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({ onSuccess }) => {
  const [usageType, setUsageType] = useState<UsageType | "">("");
  const [userEmail, setUserEmail] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [opportunityLink, setOpportunityLink] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!usageType || !userEmail.trim()) {
      setError("Please select why you're using the demo and enter your email.");
      return;
    }
    setError(null);
    // Optimistic transition so users reach the app immediately.
    setTelemetrySubmitted();
    onSuccess();
    setSubmitting(true);
    try {
      void fetch("/api/telemetry", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          usage_type: usageType,
          user_email: userEmail.trim(),
          customer_name: usageType === "Customer" ? customerName.trim() || null : null,
          opportunity_link: usageType === "Customer" ? opportunityLink.trim() || null : null,
        }),
      }).catch(() => {
        // Non-blocking: telemetry failure should not interrupt UI access.
      });
    } catch {
      // Defensive: no-op because transition is already completed.
    } finally {
      setSubmitting(false);
    }
  };

  const showCustomerFields = usageType === "Customer";

  return (
    <div className="flex min-h-screen flex-col bg-surface-base/80">
      <main className="relative z-0 mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center px-6 py-12">
        <div className="rounded-xl3 border border-black/5 bg-white/90 p-8 shadow-glass-soft backdrop-blur-md">
          <h1 className="font-heading text-xl font-sharp tracking-tight text-slate-900">
            Welcome to AI Agentic Lens
          </h1>
          <p className="mt-4 text-sm leading-relaxed text-slate-600">
            We are tracking the usage of this demo to measure usefulness and determine if we should continue supporting demos. Please fill out the information below, and you will be taken to the demo. If you demo for multiple customers, please be sure to come back and fill out the form again. This will not be shared externally and your customer will not be contacted.
          </p>

          <section className="mt-6">
            <h2 className="font-heading text-sm font-semibold tracking-tight text-slate-700">
              Need Help?
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              If you need further help, please submit an ER at{" "}
              <a href="https://goto.google.com/ai-sec-er" target="_blank" rel="noopener noreferrer" className="text-accent-powerBlue hover:underline">
                go/ai-sec-er
              </a>
              .
            </p>
            <p className="mt-1 text-sm text-slate-600">
              For any bugs, please email{" "}
              <a href="mailto:manishkgaur@google.com" className="text-accent-powerBlue hover:underline">
                manishkgaur@google.com
              </a>
              .
            </p>
          </section>

          <form onSubmit={handleSubmit} className="mt-8 space-y-6">
            <div>
              <label className="block text-sm font-medium text-slate-700">
                Why are you using the demo this time? <span className="text-red-500">*</span>
              </label>
              <div className="mt-2 flex gap-6">
                <label className="inline-flex items-center gap-2">
                  <input
                    type="radio"
                    name="usage_type"
                    value="Customer"
                    checked={usageType === "Customer"}
                    onChange={() => setUsageType("Customer")}
                    className="h-4 w-4 border-slate-300 text-accent-powerBlue focus:ring-accent-powerBlue"
                  />
                  <span className="text-sm text-slate-700">Customer</span>
                </label>
                <label className="inline-flex items-center gap-2">
                  <input
                    type="radio"
                    name="usage_type"
                    value="Personal"
                    checked={usageType === "Personal"}
                    onChange={() => setUsageType("Personal")}
                    className="h-4 w-4 border-slate-300 text-accent-powerBlue focus:ring-accent-powerBlue"
                  />
                  <span className="text-sm text-slate-700">Personal</span>
                </label>
              </div>
            </div>

            <div>
              <label htmlFor="user_email" className="block text-sm font-medium text-slate-700">
                Your email address <span className="text-red-500">*</span>
              </label>
              <input
                id="user_email"
                type="email"
                required
                value={userEmail}
                onChange={(e) => setUserEmail(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-accent-powerBlue focus:outline-none focus:ring-1 focus:ring-accent-powerBlue"
                placeholder="you@example.com"
              />
            </div>

            {showCustomerFields && (
              <>
                <div>
                  <label htmlFor="customer_name" className="block text-sm font-medium text-slate-700">
                    Customer name <span className="text-slate-400">(optional)</span>
                  </label>
                  <input
                    id="customer_name"
                    type="text"
                    value={customerName}
                    onChange={(e) => setCustomerName(e.target.value)}
                    className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-accent-powerBlue focus:outline-none focus:ring-1 focus:ring-accent-powerBlue"
                    placeholder="Acme Corp"
                  />
                </div>
                <div>
                  <label htmlFor="opportunity_link" className="block text-sm font-medium text-slate-700">
                    Opportunity or ER link <span className="text-slate-400">(optional)</span>
                  </label>
                  <input
                    id="opportunity_link"
                    type="text"
                    value={opportunityLink}
                    onChange={(e) => setOpportunityLink(e.target.value)}
                    className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-accent-powerBlue focus:outline-none focus:ring-1 focus:ring-accent-powerBlue"
                    placeholder="https://..."
                  />
                </div>
              </>
            )}

            {error && (
              <p className="text-sm text-amber-700" role="alert">
                {error}
              </p>
            )}

            <div>
              <button
                type="submit"
                disabled={submitting}
                className="inline-flex items-center justify-center rounded-lg bg-accent-powerBlue px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-accent-powerBlue/90 focus:outline-none focus:ring-2 focus:ring-accent-powerBlue focus:ring-offset-2 disabled:opacity-60"
              >
                {submitting ? "Submitting…" : "Continue to demo"}
              </button>
            </div>
          </form>
        </div>
      </main>
    </div>
  );
};
