import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { useLocation } from 'wouter';
import { PRODUCT_NAME } from '@/lib/brand-assets';

type Harness = { key: string; label: string };
type NodePosition = { key: string; x: number; y: number };

export default function StageZeroCore({ harnesses }: { harnesses: Harness[] }) {
  const stageRef = useRef<HTMLDivElement>(null);
  const [positions, setPositions] = useState<NodePosition[]>([]);
  const [webglAvailable, setWebglAvailable] = useState(true);
  const [, setLocation] = useLocation();

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    let renderer: any;
    try {
      renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    } catch {
      setWebglAvailable(false);
      return;
    }
    setWebglAvailable(true);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    renderer.setClearColor(0x000000, 0);
    renderer.domElement.className = 'core-canvas';
    renderer.domElement.setAttribute('aria-hidden', 'true');
    stage.prepend(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    camera.position.set(0, 0, 8.5);
    const orbit = new THREE.Group();
    scene.add(orbit);
    const centerGeometry = new THREE.SphereGeometry(0.45, 32, 24);
    const centerMaterial = new THREE.MeshBasicMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: 0.1,
      wireframe: true,
    });
    const center = new THREE.Mesh(centerGeometry, centerMaterial);
    orbit.add(center);

    const nodeMeshes: any[] = [];
    harnesses.forEach((_, index) => {
      const angle = (index / Math.max(harnesses.length, 1)) * Math.PI * 2;
      const radius = 2.25;
      const x = Math.cos(angle) * radius;
      const y = Math.sin(angle) * radius * 0.74;
      const z = Math.sin(angle * 2) * 0.22;
      const dot = new THREE.Mesh(
        new THREE.SphereGeometry(0.075, 16, 12),
        new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.85 }),
      );
      dot.position.set(x, y, z);
      orbit.add(dot);
      nodeMeshes.push(dot);
      const points = [new THREE.Vector3(0, 0, 0), new THREE.Vector3(x, y, z)];
      const line = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(points),
        new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.38 }),
      );
      orbit.add(line);
    });
    let reducedMotion = window.matchMedia(
      '(prefers-reduced-motion: reduce)',
    ).matches;
    let lastUiUpdate = Number.NEGATIVE_INFINITY;
    let animationFrame = 0;
    const updatePositions = (time: number) => {
      if (time - lastUiUpdate <= 48) return;
      const bounds = stage.getBoundingClientRect();
      const next = nodeMeshes.map((mesh, index) => {
        const projected = mesh.getWorldPosition(new THREE.Vector3()).project(camera);
        return {
          key: harnesses[index]?.key ?? String(index),
          x: (projected.x * 0.5 + 0.5) * bounds.width,
          y: (-projected.y * 0.5 + 0.5) * bounds.height,
        };
      });
      setPositions(next);
      lastUiUpdate = time;
    };
    const resize = () => {
      const { width, height } = stage.getBoundingClientRect();
      if (!width || !height) return;
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.render(scene, camera);
      if (reducedMotion) updatePositions(performance.now());
    };
    const observer = new ResizeObserver(resize);
    observer.observe(stage);
    resize();

    const render = (time: number) => {
      if (!reducedMotion) orbit.rotation.y = time * 0.000075;
      renderer.render(scene, camera);
      updatePositions(time);
      if (!reducedMotion) animationFrame = window.requestAnimationFrame(render);
    };
    const motionPreference = window.matchMedia(
      '(prefers-reduced-motion: reduce)',
    );
    const onMotionPreferenceChange = () => {
      reducedMotion = motionPreference.matches;
      window.cancelAnimationFrame(animationFrame);
      animationFrame = window.requestAnimationFrame(render);
    };
    motionPreference.addEventListener('change', onMotionPreferenceChange);
    animationFrame = window.requestAnimationFrame(render);
    return () => {
      window.cancelAnimationFrame(animationFrame);
      motionPreference.removeEventListener('change', onMotionPreferenceChange);
      observer.disconnect();
      renderer.dispose();
      centerGeometry.dispose();
      centerMaterial.dispose();
      scene.traverse((object: any) => {
        if (object instanceof THREE.Mesh || object instanceof THREE.Line) {
          object.geometry.dispose();
          const material = object.material;
          if (Array.isArray(material)) material.forEach((entry) => entry.dispose());
          else material.dispose();
        }
      });
      renderer.domElement.remove();
    };
  }, [harnesses]);

  const goToHarness = (key: string) => setLocation(`/harness/${encodeURIComponent(key)}`);
  const center = <div className="core-center" aria-label={`${PRODUCT_NAME} core, no data`}>
    <span className="core-center-mark" aria-hidden="true" />
    <span className="health-state"><span className="status-dot status-dot-empty" aria-hidden="true" />No data</span>
  </div>;

  return (
    <div className="core-stage" ref={stageRef} data-testid="stage-zero-core">
      {webglAvailable ? (
        <>
          {center}
          {harnesses.map((harness, index) => {
            const position = positions.find((item) => item.key === harness.key);
            return (
              <button
                key={harness.key}
                type="button"
                className="core-node"
                style={{
                  left: position ? `${position.x}px` : `${50 + Math.cos((index / Math.max(harnesses.length, 1)) * Math.PI * 2) * 28}%`,
                  top: position ? `${position.y}px` : `${50 + Math.sin((index / Math.max(harnesses.length, 1)) * Math.PI * 2) * 28}%`,
                }}
                onClick={() => goToHarness(harness.key)}
                aria-label={`Open ${harness.label} workspace`}
                data-testid={`node-harness-${harness.key}`}
              >
                <span>{harness.label}</span>
                <span className="core-node-status">
                  <span className="status-dot status-dot-empty" aria-hidden="true" />
                  No data
                </span>
              </button>
            );
          })}
        </>
      ) : (
        <div className="core-fallback">
          {center}
          <svg className="core-fallback-links" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            {harnesses.map((harness, index) => {
              const angle = (index / Math.max(harnesses.length, 1)) * Math.PI * 2;
              return <line key={harness.key} x1="50" y1="50" x2={50 + Math.cos(angle) * 36} y2={50 + Math.sin(angle) * 34} stroke="rgba(255,255,255,.32)" strokeWidth=".15" />;
            })}
          </svg>
          {harnesses.map((harness, index) => {
            const angle = (index / Math.max(harnesses.length, 1)) * Math.PI * 2;
            return <button
              className="core-node"
              type="button"
              key={harness.key}
              style={{ left: `${50 + Math.cos(angle) * 36}%`, top: `${50 + Math.sin(angle) * 34}%` }}
              onClick={() => goToHarness(harness.key)}
              data-testid={`node-harness-${harness.key}`}
            >
              <span>{harness.label}</span>
              <span className="core-node-status">
                <span className="status-dot status-dot-empty" aria-hidden="true" />
                No data
              </span>
            </button>;
          })}
        </div>
      )}
      <div className="core-caption">Stage 0 · Advise only</div>
    </div>
  );
}
