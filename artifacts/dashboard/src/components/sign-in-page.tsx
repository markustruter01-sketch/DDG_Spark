import { type FormEvent, useState } from 'react';
import { BrandLockup } from '@/lib/brand-assets';

type SignInPageProps = {
  markUrl: string | null;
  landscapeAvailable: boolean;
  checkingSession: boolean;
  onSignedIn: () => void;
};

export default function SignInPage({
  markUrl,
  landscapeAvailable,
  checkingSession,
  onSignedIn,
}: SignInPageProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      const response = await fetch('/api/auth/sign-in', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });

      if (!response.ok) {
        setError(
          response.status === 401
            ? 'Email or password is incorrect.'
            : 'Sign-in is unavailable right now.',
        );
        return;
      }

      onSignedIn();
    } catch {
      setError('Sign-in is unavailable right now.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main
      className={`sign-in-page page-graphite ${landscapeAvailable ? 'has-landscape' : ''}`}
      data-testid="page-sign-in"
    >
      <section className="sign-in-card" aria-labelledby="sign-in-title">
        <BrandLockup
          markUrl={markUrl}
          className="sign-in-brand"
          large
        />
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
              {error}
            </p>
          )}
          <button
            className="button-primary sign-in-submit"
            type="submit"
            disabled={checkingSession || submitting}
            data-testid="button-sign-in"
          >
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </section>
    </main>
  );
}
