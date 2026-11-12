import { type FormEvent, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  getSessionInfoApiAuthSessionGetQueryKey,
  useSignInApiAuthSignInPost,
} from '@workspace/api-client-react';
import { BrandLockup } from '@/lib/brand-assets';
import { useLocation } from 'wouter';

type SignInPageProps = {
  markUrl: string | null;
  landscapeAvailable: boolean;
};

export default function SignInPage({ markUrl, landscapeAvailable }: SignInPageProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const queryClient = useQueryClient();
  const [, setLocation] = useLocation();
  const signIn = useSignInApiAuthSignInPost({ request: { credentials: 'same-origin' } });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    signIn.mutate(
      { data: { email: email.trim(), password } },
      {
        onSuccess: (session) => {
          queryClient.setQueryData(getSessionInfoApiAuthSessionGetQueryKey(), session);
          setLocation('/');
        },
        onError: (cause) => {
          const status = (cause as { status?: number }).status;
          setError(status === 401 ? 'Email or password is incorrect.' : 'Sign-in is unavailable right now.');
        },
      },
    );
  };

  return (
    <main
      className={`sign-in-page page-graphite ${landscapeAvailable ? 'has-landscape' : ''}`}
      data-testid="page-sign-in"
    >
      <section className="sign-in-card" aria-labelledby="sign-in-title">
        <BrandLockup markUrl={markUrl} className="sign-in-brand" large />
        <h1 id="sign-in-title">Sign in</h1>
        <p className="sign-in-intro">Use your account to continue.</p>
        <form className="sign-in-form" onSubmit={submit}>
          <label htmlFor="sign-in-email">Email</label>
          <input
            id="sign-in-email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            data-testid="input-sign-in-email"
          />
          <label htmlFor="sign-in-password">Password</label>
          <input
            id="sign-in-password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            data-testid="input-sign-in-password"
          />
          {error && (
            <p className="sign-in-error" role="alert" data-testid="sign-in-error">
              <span className="status-dot status-dot-problem" aria-hidden="true" />
              Problem: {error}
            </p>
          )}
          <button
            className="sign-in-submit"
            type="submit"
            disabled={signIn.isPending}
            data-testid="button-sign-in"
          >
            {signIn.isPending ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </section>
    </main>
  );
}
