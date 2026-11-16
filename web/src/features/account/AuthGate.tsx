import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { Card, ErrorState, Loading } from "../../components/States";
import { api, ApiProblem, unwrap } from "../../lib/api";
import { userManager } from "../../lib/auth";

export const meKey = ["me"] as const;

export function useMe() {
  return useQuery({ queryKey: meKey, queryFn: async () => unwrap(await api.GET("/me")) });
}

/** Shows its children only to a signed-in founder whose company exists (D-64). */
export function AuthGate({ children }: { children: ReactNode }) {
  const me = useMe();
  if (me.isPending) return <Loading label="Checking your sign-in…" />;
  if (me.error instanceof ApiProblem && me.error.status === 401) return <SignIn />;
  if (me.error) return <ErrorState error={me.error} onRetry={() => void me.refetch()} />;
  if (me.data.company_id === null) return <Onboarding />;
  return <>{children}</>;
}

export function SignIn() {
  return (
    <Card className="max-w-md">
      <h1 className="m-0 text-2xl font-semibold">Sign in to Home Base</h1>
      <p className="mt-2 mb-5 text-sm text-ink-muted">
        You sign in with your email. If you are new, you can create your account there.
      </p>
      <button
        type="button"
        className="btn-primary"
        onClick={() => void userManager().signinRedirect()}
      >
        Sign in
      </button>
    </Card>
  );
}

export function Onboarding() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: async (companyName: string) =>
      unwrap(await api.POST("/onboarding", { body: { company_name: companyName } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: meKey }),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (trimmed) create.mutate(trimmed);
  }

  return (
    <Card className="max-w-md">
      <h1 className="m-0 text-2xl font-semibold">Set up your company</h1>
      <form onSubmit={submit} className="mt-5 flex flex-col gap-4">
        <label className="flex flex-col gap-1.5 text-sm font-semibold">
          Company name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            className="min-h-11 rounded-xl border border-line bg-white px-3 font-normal"
          />
        </label>
        {create.error && <ErrorState error={create.error} />}
        <button
          type="submit"
          className="btn-primary self-start"
          disabled={create.isPending || !name.trim()}
        >
          {create.isPending ? "Setting up…" : "Continue"}
        </button>
      </form>
    </Card>
  );
}

// A code can be exchanged once; React's StrictMode runs effects twice in development.
let callback: Promise<unknown> | null = null;

/** Keycloak sends the browser back here with a code; exchange it, then go to Today. */
export function SignInCallback() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    callback ??= userManager().signinRedirectCallback();
    callback
      .then(async () => {
        await queryClient.invalidateQueries({ queryKey: meKey });
        await navigate("/", { replace: true });
      })
      .catch(setError);
  }, [navigate, queryClient]);
  return error ? <ErrorState error={error} /> : <Loading label="Signing you in…" />;
}
