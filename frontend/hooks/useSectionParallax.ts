'use client';

import { RefObject, useEffect, useState } from 'react';
import {
  MotionValue,
  useReducedMotion,
  useScroll,
  useTransform,
} from 'framer-motion';

export type ParallaxProfile = {
  bg: number;
  mid: number;
  fg: number;
  fade?: boolean;
  scale?: [number, number];
};

export const heroDesktop: ParallaxProfile = {
  bg: 180,
  mid: 96,
  fg: 52,
  fade: true,
  scale: [1, 0.94],
};

export const sectionDesktop: ParallaxProfile = {
  bg: 120,
  mid: 54,
  fg: 26,
  fade: false,
  scale: [1, 1],
};

export const mobileReduced: ParallaxProfile = {
  bg: 44,
  mid: 22,
  fg: 10,
  fade: true,
  scale: [1, 0.985],
};

export const reducedMotionOff: ParallaxProfile = {
  bg: 0,
  mid: 0,
  fg: 0,
  fade: false,
  scale: [1, 1],
};

type ParallaxLayer = 'background' | 'content' | 'accent';
type ScrollOffset = Exclude<Parameters<typeof useScroll>[0], undefined>['offset'];
const defaultOffset: ScrollOffset = ['start end', 'end start'];

type UseSectionParallaxOptions = {
  target: RefObject<HTMLElement | null>;
  offset?: ScrollOffset;
  desktopProfile?: ParallaxProfile;
  mobileProfile?: ParallaxProfile;
  reducedMotionProfile?: ParallaxProfile;
  mobileQuery?: string;
};

function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia(query);

    const update = () => setMatches(mediaQuery.matches);
    update();

    mediaQuery.addEventListener('change', update);
    return () => mediaQuery.removeEventListener('change', update);
  }, [query]);

  return matches;
}

function getLayerDistance(profile: ParallaxProfile, layer: ParallaxLayer) {
  switch (layer) {
    case 'background':
      return profile.bg;
    case 'content':
      return profile.mid;
    case 'accent':
      return profile.fg;
  }
}

export function useSectionParallax({
  target,
  offset = defaultOffset,
  desktopProfile = sectionDesktop,
  mobileProfile = mobileReduced,
  reducedMotionProfile = reducedMotionOff,
  mobileQuery = '(max-width: 767px)',
}: UseSectionParallaxOptions) {
  const prefersReducedMotion = useReducedMotion();
  const isMobile = useMediaQuery(mobileQuery);

  const { scrollYProgress } = useScroll({
    target: target as RefObject<HTMLElement>,
    offset,
  });

  const profile = prefersReducedMotion
    ? reducedMotionProfile
    : isMobile
      ? mobileProfile
      : desktopProfile;

  return {
    isMobile,
    profile,
    prefersReducedMotion,
    scrollYProgress,
  };
}

export function useParallaxLayer(
  scrollYProgress: MotionValue<number>,
  profile: ParallaxProfile,
  layer: ParallaxLayer,
  direction: 1 | -1 = 1,
) {
  const distance = getLayerDistance(profile, layer) * direction;
  return useTransform(scrollYProgress, [0, 1], [distance, -distance]);
}

export function useParallaxOpacity(
  scrollYProgress: MotionValue<number>,
  profile: ParallaxProfile,
) {
  return useTransform(
    scrollYProgress,
    [0, 0.7, 1],
    profile.fade ? [1, 1, 0.24] : [1, 1, 1],
  );
}

export function useParallaxScale(
  scrollYProgress: MotionValue<number>,
  profile: ParallaxProfile,
) {
  const scaleRange = profile.scale ?? [1, 1];
  return useTransform(scrollYProgress, [0, 1], scaleRange);
}
