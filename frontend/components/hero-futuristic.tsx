'use client';

import { Canvas, extend, useFrame, useThree } from '@react-three/fiber';
import { useTexture, shaderMaterial, useAspect, Html } from '@react-three/drei';
import { useRef, useState, useEffect, useMemo, Suspense } from 'react';
import * as THREE from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';

// Usamos la imagen local para asegurar carga
const TEXTUREMAP = '/voice-sphere.png';
const DEPTHMAP = '/hero-futuristic-2.webp'; 

// --- SHADERS (GLSL Estable) ---

const SceneShader = {
  uniforms: {
    uTime: { value: 0 },
    uMouse: { value: new THREE.Vector2(0, 0) },
    uTexture: { value: null },
    uDepth: { value: null },
    uOpacity: { value: 1.0 }, // Opacidad inicial 1.0 para asegurar visibilidad
    uResolution: { value: new THREE.Vector2(1, 1) },
    uColor: { value: new THREE.Color(1.0, 0.0, 0.0) }
  },
  vertexShader: `
    varying vec2 vUv;
    void main() {
      vUv = uv;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }
  `,
  fragmentShader: `
    uniform float uTime;
    uniform vec2 uMouse;
    uniform sampler2D uTexture;
    uniform sampler2D uDepth;
    uniform float uOpacity;
    uniform vec3 uColor;
    varying vec2 vUv;

    // Pseudo-random noise
    float randomNoise(vec2 co){
        return fract(sin(dot(co.xy ,vec2(12.9898,78.233))) * 43758.5453);
    }

    void main() {
      vec2 uv = vUv;
      
      // 1. Depth & Parallax
      vec4 depthMap = texture2D(uDepth, uv);
      float depthVal = depthMap.r; // 0..1
      vec2 parallax = uMouse * depthVal * 0.015;
      vec2 distortedUv = uv + parallax;
      
      // 2. Main Texture
      vec4 texColor = texture2D(uTexture, distortedUv);
      
      // 3. Dot Pattern (Efecto de Puntos Tecnológicos)
      vec2 tiling = vec2(120.0);
      vec2 gridUv = fract(distortedUv * tiling) - 0.5; 
      vec2 gridId = floor(distortedUv * tiling);
      
      // Brillo aleatorio para cada punto
      float brightness = randomNoise(gridId);
      
      // Forma del punto (circular)
      float dist = length(gridUv);
      float dotMask = smoothstep(0.5, 0.45, dist) * brightness;
      
      // 4. Sweep Effect (Barrido de Escaneo basado en profundidad)
      float uProgress = sin(uTime * 0.5) * 0.5 + 0.5;
      float flow = 1.0 - smoothstep(0.0, 0.02, abs(depthVal - uProgress));
      
      // 5. Máscara Roja (Solo brilla donde pasa el escáner)
      vec3 mask = vec3(dotMask) * flow * vec3(10.0, 0.0, 0.0);
      
      // 6. Mezcla Final
      // Sumamos la máscara roja a la imagen original
      vec3 finalColor = texColor.rgb + mask;
      
      // 7. Make backgrounds transparent (white, red, AND dark edges)
      // Calculate luminance (brightness) of the pixel
      float luminance = dot(texColor.rgb, vec3(0.299, 0.587, 0.114));
      
      // Check if pixel is predominantly red (background color)
      // Red background: high R relative to G and B
      float redDominance = texColor.r - max(texColor.g, texColor.b);
      float isRedBg = smoothstep(0.05, 0.15, redDominance);
      
      // Check if pixel is dark red/maroon (low luminance but red-ish)
      float isDarkRed = step(0.5, texColor.r) * step(texColor.g, 0.3) * step(texColor.b, 0.3) * step(luminance, 0.4);
      
      // Check if pixel is white/light (high luminance)
      float isWhiteBg = smoothstep(0.50, 0.65, luminance);
      
      // Combine: transparent if white, red, or dark red background
      float bgMask = max(max(isRedBg, isWhiteBg), isDarkRed);
      float alpha = 1.0 - bgMask;
      
      gl_FragColor = vec4(finalColor, uOpacity * alpha);
    }
  `
};

// --- COMPONENTS ---

const Effects = () => {
  const { gl, scene, camera, size } = useThree();
  const composer = useRef<EffectComposer>();

  useEffect(() => {
    const renderScene = new RenderPass(scene, camera);
    
    // Bloom Pass para el brillo de los puntos rojos
    const bloomPass = new UnrealBloomPass(
      new THREE.Vector2(size.width, size.height),
      1.0, // Strength
      0.1, // Radius
      0.1 // Threshold
    );
    
    const effectComposer = new EffectComposer(gl);
    effectComposer.addPass(renderScene);
    effectComposer.addPass(bloomPass); 
    
    composer.current = effectComposer;
    return () => {
        composer.current = undefined;
    };
  }, [gl, scene, camera, size]);

  useFrame(() => {
    if (composer.current) {
        composer.current.render();
    }
  }, 1);

  return null;
};

const Scene = () => {
  const [textureMap, depthMap] = useTexture([TEXTUREMAP, DEPTHMAP]);
  const materialRef = useRef<THREE.ShaderMaterial>(null);
  const { viewport } = useThree();
  const [visible, setVisible] = useState(false);
  
  // Aspect Scaling
  const scale = useAspect(
    1100, // Source width
    1100, // Source height
    1
  );

  useEffect(() => {
    if (textureMap && depthMap) setVisible(true);
  }, [textureMap, depthMap]);

  useFrame((state) => {
    if (materialRef.current) {
        materialRef.current.uniforms.uTime.value = state.clock.getElapsedTime();
        // Auto-movement: Gentle circular motion
        const time = state.clock.getElapsedTime();
        materialRef.current.uniforms.uMouse.value.set(
          Math.sin(time * 0.5) * 4.0, // X movement (4x intensity)
          Math.cos(time * 0.3) * 4.0  // Y movement (4x intensity)
        ); 
        
        // Mantenemos opacidad al 1.0 para evitar parpadeos
        materialRef.current.uniforms.uOpacity.value = 1.0;
        
        materialRef.current.transparent = true;
    }
  });

  return (
    <mesh scale={[scale[0] * 0.95, scale[1] * 0.95, scale[2] * 0.95]}>
      <planeGeometry args={[1, 1]} />
      <shaderMaterial
        ref={materialRef}
        uniforms={{
          ...SceneShader.uniforms,
          uTexture: { value: textureMap },
          uDepth: { value: depthMap }
        }}
        vertexShader={SceneShader.vertexShader}
        fragmentShader={SceneShader.fragmentShader}
        transparent
      />
    </mesh>
  );
};

export const HeroFuturistic = () => {
  return (
    <div className="w-full h-full min-h-[500px] relative flex items-center justify-center">
      <Canvas
        camera={{ position: [0, 0, 2], fov: 50 }}
        style={{ background: 'transparent' }}
        gl={{ antialias: false }} 
        onCreated={() => console.log('Canvas Created')}
      >
        <Suspense fallback={<Html center><div className="text-white text-center">Loading 3D Scene...</div></Html>}>
          <Scene />
          {/* Effects removed - bloom was causing visible rectangular halo */}
        </Suspense>
      </Canvas>
    </div>
  );
};

export default HeroFuturistic;