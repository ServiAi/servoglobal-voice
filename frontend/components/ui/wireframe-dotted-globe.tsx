'use client';

import { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import type { Feature, FeatureCollection, Geometry } from 'geojson';

interface RotatingEarthProps {
  width?: number;
  height?: number;
  className?: string;
  autoRotate?: boolean;
  rotationSpeed?: number;
  dotColor?: string;
  glowColor?: string;
  backgroundColor?: string;
  showControlsHint?: boolean;
}

interface DotData {
  lng: number;
  lat: number;
  seed: number;
}

type LandFeature = Feature<Geometry>;
type LandCollection = FeatureCollection<Geometry>;

const WORLD_DATA_URL = '/data/ne_110m_land.json';
const FALLBACK_WORLD_DATA_URL =
  'https://raw.githubusercontent.com/martynafford/natural-earth-geojson/refs/heads/master/110m/physical/ne_110m_land.json';

const DOT_SPACING = 18;
const STEP_SIZE = DOT_SPACING * 0.08;
const RED = '#ff0033';
const WHITE_SCAN = 'rgba(255, 255, 255, 0.22)';
const WHITE_SCAN_SOFT = 'rgba(255, 255, 255, 0.14)';
const BLACK_CORE = 'rgba(4, 0, 3, 0.92)';
const TAU = Math.PI * 2;
const COLOMBIA_MARKER = {
  lng: -74.08,
  lat: 4.65,
  color: '#ff0033',
  glow: 'rgba(255, 0, 51, 0.95)',
};

function fract(value: number) {
  return value - Math.floor(value);
}

function randomNoise(x: number, y: number) {
  return fract(Math.sin(x * 12.9898 + y * 78.233) * 43758.5453);
}

function smoothstep(edge0: number, edge1: number, x: number) {
  const t = Math.max(0, Math.min(1, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function normalizeLng(lng: number) {
  return ((lng + 180) % 360) / 360;
}

async function fetchWorldData(): Promise<LandCollection> {
  const localResponse = await fetch(WORLD_DATA_URL);

  if (localResponse.ok) {
    return (await localResponse.json()) as LandCollection;
  }

  // Keep this fallback until the Natural Earth file is copied to frontend/public/data.
  const fallbackResponse = await fetch(FALLBACK_WORLD_DATA_URL);

  if (!fallbackResponse.ok) {
    throw new Error('Unable to load world land data.');
  }

  return (await fallbackResponse.json()) as LandCollection;
}

function generateDotsInFeature(feature: LandFeature, dotSpacing = DOT_SPACING): DotData[] {
  const dots: DotData[] = [];
  const [[minLng, minLat], [maxLng, maxLat]] = d3.geoBounds(feature);
  const step = dotSpacing === DOT_SPACING ? STEP_SIZE : dotSpacing * 0.08;
  const latStart = Math.ceil(minLat / step) * step;
  const lngStart = Math.ceil(minLng / step) * step;

  for (let lat = latStart; lat <= maxLat; lat += step) {
    if (lat < -86 || lat > 86) {
      continue;
    }

    const rowOffset = Math.abs(Math.round(lat / step)) % 2 === 0 ? 0 : step * 0.5;

    for (let lng = lngStart + rowOffset; lng <= maxLng; lng += step) {
      const jitterLng = (randomNoise(lng * 0.31, lat * 0.19) - 0.5) * step * 0.25;
      const jitterLat = (randomNoise(lng * 0.11, lat * 0.37) - 0.5) * step * 0.25;
      const candidate: [number, number] = [lng + jitterLng, lat + jitterLat];

      if (d3.geoContains(feature, candidate)) {
        dots.push({
          lng: candidate[0],
          lat: candidate[1],
          seed: randomNoise(candidate[0] * 0.17, candidate[1] * 0.23),
        });
      }
    }
  }

  return dots;
}

function generateLandDots(world: LandCollection) {
  const dots: DotData[] = [];

  for (const feature of world.features) {
    dots.push(...generateDotsInFeature(feature));
  }

  return dots;
}

function generateFallbackDots(): DotData[] {
  const dots: DotData[] = [];
  const latStep = 5.8;
  const lngStep = 7.4;

  for (let lat = -68; lat <= 72; lat += latStep) {
    const rowOffset = Math.abs(Math.round(lat / latStep)) % 2 === 0 ? 0 : lngStep * 0.5;

    for (let lng = -180 + rowOffset; lng <= 180; lng += lngStep) {
      const latitudeWeight = 1 - Math.abs(lat) / 92;
      const band =
        Math.sin((lng + lat * 1.7) * 0.045) +
        Math.cos((lng * 0.55 - lat * 2.1) * 0.038) +
        randomNoise(lng * 0.04, lat * 0.07);

      if (band > 0.45 && latitudeWeight > 0.22) {
        dots.push({
          lng: lng + (randomNoise(lng * 0.13, lat * 0.17) - 0.5) * 2.2,
          lat: lat + (randomNoise(lng * 0.19, lat * 0.11) - 0.5) * 1.8,
          seed: randomNoise(lng * 0.29, lat * 0.31),
        });
      }
    }
  }

  return dots;
}

const FALLBACK_DOTS = generateFallbackDots();

function drawCirclePath(context: CanvasRenderingContext2D, cx: number, cy: number, radius: number) {
  context.beginPath();
  context.arc(cx, cy, radius, 0, TAU);
}

export default function RotatingEarth({
  width = 780,
  height = 780,
  className = '',
  autoRotate = true,
  rotationSpeed = 0.35,
  dotColor = RED,
  glowColor = 'rgba(255, 0, 51, 0.85)',
  backgroundColor = 'transparent',
  showControlsHint = false,
}: RotatingEarthProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const dotsRef = useRef<DotData[]>(FALLBACK_DOTS);
  const worldRef = useRef<LandCollection | null>(null);
  const frameRef = useRef<number | null>(null);
  const rotationRef = useRef<[number, number, number]>([-28, -12, 0]);
  const dragRef = useRef({
    active: false,
    pointerId: -1,
    x: 0,
    y: 0,
    rotation: [-28, -12, 0] as [number, number, number],
  });
  const [isDarkMode, setIsDarkMode] = useState(true);
  const [isReady, setIsReady] = useState(false);
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    const root = document.documentElement;
    const updateTheme = () => setIsDarkMode(root.classList.contains('dark'));
    const observer = new MutationObserver(updateTheme);

    updateTheme();
    observer.observe(root, { attributes: true, attributeFilter: ['class'] });

    return () => {
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    fetchWorldData()
      .then((world) => {
        if (cancelled) {
          return;
        }

        worldRef.current = world;
        window.setTimeout(() => {
          if (cancelled) {
            return;
          }

          dotsRef.current = generateLandDots(world);
          setIsReady(true);
        }, 0);
      })
      .catch(() => {
        if (!cancelled) {
          setHasError(true);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;

    if (!canvas) {
      return;
    }

    const context = canvas.getContext('2d', { alpha: true });

    if (!context) {
      return;
    }

    let mounted = true;
    const reducedMotionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    let prefersReducedMotion = reducedMotionQuery.matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const size = Math.min(width, height);
    const radius = size * 0.405;
    const cx = width / 2;
    const cy = height / 2;
    const mapDotColor = dotColor;
    const mapGlowColor = glowColor;
    const graticuleColor = isDarkMode ? 'rgba(255, 255, 255, 0.16)' : 'rgba(0, 0, 0, 0.14)';
    const landStrokeColor = isDarkMode ? 'rgba(255, 255, 255, 0.28)' : 'rgba(0, 0, 0, 0.88)';
    const scanColor = isDarkMode ? WHITE_SCAN : 'rgba(0, 0, 0, 0.16)';
    const scanEdgeColor = isDarkMode ? 'rgba(255, 255, 255, 0)' : 'rgba(0, 0, 0, 0)';
    const scanArcColor = isDarkMode ? WHITE_SCAN_SOFT : 'rgba(0, 0, 0, 0.12)';

    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    context.setTransform(dpr, 0, 0, dpr, 0, 0);

    const projection = d3
      .geoOrthographic()
      .translate([cx, cy])
      .scale(radius)
      .clipAngle(90)
      .precision(0.6);
    const geoPath = d3.geoPath(projection, context);
    const graticule = d3.geoGraticule10();

    const drawSphereBase = () => {
      context.clearRect(0, 0, width, height);

      if (backgroundColor !== 'transparent') {
        context.fillStyle = backgroundColor;
        context.fillRect(0, 0, width, height);
      }

      const core = context.createRadialGradient(cx - radius * 0.28, cy - radius * 0.32, radius * 0.08, cx, cy, radius * 1.04);

      if (isDarkMode) {
        core.addColorStop(0, 'rgba(18, 18, 22, 0.95)');
        core.addColorStop(0.5, BLACK_CORE);
        core.addColorStop(1, 'rgba(0, 0, 0, 0.98)');
      } else {
        core.addColorStop(0, 'rgba(255, 255, 255, 1)');
        core.addColorStop(0.55, 'rgba(255, 255, 255, 0.98)');
        core.addColorStop(1, 'rgba(255, 255, 255, 0.96)');
      }

      drawCirclePath(context, cx, cy, radius);
      context.fillStyle = core;
      context.fill();

      if (isDarkMode) {
        const innerShade = context.createRadialGradient(
          cx + radius * 0.34,
          cy + radius * 0.3,
          radius * 0.12,
          cx + radius * 0.2,
          cy + radius * 0.2,
          radius * 1.12,
        );
        innerShade.addColorStop(0, 'rgba(0, 0, 0, 0)');
        innerShade.addColorStop(0.62, 'rgba(0, 0, 0, 0.22)');
        innerShade.addColorStop(1, 'rgba(0, 0, 0, 0.68)');
        drawCirclePath(context, cx, cy, radius);
        context.fillStyle = innerShade;
        context.fill();
      }

    };

    const drawGeoLayers = (time: number) => {
      const world = worldRef.current;

      context.save();
      drawCirclePath(context, cx, cy, radius);
      context.clip();

      context.beginPath();
      geoPath(graticule);
      context.strokeStyle = graticuleColor;
      context.lineWidth = 0.55;
      context.stroke();

      if (world) {
        context.beginPath();
        geoPath(world);
        context.strokeStyle = landStrokeColor;
        context.lineWidth = 0.72;
        context.stroke();
      }

      const sweepPosition = Math.sin(time * 0.75) * 0.5 + 0.5;
      const sweepX = cx - radius + radius * 2 * sweepPosition;
      const scan = context.createLinearGradient(sweepX - radius * 0.16, cy, sweepX + radius * 0.16, cy);
      scan.addColorStop(0, scanEdgeColor);
      scan.addColorStop(0.5, scanColor);
      scan.addColorStop(1, scanEdgeColor);
      context.fillStyle = scan;
      drawCirclePath(context, cx, cy, radius);
      context.fill();

      for (const dot of dotsRef.current) {
        const visible = d3.geoDistance([dot.lng, dot.lat], [-rotationRef.current[0], -rotationRef.current[1]]) <= Math.PI / 2;

        if (!visible) {
          continue;
        }

        const point = projection([dot.lng, dot.lat]);

        if (!point) {
          continue;
        }

        const [x, y] = point;
        const nx = (x - cx) / radius;
        const ny = (y - cy) / radius;
        const radialDistance = Math.sqrt(nx * nx + ny * ny);
        const depth = Math.sqrt(Math.max(0, 1 - radialDistance * radialDistance));
        const limbFade = smoothstep(0, 0.16, 1 - radialDistance);
        const lighting = clamp(0.38 + depth * 0.74 - nx * 0.1 - ny * 0.08, 0, 1);
        const normalizedLng = normalizeLng(dot.lng + rotationRef.current[0]);
        const sweep = 1 - smoothstep(0, 0.08, Math.abs(normalizedLng - sweepPosition));
        const pulse = 0.55 + 0.45 * Math.sin(time * 2.2 + dot.seed * TAU);
        const shimmer = randomNoise(dot.lng * 0.02 + time * 0.21, dot.lat * 0.03 + dot.seed);
        const baseVisibility = limbFade * lighting;
        const finalAlpha = clamp(baseVisibility * (0.3 + dot.seed * 0.35 + sweep * 0.65 + shimmer * 0.12) * pulse, 0, 0.94);

        if (finalAlpha < 0.035) {
          continue;
        }

        const finalRadius = (0.78 + depth * 0.68) * (0.75 + sweep * 1.4 + dot.seed * 0.4);

        context.save();
        context.globalAlpha = finalAlpha;
        context.shadowBlur = 8 + sweep * 18;
        context.shadowColor = mapGlowColor;
        drawCirclePath(context, x, y, finalRadius);
        context.fillStyle = mapDotColor;
        context.fill();
        context.restore();
      }

      const colombiaVisible =
        d3.geoDistance([COLOMBIA_MARKER.lng, COLOMBIA_MARKER.lat], [-rotationRef.current[0], -rotationRef.current[1]]) <=
        Math.PI / 2;

      if (colombiaVisible) {
        const markerPoint = projection([COLOMBIA_MARKER.lng, COLOMBIA_MARKER.lat]);

        if (markerPoint) {
          const [markerX, markerY] = markerPoint;
          const markerNx = (markerX - cx) / radius;
          const markerNy = (markerY - cy) / radius;
          const markerDistance = Math.sqrt(markerNx * markerNx + markerNy * markerNy);
          const markerDepth = Math.sqrt(Math.max(0, 1 - markerDistance * markerDistance));
          const markerFade = smoothstep(0, 0.18, 1 - markerDistance);
          const markerPulse = 0.72 + 0.28 * Math.sin(time * 3.1);
          const markerRadius = (2.45 + markerDepth * 1.15) * markerPulse;

          context.save();
          context.globalAlpha = clamp(markerFade * (0.78 + markerDepth * 0.32), 0, 1);
          context.shadowBlur = 22;
          context.shadowColor = COLOMBIA_MARKER.glow;
          drawCirclePath(context, markerX, markerY, markerRadius);
          context.fillStyle = COLOMBIA_MARKER.color;
          context.fill();

          context.globalAlpha *= 0.32;
          context.shadowBlur = 30;
          drawCirclePath(context, markerX, markerY, markerRadius * 2.35);
          context.strokeStyle = COLOMBIA_MARKER.glow;
          context.lineWidth = 1.1;
          context.stroke();
          context.restore();
        }
      }

      const sweepArcAngle = time * 0.28;
      context.save();
      context.globalCompositeOperation = 'screen';
      context.strokeStyle = scanArcColor;
      context.lineWidth = 1;
      context.beginPath();
      context.ellipse(cx, cy, radius * 0.98, radius * 0.23, sweepArcAngle, Math.PI * 0.08, Math.PI * 1.02);
      context.stroke();
      context.restore();

      const highlight = context.createRadialGradient(
        cx - radius * 0.36,
        cy - radius * 0.38,
        radius * 0.04,
        cx - radius * 0.18,
        cy - radius * 0.2,
        radius * 0.72,
      );
      if (isDarkMode) {
        highlight.addColorStop(0, 'rgba(255, 255, 255, 0.14)');
        highlight.addColorStop(0.42, 'rgba(255, 255, 255, 0.05)');
        highlight.addColorStop(1, 'rgba(255, 255, 255, 0)');
      } else {
        highlight.addColorStop(0, 'rgba(255, 255, 255, 0.45)');
        highlight.addColorStop(0.42, 'rgba(255, 255, 255, 0.14)');
        highlight.addColorStop(1, 'rgba(255, 255, 255, 0)');
      }
      drawCirclePath(context, cx, cy, radius);
      context.fillStyle = highlight;
      context.fill();

      context.restore();
    };

    const render = (now: number) => {
      if (!mounted) {
        return;
      }

      const time = now / 1000;
      const activeSpeed = prefersReducedMotion ? rotationSpeed * 0.08 : rotationSpeed;

      if (autoRotate && !dragRef.current.active) {
        rotationRef.current = [
          rotationRef.current[0] + activeSpeed,
          rotationRef.current[1],
          rotationRef.current[2],
        ];
      }

      projection.rotate(rotationRef.current);
      drawSphereBase();
      drawGeoLayers(time);
      frameRef.current = window.requestAnimationFrame(render);
    };

    const handleMotionPreferenceChange = (event: MediaQueryListEvent) => {
      prefersReducedMotion = event.matches;
    };

    const handlePointerDown = (event: PointerEvent) => {
      dragRef.current = {
        active: true,
        pointerId: event.pointerId,
        x: event.clientX,
        y: event.clientY,
        rotation: [...rotationRef.current],
      };
      canvas.setPointerCapture(event.pointerId);
    };

    const handlePointerMove = (event: PointerEvent) => {
      if (!dragRef.current.active || event.pointerId !== dragRef.current.pointerId) {
        return;
      }

      const dx = event.clientX - dragRef.current.x;
      const dy = event.clientY - dragRef.current.y;
      rotationRef.current = [
        dragRef.current.rotation[0] + dx * 0.22,
        clamp(dragRef.current.rotation[1] - dy * 0.18, -55, 55),
        0,
      ];
    };

    const handlePointerUp = (event: PointerEvent) => {
      if (event.pointerId !== dragRef.current.pointerId) {
        return;
      }

      dragRef.current.active = false;
      canvas.releasePointerCapture(event.pointerId);
    };

    reducedMotionQuery.addEventListener('change', handleMotionPreferenceChange);
    canvas.addEventListener('pointerdown', handlePointerDown);
    canvas.addEventListener('pointermove', handlePointerMove);
    canvas.addEventListener('pointerup', handlePointerUp);
    canvas.addEventListener('pointercancel', handlePointerUp);
    frameRef.current = window.requestAnimationFrame(render);

    return () => {
      mounted = false;

      if (frameRef.current !== null) {
        window.cancelAnimationFrame(frameRef.current);
      }

      reducedMotionQuery.removeEventListener('change', handleMotionPreferenceChange);
      canvas.removeEventListener('pointerdown', handlePointerDown);
      canvas.removeEventListener('pointermove', handlePointerMove);
      canvas.removeEventListener('pointerup', handlePointerUp);
      canvas.removeEventListener('pointercancel', handlePointerUp);
    };
  }, [autoRotate, backgroundColor, dotColor, glowColor, hasError, height, isDarkMode, rotationSpeed, width]);

  return (
    <div className={`relative flex h-full min-h-[500px] w-full items-center justify-center ${className}`}>
      <canvas
        ref={canvasRef}
        aria-label="Planeta digital giratorio con cobertura global de Servi-IA"
        className="block h-full w-full touch-none select-none"
        role="img"
      />
      {!isReady && !hasError ? (
        <div className="pointer-events-none absolute inset-0 rounded-full bg-[radial-gradient(circle_at_center,rgba(184,0,245,0.12),transparent_64%)] opacity-60" />
      ) : null}
      {hasError ? (
        <div className="pointer-events-none absolute h-[62%] w-[62%] rounded-full border border-[#ff0033]/20 shadow-[0_0_80px_rgba(255,0,51,0.14)]" />
      ) : null}
      {showControlsHint ? (
        <div className="pointer-events-none absolute bottom-8 rounded-full border border-[#ff0033]/20 bg-black/40 px-3 py-1 text-xs text-[#ff8aa0] backdrop-blur">
          Drag to rotate
        </div>
      ) : null}
    </div>
  );
}
