"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Eye, EyeOff } from "lucide-react";

import { AuthModeTabs } from "@/components/auth/auth-mode-tabs";
import { AuthShell } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/auth-context";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const { login, pending, bootstrapping, isAuthenticated } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!bootstrapping && isAuthenticated) {
      router.replace("/dashboard");
    }
  }, [bootstrapping, isAuthenticated, router]);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    try {
      await login({ email, password });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to sign in.");
    }
  }

  return (
    <AuthShell
      title="The intelligent platform for high-performance content operations."
      subtitle="Streamline your workflow with AI-driven insights — sign in to continue."
      footer={
        <p className="text-sm text-on-surface-variant">
          New to creatoros?{" "}
          <Link href="/register" className="font-semibold text-primary hover:underline">
            Create an account
          </Link>
        </p>
      }
    >
      <div className="mx-auto w-full max-w-md space-y-8">
        <AuthModeTabs active="login" />
        <div className="space-y-2">
          <h2 className="font-display text-3xl font-semibold tracking-tight text-on-surface">
            Welcome back
          </h2>
          <p className="text-sm text-on-surface-variant">
            Sign in to continue to your workspace.
          </p>
        </div>

        <form className="space-y-5" onSubmit={handleSubmit}>
          <div className="space-y-2">
            <Label htmlFor="email">Email address</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              placeholder="name@company.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <div className="relative">
              <Input
                id="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                className="pr-11"
              />
              <button
                type="button"
                className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-outline hover:text-on-surface"
                onClick={() => setShowPassword((value) => !value)}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          {error ? (
            <div className="rounded-lg border border-error/20 bg-error-container/60 px-3 py-2 text-sm text-error">
              {error}
            </div>
          ) : null}

          <Button type="submit" className="w-full" disabled={pending}>
            {pending ? "Signing in…" : "Sign In"}
          </Button>
        </form>
      </div>
    </AuthShell>
  );
}
