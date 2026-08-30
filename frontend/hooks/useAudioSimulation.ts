import { useState, useRef, useEffect, useCallback } from 'react';

export type DemoState = 'idle' | 'connecting' | 'connected' | 'ended';

export function useAudioSimulation() {
  const [demoState, setDemoState] = useState<DemoState>('idle');
  const [volumeLevels, setVolumeLevels] = useState<number[]>(new Array(5).fill(10));
  const [duration, setDuration] = useState(0);
  
  // Timer for call 
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (demoState === 'connected') {
      interval = setInterval(() => {
        setDuration(prev => prev + 1);
      }, 1000);
    } else {
      setDuration(0);
    }
    return () => clearInterval(interval);
  }, [demoState]);

  // Audio wave simulation
  useEffect(() => {
    let animationFrame: number;
    
    const animateWaves = () => {
      if (demoState === 'connected') {
        const newLevels = volumeLevels.map(() => Math.max(10, Math.random() * 100)); // Simulate voice activity
        setVolumeLevels(newLevels);
      } else {
        setVolumeLevels(new Array(5).fill(10));
      }
      // Slow down the update rate for visual comfort
      setTimeout(() => {
        animationFrame = requestAnimationFrame(animateWaves);
      }, 100);
    };

    if (demoState === 'connected') {
      animateWaves();
    }

    return () => cancelAnimationFrame(animationFrame);
  }, [demoState]); // Removed volumeLevels from deps to avoid infinite loop logic if strict

  const startCall = useCallback(() => {
    setDemoState('connecting');
    setTimeout(() => {
      setDemoState('connected');
    }, 2000); // 2s simulated connection time
  }, []);

  const endCall = useCallback(() => {
    setDemoState('ended');
  }, []);

  const resetDemo = useCallback(() => {
    setDemoState('idle');
    setDuration(0);
  }, []);

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return {
    demoState,
    volumeLevels,
    duration: formatDuration(duration),
    startCall,
    endCall,
    resetDemo
  };
}
