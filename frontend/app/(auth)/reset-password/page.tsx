"use client";

import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";

export default function ResetPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    // Wired to a dedicated /auth/password-reset endpoint once email
    // delivery is configured; the UI flow is intentionally ready ahead of it.
    setSent(true);
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <Card className="w-full max-w-sm">
        <h1 className="mb-6 text-xl font-semibold">Reset your password</h1>
        {sent ? (
          <p className="text-sm text-slate-600">
            If an account exists for {email}, a reset link has been sent.
          </p>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <Input label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            <Button type="submit" className="mt-2 w-full">
              Send reset link
            </Button>
          </form>
        )}
      </Card>
    </main>
  );
}
