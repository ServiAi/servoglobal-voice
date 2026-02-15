import { useState, useEffect, useCallback, useRef } from 'react';
import { UltravoxSession, UltravoxSessionStatus } from 'ultravox-client';

export type DemoState = 'idle' | 'connecting' | 'connected' | 'ended';

export function useUltravox() {
  const [status, setStatus] = useState<UltravoxSessionStatus>(UltravoxSessionStatus.DISCONNECTED);
  const [demoState, setDemoState] = useState<DemoState>('idle');
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [volumeLevels, setVolumeLevels] = useState<number[]>(new Array(5).fill(10));
  const sessionRef = useRef<UltravoxSession | null>(null); 

  // Initialize session
  useEffect(() => {
    const session = new UltravoxSession();
    sessionRef.current = session;

    const handleStatusChange = (newStatus: UltravoxSessionStatus) => {
      setStatus(newStatus);
      
      switch (newStatus) {
        case UltravoxSessionStatus.CONNECTING:
          setDemoState('connecting');
          break;
        case UltravoxSessionStatus.IDLE:
        case UltravoxSessionStatus.LISTENING:
        case UltravoxSessionStatus.THINKING:
        case UltravoxSessionStatus.SPEAKING:
          setDemoState('connected');
          break;
        case UltravoxSessionStatus.DISCONNECTED:
          // differentiating between initial idle and ended requires context, 
          // but for simple flow we can handle 'ended' manually on hangup
          if (demoState !== 'idle') {
             setDemoState('ended');
          }
          break;
      }
      
      setIsSpeaking(newStatus === UltravoxSessionStatus.SPEAKING);
    };

    session.addEventListener('status', (e: any) => handleStatusChange(session.status));

    // Cleanup
    return () => {
      session.leaveCall();
    };
  }, []);

  // Mock volume visualizer effect when speaking
  useEffect(() => {
    if (!isSpeaking) {
      setVolumeLevels(new Array(5).fill(10));
      return;
    }

    const interval = setInterval(() => {
      const newLevels = new Array(5).fill(0).map(() => Math.random() * 40 + 10);
      setVolumeLevels(newLevels);
    }, 100);

    return () => clearInterval(interval);
  }, [isSpeaking]);

  const startCall = useCallback(async (context?: Record<string, any>) => {
    if (!sessionRef.current) return;
    
    // TODO: url de fast api
    let joinUrl = ''; // Initialize joinUrl as mutable

    try {
      // Fetch the Join URL from our backend
      const response = await fetch('http://localhost:8000/api/v1/calls', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            template_context: context || {}  
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to get join URL');
      }

      const data = await response.json();
      joinUrl = data.joinUrl; // Assign to the mutable joinUrl

      if (!joinUrl) {
          throw new Error('Received empty joinUrl from backend');
      }

      // Join the call
      await sessionRef.current.joinCall(joinUrl);
    } catch (error) {
      console.error('Failed to join call:', error);
      setDemoState('ended');
    }
  }, []);

  const endCall = useCallback(() => {
    if (sessionRef.current) {
      sessionRef.current.leaveCall();
    }
    setDemoState('ended');
  }, []);

  const resetDemo = useCallback(() => {
    if (sessionRef.current) {
        // Ensure clean state
        if(sessionRef.current.status !== UltravoxSessionStatus.DISCONNECTED) {
            sessionRef.current.leaveCall();
        }
    }
    setDemoState('idle');
    setStatus(UltravoxSessionStatus.DISCONNECTED);
  }, []);

  return {
    status,
    demoState,
    isSpeaking,
    volumeLevels, // Exposed for visualizer
    startCall,
    endCall,
    resetDemo
  };
}
