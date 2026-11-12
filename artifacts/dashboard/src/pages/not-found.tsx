import { BrandLockup } from '@/lib/brand-assets';

type NotFoundProps = {
  markUrl: string | null;
  landscapeAvailable: boolean;
};

export default function NotFound({
  markUrl,
  landscapeAvailable,
}: NotFoundProps) {
  return (
    <main
      className={`page-graphite not-found-page ${landscapeAvailable ? 'has-landscape' : ''}`}
      data-testid="page-not-found"
    >
      <BrandLockup markUrl={markUrl} className="not-found-brand" />
      <section className="not-found-card">
        <h1>Page not found</h1>
        <p>This page is not available.</p>
      </section>
    </main>
  );
}
