"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiRequest, ApiError } from "@/lib/api/client";

interface Enrollment {
  secret: string;
  otpauth_uri: string;
  expires_in_seconds: number;
}

interface Activity {
  id: string;
  occurred_at: string;
  actor_id: string | null;
  action: string;
  resource_id: string | null;
  details: Record<string, string | number>;
}

interface AuditPage {
  items: Activity[];
  next_cursor: string | null;
}

const labels: Record<string, string> = {
  credit_adjustment: "Credits adjusted",
  credit_adjustment_authorized: "Credit change authorized",
  admin_mfa_enrollment_started: "Authenticator enrollment started",
  admin_mfa_enabled: "Authenticator enabled",
  admin_mfa_rotation_started: "Authenticator replacement started",
  admin_mfa_rotated: "Authenticator replaced",
};

function readableError(cause: unknown, fallback: string) {
  return cause instanceof ApiError ? cause.message : fallback;
}

export function AdminSecurityOperations({
  mfaEnabled,
  refreshKey,
}: {
  mfaEnabled: boolean;
  refreshKey: number;
}) {
  const [rotateOpen, setRotateOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [oldCode, setOldCode] = useState("");
  const [newCode, setNewCode] = useState("");
  const [enrollment, setEnrollment] = useState<Enrollment | null>(null);
  const [rotateBusy, setRotateBusy] = useState(false);
  const [rotationMessage, setRotationMessage] = useState<string | null>(null);
  const [rotationError, setRotationError] = useState<string | null>(null);

  const [auditItems, setAuditItems] = useState<Activity[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [auditVersion, setAuditVersion] = useState(0);

  useEffect(() => {
    let active = true;
    setAuditLoading(true);
    setAuditError(null);
    apiRequest<AuditPage>("/admin/audit?limit=20")
      .then(data => {
        if (!active) return;
        setAuditItems(data.items);
        setNextCursor(data.next_cursor);
      })
      .catch(cause => { if (active) setAuditError(readableError(cause, "Could not load operator history.")); })
      .finally(() => { if (active) setAuditLoading(false); });
    return () => { active = false; };
  }, [refreshKey, auditVersion]);

  const loadMore = useCallback(async () => {
    if (!nextCursor || auditLoading) return;
    setAuditLoading(true);
    setAuditError(null);
    try {
      const data = await apiRequest<AuditPage>(
        `/admin/audit?limit=20&cursor=${encodeURIComponent(nextCursor)}`
      );
      setAuditItems(previous => [...previous, ...data.items]);
      setNextCursor(data.next_cursor);
    } catch (cause) {
      setAuditError(readableError(cause, "Could not load older events."));
    } finally {
      setAuditLoading(false);
    }
  }, [auditLoading, nextCursor]);

  async function startRotation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRotateBusy(true);
    setRotationError(null);
    setRotationMessage(null);
    try {
      const result = await apiRequest<Enrollment>("/admin/mfa/rotation/start", {
        method: "POST", body: { password, code: oldCode },
      });
      setEnrollment(result);
      setPassword("");
      setOldCode("");
      setRotationMessage("Add the replacement key as a NEW entry. Keep your current authenticator until the new one is verified.");
      setAuditVersion(value => value + 1);
    } catch (cause) {
      setRotationError(readableError(cause, "Could not start authenticator replacement."));
    } finally { setRotateBusy(false); }
  }

  async function confirmRotation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRotateBusy(true);
    setRotationError(null);
    try {
      await apiRequest("/admin/mfa/rotation/confirm", {
        method: "POST", body: { code: newCode },
      });
      setEnrollment(null);
      setNewCode("");
      setPassword("");
      setOldCode("");
      setRotateOpen(false);
      setRotationMessage("Authenticator replaced successfully. Your previous device will no longer authorize new adjustments.");
      setAuditVersion(value => value + 1);
    } catch (cause) {
      setRotationError(readableError(cause, "Replacement verification failed. Your original authenticator still works."));
    } finally { setRotateBusy(false); }
  }

  return <>
    <section className="studio-surface mt-6 p-6" aria-label="Authenticator device management">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="studio-eyebrow mb-1">Account continuity</p>
          <h2 className="text-lg font-semibold">Authenticator device management</h2>
          <p className="mt-2 max-w-2xl text-sm text-[#a7acc4]">
            Replacing your phone requires your password and a code from your current authenticator.
            The existing device remains active until you verify the replacement.
          </p>
        </div>
        {mfaEnabled && !rotateOpen && <button type="button" className="studio-button-secondary"
          onClick={() => { setRotateOpen(true); setRotationError(null); setRotationMessage(null); }}>
          Replace authenticator
        </button>}
      </div>
      {!mfaEnabled && <p className="mt-4 text-sm text-amber-200">
        Enable your first authenticator above before attempting device replacement.
      </p>}
      {rotateOpen && !enrollment && <form onSubmit={startRotation} className="mt-5 grid gap-4 border-t border-white/10 pt-5 sm:grid-cols-2">
        <label className="block text-xs font-semibold text-[#b4b8cf]">Administrator password
          <input type="password" autoComplete="current-password" value={password}
            onChange={e => setPassword(e.target.value)} required className="studio-input mt-2" />
        </label>
        <label className="block text-xs font-semibold text-[#b4b8cf]">Current authenticator code
          <input inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code"
            value={oldCode} onChange={e => setOldCode(e.target.value)} required className="studio-input mt-2" />
        </label>
        <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
          <button type="submit" disabled={rotateBusy || !password || !/^[0-9]{6}$/.test(oldCode)}
            className="studio-button">{rotateBusy ? "Starting…" : "Start device replacement"}</button>
          <button type="button" className="studio-button-secondary" onClick={() => {
            setRotateOpen(false); setPassword(""); setOldCode("");
          }}>Cancel</button>
        </div>
      </form>}
      {rotateOpen && enrollment && <div className="mt-5 space-y-4 border-t border-white/10 pt-5">
        <p className="text-sm font-semibold text-amber-200">
          Your replacement setup expires in 10 minutes. Do not remove your existing authenticator until confirmation succeeds.
        </p>
        <div className="rounded-xl border border-violet-400/20 bg-[#111320] p-4">
          <p className="mb-2 text-xs font-semibold text-[#cbc8e6]">Replacement key (shown only now)</p>
          <code className="block break-all text-sm font-semibold tracking-wider text-white">{enrollment.secret}</code>
          <p className="mt-3 text-xs text-[#a6aac4]">Provisioning URI:</p>
          <code className="mt-2 block break-all text-[11px] text-[#9da2bc]">{enrollment.otpauth_uri}</code>
          <p className="mt-3 text-xs text-amber-200">Keep this key private. Do not share a screenshot of this page.</p>
        </div>
        <form onSubmit={confirmRotation} className="flex flex-wrap items-end gap-3">
          <label className="block text-xs font-semibold text-[#b4b8cf]">Six-digit code from your NEW authenticator
            <input inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code"
              required value={newCode} onChange={e => setNewCode(e.target.value)} className="studio-input mt-2" />
          </label>
          <button type="submit" className="studio-button"
            disabled={rotateBusy || !/^[0-9]{6}$/.test(newCode)}>
            {rotateBusy ? "Verifying…" : "Confirm replacement"}
          </button>
          <button type="button" className="studio-button-secondary" onClick={() => {
            setEnrollment(null); setNewCode(""); setRotationError(null);
          }}>Start over with existing device</button>
        </form>
      </div>}
      {rotationMessage && <p role="status" className="mt-4 text-sm text-emerald-300">{rotationMessage}</p>}
      {rotationError && <p role="alert" className="mt-4 text-sm text-rose-300">{rotationError}</p>}
      <p className="mt-4 text-xs text-[#959bb4]">
        Lost access to your old device? Self-service bypass is intentionally unavailable; contact your infrastructure administrator for reviewed recovery.
      </p>
    </section>

    <section className="studio-surface mt-6 p-6" aria-label="Operator activity history">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="studio-eyebrow mb-1">Accountability</p>
          <h2 className="text-lg font-semibold">Administrator activity history</h2>
          <p className="mt-2 text-xs text-[#9fa5bd]">Recorded credit adjustments and authenticator changes (successful actions only).</p>
        </div>
        <button type="button" className="studio-button-secondary"
          onClick={() => setAuditVersion(value => value + 1)} disabled={auditLoading}>
          Refresh history
        </button>
      </div>
      {auditError && <p role="alert" className="mb-4 text-sm text-rose-300">{auditError}</p>}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[670px] text-left text-xs">
          <thead className="text-[#a9abc2]">
            <tr>{["Time", "Event", "Administrator", "Target", "Details"].map(label =>
              <th key={label} className="border-b border-white/10 px-2 py-3">{label}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-white/[0.07]">
            {auditItems.map(item => <tr key={item.id}>
              <td className="whitespace-nowrap px-2 py-3 text-[#b4b9d0]">
                {new Date(item.occurred_at).toLocaleString()}
              </td>
              <td className="px-2 py-3">{labels[item.action] ?? item.action}</td>
              <td className="max-w-[130px] break-all px-2 py-3 font-mono text-[#9fa5bd]">{item.actor_id ?? "—"}</td>
              <td className="max-w-[130px] break-all px-2 py-3 font-mono text-[#9fa5bd]">{item.resource_id ?? "—"}</td>
              <td className="max-w-[250px] break-words px-2 py-3 text-[#b4b9d0]">
                {Object.entries(item.details).map(([key, value]) =>
                  <div key={key}><span className="text-[#858ca6]">{key}:</span> {String(value)}</div>)}
              </td>
            </tr>)}
            {!auditItems.length && !auditLoading && <tr><td colSpan={5} className="py-8 text-center text-[#989eb9]">
              No recorded administrator actions yet.
            </td></tr>}
          </tbody>
        </table>
      </div>
      {auditLoading && <p className="mt-3 text-sm text-[#aab0c8]">Loading activity…</p>}
      {nextCursor && <button type="button" disabled={auditLoading}
        onClick={loadMore} className="studio-button-secondary mt-4">Load older activity</button>}
    </section>
  </>;
}
