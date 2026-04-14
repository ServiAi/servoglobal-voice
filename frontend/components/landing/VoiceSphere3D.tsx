'use client';

import React, { useRef, useMemo } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Icosahedron, MeshDistortMaterial } from '@react-three/drei';
import * as THREE from 'three';

// Componente interno de esfera de energía líquida con efecto metaball
function LiquidEnergySphere() {
  const meshRef = useRef<THREE.Mesh>(null);
  const materialRef = useRef<React.ElementRef<typeof MeshDistortMaterial>>(null);
  const { pointer, size, viewport } = useThree();
  
  // Valores suavizados para el movimiento del mouse
  const smoothedMouse = useRef({ x: 0, y: 0 });
  const mouseInfluence = useRef(0);

  useFrame((state) => {
    const time = state.clock.elapsedTime;
    
    // === CÁLCULO DE INFLUENCIA DEL MOUSE ===
    // Convertir posición del pointer a coordenadas 3D
    const mouseX = (pointer.x * viewport.width) / 2;
    const mouseY = (pointer.y * viewport.height) / 2;
    
    // Calcular distancia del mouse al centro de la esfera
    const distanceToCenter = Math.sqrt(mouseX * mouseX + mouseY * mouseY);
    const sphereRadius = 2.2; // Radio visual de la esfera
    const influenceRadius = 4; // Radio de influencia del mouse
    
    // Factor de proximidad (1 cuando está cerca, 0 cuando está lejos)
    const proximityFactor = Math.max(0, 1 - distanceToCenter / influenceRadius);
    
    // Suavizar la influencia del mouse para evitar cambios bruscos
    mouseInfluence.current += (proximityFactor - mouseInfluence.current) * 0.08;
    
    // Suavizar posición del mouse
    smoothedMouse.current.x += (mouseX - smoothedMouse.current.x) * 0.05;
    smoothedMouse.current.y += (mouseY - smoothedMouse.current.y) * 0.05;

    if (meshRef.current) {
      // === MOVIMIENTO ORGÁNICO SIN ROTACIÓN SIMPLE ===
      // Ondulación suave del mesh para efecto de "respiración"
      const breathe = Math.sin(time * 0.3) * 0.02;
      meshRef.current.scale.setScalar(2.2 + breathe);
      
      // Micro-movimiento orgánico basado en funciones seno combinadas
      meshRef.current.position.x = Math.sin(time * 0.4) * 0.05 + Math.sin(time * 0.7) * 0.03;
      meshRef.current.position.y = Math.cos(time * 0.5) * 0.04 + Math.sin(time * 0.3) * 0.02;
      meshRef.current.position.z = Math.sin(time * 0.6) * 0.03;
      
      // Rotación muy sutil y orgánica (no una rotación constante)
      meshRef.current.rotation.x = Math.sin(time * 0.2) * 0.1;
      meshRef.current.rotation.y = Math.cos(time * 0.15) * 0.15;
      meshRef.current.rotation.z = Math.sin(time * 0.25) * 0.08;
    }

    if (materialRef.current) {
      // === DISTORSIÓN TOPOLÓGICA FLUIDA ===
      // Múltiples ondas seno combinadas para efecto viscoso orgánico
      const wave1 = Math.sin(time * 0.4) * 0.15;
      const wave2 = Math.sin(time * 0.7 + 1.5) * 0.1;
      const wave3 = Math.sin(time * 1.1 + 3.0) * 0.08;
      const wave4 = Math.cos(time * 0.5 + 0.5) * 0.12;
      
      // Combinar ondas para distorsión orgánica
      const baseDistort = 0.35 + wave1 + wave2 + wave3 + wave4;
      
      // Aumentar distorsión cuando el mouse está cerca
      const mouseBoost = mouseInfluence.current * 0.25;
      (materialRef.current as any).distort = Math.min(0.8, Math.max(0.2, baseDistort + mouseBoost));
      
      // === VELOCIDAD DINÁMICA ===
      // Velocidad base con variación orgánica
      const baseSpeed = 2.5 + Math.sin(time * 0.3) * 0.5;
      // Aumentar velocidad con proximidad del mouse
      const speedBoost = mouseInfluence.current * 2;
      (materialRef.current as any).speed = baseSpeed + speedBoost;
    }
  });

  return (
    <Icosahedron args={[1, 64]} ref={meshRef}>
      <MeshDistortMaterial
        ref={materialRef}
        color="#8B5CF6"
        attach="material"
        distort={0.4}
        speed={2.5}
        roughness={0.12}
        metalness={0.95}
        envMapIntensity={1.2}
      />
    </Icosahedron>
  );
}

// Componente de partículas internas para el efecto del núcleo con interactividad del mouse
function InnerCoreParticles() {
  const particlesRef = useRef<THREE.Points>(null);
  const materialRef = useRef<THREE.PointsMaterial>(null);
  const { pointer, viewport } = useThree();
  const particleCount = 200;
  
  // Valores suavizados para el mouse
  const mouseInfluence = useRef(0);

  // Guardar posiciones originales para el efecto de onda
  const { positions, colors, originalPositions } = useMemo(() => {
    const positions = new Float32Array(particleCount * 3);
    const originalPositions = new Float32Array(particleCount * 3);
    const colors = new Float32Array(particleCount * 3);
    
    for (let i = 0; i < particleCount; i++) {
      // Distribuir partículas en una esfera interior
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      const radius = Math.random() * 1.5;
      
      const x = radius * Math.sin(phi) * Math.cos(theta);
      const y = radius * Math.sin(phi) * Math.sin(theta);
      const z = radius * Math.cos(phi);
      
      positions[i * 3] = x;
      positions[i * 3 + 1] = y;
      positions[i * 3 + 2] = z;
      
      // Guardar posiciones originales
      originalPositions[i * 3] = x;
      originalPositions[i * 3 + 1] = y;
      originalPositions[i * 3 + 2] = z;
      
      // Colores violeta/púrpura variados
      colors[i * 3] = 0.5 + Math.random() * 0.3;     // R
      colors[i * 3 + 1] = 0.3 + Math.random() * 0.2; // G
      colors[i * 3 + 2] = 0.9 + Math.random() * 0.1; // B
    }
    
    return { positions, colors, originalPositions };
  }, []);

  useFrame((state) => {
    const time = state.clock.elapsedTime;
    
    // === CÁLCULO DE INFLUENCIA DEL MOUSE ===
    const mouseX = (pointer.x * viewport.width) / 2;
    const mouseY = (pointer.y * viewport.height) / 2;
    const distanceToCenter = Math.sqrt(mouseX * mouseX + mouseY * mouseY);
    const influenceRadius = 4;
    const proximityFactor = Math.max(0, 1 - distanceToCenter / influenceRadius);
    
    // Suavizar influencia del mouse
    mouseInfluence.current += (proximityFactor - mouseInfluence.current) * 0.1;
    
    if (particlesRef.current) {
      // === ROTACIÓN AUMENTADA CON MOUSE ===
      const baseRotationSpeed = 0.1;
      const boostedRotationSpeed = baseRotationSpeed + mouseInfluence.current * 0.5;
      particlesRef.current.rotation.y = time * boostedRotationSpeed;
      particlesRef.current.rotation.x = Math.sin(time * 0.2) * 0.2 + mouseInfluence.current * 0.3;
      particlesRef.current.rotation.z = Math.cos(time * 0.15) * mouseInfluence.current * 0.2;
      
      // === EFECTO DE ONDA EN PARTÍCULAS ===
      const geometry = particlesRef.current.geometry;
      const positionAttribute = geometry.attributes.position;
      
      if (positionAttribute) {
        for (let i = 0; i < particleCount; i++) {
          const ox = originalPositions[i * 3];
          const oy = originalPositions[i * 3 + 1];
          const oz = originalPositions[i * 3 + 2];
          
          // Factor de expansión basado en proximidad del mouse
          const expansionFactor = 1 + mouseInfluence.current * 0.4;
          
          // Onda pulsante que se intensifica con el mouse
          const waveIntensity = 0.05 + mouseInfluence.current * 0.15;
          const particlePhase = i * 0.1; // Fase única por partícula
          const wave = Math.sin(time * 2 + particlePhase) * waveIntensity;
          
          // Aplicar expansión + onda
          positionAttribute.setXYZ(
            i,
            ox * expansionFactor + ox * wave,
            oy * expansionFactor + oy * wave,
            oz * expansionFactor + oz * wave
          );
        }
        positionAttribute.needsUpdate = true;
      }
    }
    
    // === TAMAÑO Y OPACIDAD DINÁMICOS ===
    if (materialRef.current) {
      materialRef.current.size = 0.03 + mouseInfluence.current * 0.04;
      materialRef.current.opacity = 0.6 + mouseInfluence.current * 0.3;
    }
  });

  return (
    <points ref={particlesRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={particleCount}
          args={[positions, 3]}
        />
        <bufferAttribute
          attach="attributes-color"
          count={particleCount}
          args={[colors, 3]}
        />
      </bufferGeometry>
      <pointsMaterial
        ref={materialRef}
        size={0.03}
        vertexColors
        transparent
        opacity={0.6}
        sizeAttenuation
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

// Anillos de energía orbitando
function EnergyRings() {
  const ring1Ref = useRef<THREE.Mesh>(null);
  const ring2Ref = useRef<THREE.Mesh>(null);
  const ring3Ref = useRef<THREE.Mesh>(null);

  useFrame((state) => {
    const time = state.clock.elapsedTime;
    
    if (ring1Ref.current) {
      ring1Ref.current.rotation.x = time * 0.3;
      ring1Ref.current.rotation.y = time * 0.2;
    }
    if (ring2Ref.current) {
      ring2Ref.current.rotation.x = time * 0.25 + Math.PI / 3;
      ring2Ref.current.rotation.z = time * 0.15;
    }
    if (ring3Ref.current) {
      ring3Ref.current.rotation.y = time * 0.35;
      ring3Ref.current.rotation.z = time * 0.2 + Math.PI / 2;
    }
  });

  return (
    <group>
      <mesh ref={ring1Ref}>
        <torusGeometry args={[2.6, 0.015, 16, 100]} />
        <meshBasicMaterial color="#a78bfa" transparent opacity={0.4} />
      </mesh>
      <mesh ref={ring2Ref}>
        <torusGeometry args={[2.8, 0.01, 16, 100]} />
        <meshBasicMaterial color="#c4b5fd" transparent opacity={0.3} />
      </mesh>
      <mesh ref={ring3Ref}>
        <torusGeometry args={[3.0, 0.008, 16, 100]} />
        <meshBasicMaterial color="#8B5CF6" transparent opacity={0.25} />
      </mesh>
    </group>
  );
}

export function VoiceSphere3D() {
  return (
    <div className="w-full h-[300px] sm:h-[400px] flex items-center justify-center relative">
      <Canvas 
        className="bg-transparent" 
        camera={{ position: [0, 0, 6], fov: 45 }}
        dpr={[1, 2]}
      >
        {/* Iluminación ambiental fuerte */}
        <ambientLight intensity={0.8} />
        
        {/* SpotLight principal para resaltar relieves de distorsión */}
        <spotLight 
          position={[5, 5, 5]} 
          angle={0.3} 
          penumbra={1} 
          intensity={2}
          color="#ffffff"
          castShadow
        />
        
        {/* Luz secundaria para contraluz dramático */}
        <spotLight 
          position={[-5, -3, -5]} 
          angle={0.4} 
          penumbra={0.8} 
          intensity={1.2}
          color="#a78bfa"
        />
        
        {/* Luz puntual para brillo violeta */}
        <pointLight position={[0, 3, 3]} intensity={1.5} color="#8B5CF6" />
        <pointLight position={[-3, -2, 2]} intensity={0.8} color="#c4b5fd" />
        
        {/* Luz de relleno suave */}
        <pointLight position={[0, -5, 0]} intensity={0.5} color="#6d28d9" />
        
        {/* Componentes de la esfera */}
        <InnerCoreParticles />
        <LiquidEnergySphere />
        <EnergyRings />
      </Canvas>
      
      {/* Efecto glow de fondo */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[250px] h-[250px] bg-violet-500/40 blur-[100px] rounded-full pointer-events-none" />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[150px] h-[150px] bg-purple-400/30 blur-[50px] rounded-full pointer-events-none" />
    </div>
  );
}
