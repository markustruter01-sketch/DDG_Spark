import { useEffect, useRef, useState } from 'react';

// The product name. Change it here only.
export const PRODUCT_NAME = 'Spark';

export const brandAssetUrl = (filename: string) => {
  const base = import.meta.env.BASE_URL.endsWith('/')
    ? import.meta.env.BASE_URL
    : `${import.meta.env.BASE_URL}/`;
  return `${base}brand/${filename}`;
};

type BrandAssets = {
  markUrl: string | null;
  landscapeUrl: string | null;
};

const preloadImage = (filename: string) =>
  new Promise<string | null>((resolve) => {
    const candidate = `${brandAssetUrl(filename)}?asset-check=${Date.now()}`;
    const image = new Image();
    image.onload = () => resolve(candidate);
    image.onerror = () => resolve(null);
    image.src = candidate;
  });

export function useBrandAssets(): BrandAssets {
  const found = useRef<BrandAssets>({ markUrl: null, landscapeUrl: null });
  const [assets, setAssets] = useState<BrandAssets>(found.current);

  useEffect(() => {
    let cancelled = false;
    let retryTimer: number | undefined;

    const check = async () => {
      const [markUrl, landscapeUrl] = await Promise.all([
        found.current.markUrl
          ? Promise.resolve(found.current.markUrl)
          : preloadImage('ddg-mark-glitch.png'),
        found.current.landscapeUrl
          ? Promise.resolve(found.current.landscapeUrl)
          : preloadImage('night-glass-landscape.jpg'),
      ]);

      if (cancelled) return;
      found.current = { markUrl, landscapeUrl };
      setAssets(found.current);

      if (!markUrl || !landscapeUrl) {
        retryTimer = window.setTimeout(check, 5000);
      }
    };

    void check();
    return () => {
      cancelled = true;
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
    };
  }, []);

  return assets;
}

type BrandLockupProps = {
  markUrl: string | null;
  className?: string;
  large?: boolean;
};

export function BrandLockup({
  markUrl,
  className = '',
  large = false,
}: BrandLockupProps) {
  const [markFailed, setMarkFailed] = useState(false);

  useEffect(() => setMarkFailed(false), [markUrl]);

  return (
    <div
      className={`brand-lockup ${className} ${large ? 'brand-lockup-large' : ''}`}
      role="img"
      aria-label={`DDG ${PRODUCT_NAME}`}
      data-testid="brand-lockup"
    >
      {markUrl && !markFailed && (
        <img
          className="brand-logo-mark"
          src={markUrl}
          alt=""
          aria-hidden="true"
          onError={() => setMarkFailed(true)}
          data-testid="brand-mark"
        />
      )}
      <span className="brand-ddg">DDG</span>
      <span className="brand-divider" aria-hidden="true" />
      <span className="brand-name">{PRODUCT_NAME}</span>
    </div>
  );
}

type IntroPhase = 'checking' | 'playing' | 'fading' | 'done';

const introPlayedKey = 'spark-intro-played';

function shouldShowIntro(): boolean {
  if (typeof window === 'undefined') return false;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return false;
  try {
    return window.sessionStorage.getItem(introPlayedKey) !== 'true';
  } catch {
    return false;
  }
}

export function IntroLoader({ markUrl }: { markUrl: string | null }) {
  const [phase, setPhase] = useState<IntroPhase>(
    shouldShowIntro() ? 'checking' : 'done',
  );
  const [videoSource] = useState(
    () => `${brandAssetUrl('ddg-loader.mp4')}?asset-check=${Date.now()}`,
  );
  const videoRef = useRef<HTMLVideoElement>(null);

  const markPlayed = () => {
    try {
      window.sessionStorage.setItem(introPlayedKey, 'true');
    } catch {
      // Session storage can be unavailable in restricted browser contexts.
    }
  };

  const skip = (recordSession = true) => {
    if (recordSession) markPlayed();
    setPhase('done');
  };

  useEffect(() => {
    if (phase !== 'checking' && phase !== 'playing') return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      skip();
      return;
    }

    const fallbackTimer = window.setTimeout(
      () => skip(phase === 'playing'),
      phase === 'checking' ? 2400 : 8000,
    );
    const motionPreference = window.matchMedia(
      '(prefers-reduced-motion: reduce)',
    );
    const skipOnInput = () => skip();
    const skipForMotion = () => {
      if (motionPreference.matches) skip();
    };
    window.addEventListener('pointerdown', skipOnInput);
    window.addEventListener('keydown', skipOnInput);
    motionPreference.addEventListener('change', skipForMotion);

    return () => {
      window.clearTimeout(fallbackTimer);
      window.removeEventListener('pointerdown', skipOnInput);
      window.removeEventListener('keydown', skipOnInput);
      motionPreference.removeEventListener('change', skipForMotion);
    };
  }, [phase]);

  const startVideo = () => {
    const video = videoRef.current;
    if (!video || phase !== 'checking') return;
    const playback = video.play();
    if (playback) playback.catch(skip);
  };

  const finishVideo = () => {
    setPhase('fading');
    window.setTimeout(skip, 400);
  };

  if (phase === 'done') return null;

  return (
    <div
      className={`intro-overlay ${phase === 'fading' ? 'intro-overlay-fading' : ''}`}
      role="presentation"
      data-testid="intro-overlay"
    >
      <video
        ref={videoRef}
        className="intro-video"
        src={videoSource}
        autoPlay
        muted
        playsInline
        preload="auto"
        controls={false}
        aria-hidden="true"
        onCanPlay={startVideo}
        onPlaying={() => {
          markPlayed();
          setPhase('playing');
        }}
        onEnded={finishVideo}
        onError={() => skip(false)}
        data-testid="intro-video"
      />
      {phase === 'checking' && (
        <BrandLockup
          markUrl={markUrl}
          className="intro-fallback-lockup"
        />
      )}
    </div>
  );
}
