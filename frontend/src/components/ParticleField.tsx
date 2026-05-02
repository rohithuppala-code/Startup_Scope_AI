"use client";
import { useEffect, useRef } from "react";
import * as THREE from "three";

interface ParticleFieldProps {
  particleCount?: number;
  speed?: number;
  opacity?: number;
}

export default function ParticleField({
  particleCount = 900,
  speed = 0.15,
  opacity = 0.6,
}: ParticleFieldProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const container = containerRef.current;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(
      60,
      window.innerWidth / window.innerHeight,
      0.1,
      1000
    );
    camera.position.z = 300;

    const renderer = new THREE.WebGLRenderer({
      antialias: false,
      alpha: true,
      powerPreference: "low-power",
    });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    container.appendChild(renderer.domElement);

    // Create particles
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    const colors = new Float32Array(particleCount * 3);
    const sizes = new Float32Array(particleCount);
    const velocities = new Float32Array(particleCount * 3);

    const violetColor = new THREE.Color(0x8b5cf6);
    const cyanColor = new THREE.Color(0x06b6d4);
    const whiteColor = new THREE.Color(0xfafafa);

    for (let i = 0; i < particleCount; i++) {
      // Position: spread in a wide sphere
      positions[i * 3] = (Math.random() - 0.5) * 800;
      positions[i * 3 + 1] = (Math.random() - 0.5) * 600;
      positions[i * 3 + 2] = (Math.random() - 0.5) * 400;

      // Color: violet → cyan → white gradient
      const t = Math.random();
      let color: THREE.Color;
      if (t < 0.4) {
        color = violetColor.clone().lerp(cyanColor, t / 0.4);
      } else if (t < 0.8) {
        color = cyanColor.clone().lerp(whiteColor, (t - 0.4) / 0.4);
      } else {
        color = whiteColor.clone();
      }
      colors[i * 3] = color.r;
      colors[i * 3 + 1] = color.g;
      colors[i * 3 + 2] = color.b;

      // Size: varied
      sizes[i] = Math.random() * 2.5 + 0.5;

      // Velocity: gentle drift
      velocities[i * 3] = (Math.random() - 0.5) * speed;
      velocities[i * 3 + 1] = (Math.random() - 0.5) * speed;
      velocities[i * 3 + 2] = (Math.random() - 0.5) * speed * 0.3;
    }

    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    geometry.setAttribute("size", new THREE.BufferAttribute(sizes, 1));

    const material = new THREE.PointsMaterial({
      size: 2,
      vertexColors: true,
      transparent: true,
      opacity,
      blending: THREE.AdditiveBlending,
      sizeAttenuation: true,
      depthWrite: false,
    });

    const particles = new THREE.Points(geometry, material);
    scene.add(particles);

    // Mouse interaction
    let mouseX = 0;
    let mouseY = 0;
    const onMouseMove = (e: MouseEvent) => {
      mouseX = (e.clientX / window.innerWidth) * 2 - 1;
      mouseY = -(e.clientY / window.innerHeight) * 2 + 1;
    };
    window.addEventListener("mousemove", onMouseMove, { passive: true });

    // Animation
    let animationId: number;
    let time = 0;

    const animate = () => {
      animationId = requestAnimationFrame(animate);
      time += 0.001;

      const posArr = geometry.attributes.position.array as Float32Array;
      for (let i = 0; i < particleCount; i++) {
        posArr[i * 3] += velocities[i * 3] + Math.sin(time + i * 0.01) * 0.02;
        posArr[i * 3 + 1] += velocities[i * 3 + 1] + Math.cos(time + i * 0.01) * 0.02;
        posArr[i * 3 + 2] += velocities[i * 3 + 2];

        // Wrap around boundaries
        if (posArr[i * 3] > 400) posArr[i * 3] = -400;
        if (posArr[i * 3] < -400) posArr[i * 3] = 400;
        if (posArr[i * 3 + 1] > 300) posArr[i * 3 + 1] = -300;
        if (posArr[i * 3 + 1] < -300) posArr[i * 3 + 1] = 300;
        if (posArr[i * 3 + 2] > 200) posArr[i * 3 + 2] = -200;
        if (posArr[i * 3 + 2] < -200) posArr[i * 3 + 2] = 200;
      }
      geometry.attributes.position.needsUpdate = true;

      // Gentle camera response to mouse
      camera.position.x += (mouseX * 20 - camera.position.x) * 0.02;
      camera.position.y += (mouseY * 15 - camera.position.y) * 0.02;
      camera.lookAt(scene.position);

      // Slow rotation
      particles.rotation.y = time * 0.5;
      particles.rotation.x = Math.sin(time * 0.3) * 0.05;

      renderer.render(scene, camera);
    };
    animate();

    // Resize handler
    const onResize = () => {
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    };
    window.addEventListener("resize", onResize, { passive: true });

    // Cleanup
    return () => {
      cancelAnimationFrame(animationId);
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("resize", onResize);
      geometry.dispose();
      material.dispose();
      renderer.dispose();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [particleCount, speed, opacity]);

  return <div ref={containerRef} className="particle-canvas" />;
}
