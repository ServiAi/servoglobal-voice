"use client";

import { useEffect, useRef, useState } from "react";
import type React from "react";
import { ArrowRight, Link, Zap } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface TimelineItem {
  id: number;
  title: string;
  date: string;
  content: string;
  category: string;
  icon: LucideIcon;
  relatedIds: number[];
  status: "completed" | "in-progress" | "pending";
  energy: number;
}

interface RadialOrbitalTimelineProps {
  timelineData: TimelineItem[];
  className?: string;
}

const statusLabels = {
  completed: "READY",
  "in-progress": "ACTIVE",
  pending: "NEXT",
} as const;

export default function RadialOrbitalTimeline({ timelineData, className }: RadialOrbitalTimelineProps) {
  const [expandedItems, setExpandedItems] = useState<Record<number, boolean>>({});
  const [rotationAngle, setRotationAngle] = useState(0);
  const [autoRotate, setAutoRotate] = useState(true);
  const [pulseEffect, setPulseEffect] = useState<Record<number, boolean>>({});
  const [activeNodeId, setActiveNodeId] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const orbitRef = useRef<HTMLDivElement>(null);

  const getRelatedItems = (itemId: number): number[] => {
    const currentItem = timelineData.find((item) => item.id === itemId);
    return currentItem ? currentItem.relatedIds : [];
  };

  const centerViewOnNode = (nodeId: number) => {
    const nodeIndex = timelineData.findIndex((item) => item.id === nodeId);
    const totalNodes = timelineData.length;
    const targetAngle = (nodeIndex / totalNodes) * 360;
    setRotationAngle(270 - targetAngle);
  };

  const toggleItem = (id: number) => {
    setExpandedItems((prev) => {
      const nextState: Record<number, boolean> = {};
      Object.keys(prev).forEach((key) => {
        const numericKey = Number(key);
        nextState[numericKey] = numericKey === id ? !prev[numericKey] : false;
      });

      nextState[id] = !prev[id];

      if (!prev[id]) {
        setActiveNodeId(id);
        setAutoRotate(false);
        setPulseEffect(Object.fromEntries(getRelatedItems(id).map((relatedId) => [relatedId, true])));
        centerViewOnNode(id);
      } else {
        setActiveNodeId(null);
        setAutoRotate(true);
        setPulseEffect({});
      }

      return nextState;
    });
  };

  const handleContainerClick = (event: React.MouseEvent<HTMLDivElement>) => {
    if (event.target === containerRef.current || event.target === orbitRef.current) {
      setExpandedItems({});
      setActiveNodeId(null);
      setPulseEffect({});
      setAutoRotate(true);
    }
  };

  useEffect(() => {
    if (!autoRotate) {
      return;
    }

    const rotationTimer = window.setInterval(() => {
      setRotationAngle((prev) => Number(((prev + 0.28) % 360).toFixed(3)));
    }, 50);

    return () => {
      window.clearInterval(rotationTimer);
    };
  }, [autoRotate]);

  const calculateNodePosition = (index: number, total: number) => {
    const angle = ((index / total) * 360 + rotationAngle) % 360;
    const radius = 178;
    const radian = (angle * Math.PI) / 180;
    const x = radius * Math.cos(radian);
    const y = radius * Math.sin(radian);
    const zIndex = Math.round(100 + 50 * Math.cos(radian));
    const opacity = Math.max(0.46, Math.min(1, 0.46 + 0.54 * ((1 + Math.sin(radian)) / 2)));

    return { x, y, zIndex, opacity };
  };

  const isRelatedToActive = (itemId: number): boolean => {
    if (!activeNodeId) {
      return false;
    }

    return getRelatedItems(activeNodeId).includes(itemId);
  };

  const getStatusStyles = (status: TimelineItem["status"]): string => {
    switch (status) {
      case "completed":
        return "border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-300/60 dark:bg-emerald-500/15 dark:text-emerald-100";
      case "in-progress":
        return "border-violet-300 bg-violet-50 text-violet-700 dark:border-violet-300/70 dark:bg-violet-500/20 dark:text-violet-100";
      case "pending":
        return "border-fuchsia-300 bg-fuchsia-50 text-fuchsia-700 dark:border-fuchsia-300/50 dark:bg-fuchsia-500/15 dark:text-fuchsia-100";
      default:
        return "border-zinc-200 bg-zinc-50 text-zinc-700 dark:border-white/20 dark:bg-white/10 dark:text-white/80";
    }
  };

  return (
    <div
      ref={containerRef}
      onClick={handleContainerClick}
      className={cn("relative w-full overflow-hidden rounded-[1.5rem]", className)}
    >
      <div className="hidden min-h-[520px] items-center justify-center lg:flex">
        <div
          ref={orbitRef}
          className="relative flex h-[500px] w-full max-w-4xl items-center justify-center"
          style={{ perspective: "1000px" }}
        >
          <div className="absolute z-10 flex size-20 items-center justify-center rounded-full bg-gradient-to-br from-violet-600 via-fuchsia-500 to-[#ff0033] shadow-[0_0_80px_rgba(168,85,247,0.42)]">
            <div className="absolute size-28 rounded-full border border-violet-500/25 animate-ping opacity-60 dark:border-violet-300/25" />
            <div className="absolute size-36 rounded-full border border-fuchsia-500/15 animate-pulse dark:border-fuchsia-300/15" />
            <div className="size-9 rounded-full bg-white/85 shadow-[0_0_28px_rgba(255,255,255,0.45)]" />
          </div>

          <div className="absolute size-[22rem] rounded-full border border-violet-500/20 dark:border-violet-300/15" />
          <div className="absolute size-[30rem] rounded-full border border-fuchsia-500/15 dark:border-fuchsia-300/10" />
          <div className="absolute h-px w-[30rem] bg-gradient-to-r from-transparent via-violet-500/25 to-transparent dark:via-violet-300/20" />
          <div className="absolute h-[30rem] w-px bg-gradient-to-b from-transparent via-fuchsia-500/25 to-transparent dark:via-fuchsia-300/20" />

          {timelineData.map((item, index) => {
            const position = calculateNodePosition(index, timelineData.length);
            const isExpanded = expandedItems[item.id];
            const isRelated = isRelatedToActive(item.id);
            const isPulsing = pulseEffect[item.id];
            const Icon = item.icon;

            return (
              <div
                key={item.id}
                className="absolute cursor-pointer transition-all duration-700"
                style={{
                  transform: `translate(${position.x}px, ${position.y}px)`,
                  zIndex: isExpanded ? 200 : position.zIndex,
                  opacity: isExpanded ? 1 : position.opacity,
                }}
                onClick={(event) => {
                  event.stopPropagation();
                  toggleItem(item.id);
                }}
              >
                <div
                  className={cn("absolute rounded-full -inset-1", isPulsing && "animate-pulse duration-1000")}
                  style={{
                    background:
                      "radial-gradient(circle, rgba(217,70,239,0.22) 0%, rgba(124,58,237,0.12) 45%, rgba(255,0,51,0) 72%)",
                    width: `${item.energy * 0.5 + 46}px`,
                    height: `${item.energy * 0.5 + 46}px`,
                    left: `-${(item.energy * 0.5 + 6) / 2}px`,
                    top: `-${(item.energy * 0.5 + 6) / 2}px`,
                  }}
                />

                <div
                  className={cn(
                    "flex size-12 items-center justify-center rounded-full border-2 transition-all duration-300",
                    isExpanded
                      ? "scale-150 border-violet-200 bg-white text-zinc-950 shadow-lg shadow-fuchsia-500/30 dark:border-white dark:bg-white dark:shadow-fuchsia-500/40"
                      : isRelated
                        ? "border-fuchsia-400 bg-fuchsia-50 text-zinc-950 animate-pulse dark:border-fuchsia-300 dark:bg-white/70"
                        : "border-zinc-300 bg-white text-zinc-950 shadow-sm dark:border-white/35 dark:bg-zinc-950 dark:text-white",
                  )}
                >
                  <Icon size={18} />
                </div>

                <div
                  className={cn(
                    "absolute left-1/2 top-14 -translate-x-1/2 whitespace-nowrap text-xs font-semibold transition-all duration-300",
                    isExpanded ? "scale-125 text-zinc-950 dark:text-white" : "text-zinc-600 dark:text-white/70",
                  )}
                >
                  {item.title}
                </div>

                {isExpanded && (
                  <Card className="absolute left-1/2 top-24 w-72 -translate-x-1/2 overflow-visible border-zinc-200 bg-white text-zinc-950 shadow-xl shadow-violet-500/10 backdrop-blur-lg dark:border-white/20 dark:bg-zinc-950/95 dark:text-white dark:shadow-fuchsia-500/15">
                    <div className="absolute -top-3 left-1/2 h-3 w-px -translate-x-1/2 bg-zinc-300 dark:bg-white/40" />
                    <CardHeader className="pb-2">
                      <div className="flex items-center justify-between gap-3">
                        <Badge className={cn("px-2 text-[10px]", getStatusStyles(item.status))}>
                          {statusLabels[item.status]}
                        </Badge>
                        <span className="text-xs font-mono text-zinc-500 dark:text-white/50">{item.date}</span>
                      </div>
                      <CardTitle className="mt-2 text-sm text-zinc-950 dark:text-white">{item.title}</CardTitle>
                    </CardHeader>
                    <CardContent className="text-xs leading-relaxed text-zinc-600 dark:text-white/75">
                      <p>{item.content}</p>

                      <div className="mt-4 border-t border-zinc-200 pt-3 dark:border-white/10">
                        <div className="mb-1 flex items-center justify-between text-xs">
                          <span className="flex items-center">
                            <Zap size={10} className="mr-1 text-fuchsia-600 dark:text-fuchsia-200" />
                            {item.category}
                          </span>
                          <span className="font-mono">{item.energy}%</span>
                        </div>
                        <div className="h-1 w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-white/10">
                          <div
                            className="h-full bg-gradient-to-r from-violet-500 via-fuchsia-500 to-[#ff0033]"
                            style={{ width: `${item.energy}%` }}
                          />
                        </div>
                      </div>

                      {item.relatedIds.length > 0 && (
                        <div className="mt-4 border-t border-zinc-200 pt-3 dark:border-white/10">
                          <div className="mb-2 flex items-center">
                            <Link size={10} className="mr-1 text-zinc-500 dark:text-white/70" />
                            <h4 className="text-xs font-medium uppercase text-zinc-500 dark:text-white/70">Conexiones</h4>
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {item.relatedIds.map((relatedId) => {
                              const relatedItem = timelineData.find((candidate) => candidate.id === relatedId);
                              return (
                                <Button
                                  key={relatedId}
                                  variant="outline"
                                  size="sm"
                                  className="h-6 rounded-none border-zinc-200 bg-white px-2 py-0 text-xs text-zinc-700 hover:bg-violet-50 hover:text-violet-700 dark:border-white/20 dark:bg-transparent dark:text-white/80 dark:hover:bg-white/10 dark:hover:text-white"
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    toggleItem(relatedId);
                                  }}
                                >
                                  {relatedItem?.title}
                                  <ArrowRight size={8} className="ml-1 text-zinc-500 dark:text-white/60" />
                                </Button>
                              );
                            })}
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="grid gap-3 lg:hidden">
        {timelineData.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => toggleItem(item.id)}
              className="rounded-2xl border border-zinc-200 bg-zinc-50 p-4 text-left transition-colors hover:border-violet-300/60 dark:border-white/10 dark:bg-white/[0.03] dark:hover:border-violet-300/40"
            >
              <div className="flex items-start gap-3">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-100">
                  <Icon className="size-5" />
                </span>
                <span>
                  <span className="block font-semibold text-zinc-900 dark:text-white">{item.title}</span>
                  <span className="mt-1 block text-sm leading-relaxed text-zinc-600 dark:text-white/65">{item.content}</span>
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
