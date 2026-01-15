"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { AuthShell } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/auth-context";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

function getPasswordStrength(password) {
  let score = 0;
  if (password.length >= 8) score += 1;
  if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score += 1;
  if (/\d/.test(password) || /[^A-Za-z0-9]/.test(password)) score += 1;
  if (score <= 1) return { score, label: "Weak" };
  if (score === 2) return { score, label: "Good" };
  return { score, label: "Strong" };
}

export default function RegisterPage() {
  const router = useRouter();
  const { register, pending, bootstrapping, isAuthenticated } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const strength = useMemo(() => getPasswordStrength(password), [password]);

  useEffect(() => {
    if (!bootstrapping && isAuthenticated) {
      router.replace("/dashboard");
    }
  }, [bootstrapping, isAuthenticated, router]);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    try {
      await register({
        email,
        password,
        full_name: fullName || null,
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to create account.");
    }
  }

  return (
    <AuthShell
      title="Start your automated content engine in minutes."
      subtitle="Join the modern content operations platform designed for high-performance creators."
      footer={
        <p className="text-sm text-on-surface-variant">
          Already have an account?{" "}
          <Link href="/login" className="font-semibold text-primary hover:underline">
            Log in
          </Link>
        </p>
      }
    >
      <div className="mx-auto w-full max-w-md space-y-8">
        <div className="space-y-2">
          <h2 className="font-display text-3xl font-semibold tracking-tight text-on-surface">
            Create your account
          </h2>
          <p className="text-sm text-on-surface-variant">
            Set up your creatoros workspace in under a minute.
          </p>
        </div>

        <form className="space-y-5" onSubmit={handleSubmit}>
          <div className="space-y-2">
            <Label htmlFor="full_name">Full name</Label>
            <Input
              id="full_name"
              autoComplete="name"
              placeholder="Jane Doe"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="email">Work email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              placeholder="jane@company.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              minLength={8}
              required
            />
            <div className="flex items-center gap-3 pt-1">
              <div className="grid flex-1 grid-cols-3 gap-1.5">
                {[1, 2, 3].map((level) => (
                  <div
                    key={level}
                    className={cn(
                      "h-1.5 rounded-full bg-surface-container-high",
                      strength.score >= level && "bg-primary",
                    )}
                  />
                ))}
              </div>
              <span className="font-label text-xs text-outline">{strength.label}</span>
            </div>
          </div>

          {error ? (
            <div className="rounded-lg border border-error/20 bg-error-container/60 px-3 py-2 text-sm text-error">
              {error}
            </div>
          ) : null}

          <Button type="submit" className="w-full" disabled={pending}>
            {pending ? "Creating account…" : "Create account"}
          </Button>
        </form>
      </div>
    </AuthShell>
  );
}
