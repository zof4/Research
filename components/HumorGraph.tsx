"use client";

import React, { useState, useRef, Suspense, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Copy, Check } from "lucide-react";

interface Point {
  x: number;
  y: number;
  label: string;
  id: string;
}

function GraphContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const svgRef = useRef<SVGSVGElement>(null);

  // Derive points state directly from URL
  const points: Point[] = useMemo(() => {
    const g = searchParams.get("g");
    if (!g) return [];
    try {
      const decoded = JSON.parse(g);
      return Array.isArray(decoded) ? decoded : [];
    } catch (e) {
      console.error("Failed to parse graph data", e);
      return [];
    }
  }, [searchParams]);

  const [modalOpen, setModalOpen] = useState(false);
  const [tempPoint, setTempPoint] = useState<{ x: number; y: number } | null>(null);
  const [labelInput, setLabelInput] = useState("");
  const [copied, setCopied] = useState(false);

  const updatePoints = (newPoints: Point[]) => {
    const params = new URLSearchParams(searchParams.toString());
    if (newPoints.length > 0) {
      params.set("g", JSON.stringify(newPoints));
    } else {
      params.delete("g");
    }
    router.replace(`?${params.toString()}`, { scroll: false });
  };

  const handleSvgClick = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * 100;
    const y = ((e.clientY - rect.top) / rect.height) * 100;

    setTempPoint({ x, y });
    setLabelInput("");
    setModalOpen(true);
  };

  const handleAddPoint = (e: React.FormEvent) => {
    e.preventDefault();
    if (!tempPoint || !labelInput.trim()) return;

    const newPoint: Point = {
      x: tempPoint.x,
      y: tempPoint.y,
      label: labelInput.trim(),
      id: Date.now().toString(),
    };

    updatePoints([...points, newPoint]);
    setModalOpen(false);
    setTempPoint(null);
  };

  const handleShare = () => {
    if (typeof window !== "undefined") {
      navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleRemovePoint = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    updatePoints(points.filter((p) => p.id !== id));
  };

  const handleReset = () => {
      // Clear the query param
      router.replace('?', { scroll: false });
  };

  return (
    <div className="w-full max-w-5xl mx-auto p-4 flex flex-col items-center">
      <h1 className="text-4xl md:text-6xl font-bold text-center mb-4 font-handwriting">Humor Graph</h1>

      <div className="mb-4 flex gap-4">
        <button
          onClick={handleShare}
          className="flex items-center gap-2 px-4 py-2 bg-gray-900 text-white rounded hover:bg-gray-700 transition-colors shadow"
        >
          {copied ? <Check size={16} /> : <Copy size={16} />}
          {copied ? "Copied Link!" : "Share Graph"}
        </button>
        {points.length > 0 && (
          <button
            onClick={handleReset}
            className="px-4 py-2 bg-red-100 text-red-700 rounded hover:bg-red-200 transition-colors shadow text-sm"
          >
            Reset
          </button>
        )}
      </div>

      <div className="relative w-full aspect-[16/9] bg-white rounded-lg shadow-xl overflow-hidden border-2 border-gray-800">
        <svg
          ref={svgRef}
          viewBox="0 0 100 100"
          className="w-full h-full cursor-crosshair select-none"
          onClick={handleSvgClick}
        >
          {/* Arrow Markers */}
          <defs>
            <marker id="arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
              <path d="M0,0 L0,6 L6,3 z" fill="black" />
            </marker>
          </defs>

          {/* Axes */}
          <line x1="10" y1="10" x2="10" y2="90" stroke="black" strokeWidth="0.5" markerEnd="url(#arrow)" />
          <line x1="10" y1="90" x2="95" y2="90" stroke="black" strokeWidth="0.5" markerEnd="url(#arrow)" />

          {/* Axis Labels */}
          <text
            x="5"
            y="50"
            transform="rotate(-90 5,50)"
            textAnchor="middle"
            className="text-[3px] font-bold uppercase tracking-widest"
            style={{ fontFamily: "var(--font-handwriting)" }}
          >
            Common Understanding
          </text>
          <text
            x="50"
            y="96"
            textAnchor="middle"
            className="text-[3px] font-bold uppercase tracking-widest"
            style={{ fontFamily: "var(--font-handwriting)" }}
          >
            Weirdness
          </text>

          {/* The Humor Curve */}
          <path
            d="M 10,15
               C 25,14 30,18 34,25
               C 36,40 38,70 42,78
               C 50,85 70,86 92,84"
            fill="none"
            stroke="black"
            strokeWidth="0.8"
            strokeLinecap="round"
            className="drop-shadow-md"
          />

          {/* Static Labels */}
          <text x="18" y="22" className="text-[2px] font-medium opacity-80 pointer-events-none">
            Normie plateau
          </text>
          <text x="44" y="25" className="text-[2px] font-medium opacity-80 pointer-events-none">
            Cliffs of insanity
          </text>
          <line x1="43" y1="26" x2="38" y2="35" stroke="black" strokeWidth="0.2" className="pointer-events-none" />
          <text x="18" y="12" className="text-[2px] fill-red-600 opacity-70 pointer-events-none">
            TikTok trends
          </text>
          <path
            d="M 16,13 C 20,10 28,10 32,13"
            fill="none"
            stroke="red"
            strokeWidth="0.2"
            opacity="0.5"
            className="pointer-events-none"
          />
          <text x="35" y="11" className="text-[2px] fill-blue-600 opacity-70 pointer-events-none">
            Studio C, SNL
          </text>
          <text x="39" y="38" className="text-[2px] fill-orange-700 opacity-80 pointer-events-none">
            Old Vines
          </text>
          <text x="75" y="55" className="text-[2px] fill-gray-800 pointer-events-none">
            Daniel thrasher
          </text>
          <circle cx="75" cy="58" r="0.8" fill="none" stroke="black" strokeWidth="0.1" className="pointer-events-none" />
          <line x1="75" y1="58.8" x2="75" y2="61" stroke="black" strokeWidth="0.1" className="pointer-events-none" />
          <line x1="75" y1="61" x2="74" y2="63" stroke="black" strokeWidth="0.1" className="pointer-events-none" />
          <line x1="75" y1="61" x2="76" y2="63" stroke="black" strokeWidth="0.1" className="pointer-events-none" />
          <line x1="75" y1="59.5" x2="73.5" y2="59" stroke="black" strokeWidth="0.1" className="pointer-events-none" />
          <line x1="75" y1="59.5" x2="76.5" y2="59" stroke="black" strokeWidth="0.1" className="pointer-events-none" />

          {/* User Points */}
          {points.map((p) => (
            <g key={p.id} className="group cursor-pointer" onClick={(e) => handleRemovePoint(e, p.id)}>
              <circle cx={p.x} cy={p.y} r="1.5" fill="#ef4444" className="transition-all group-hover:r-2" />
              <text
                x={p.x}
                y={p.y - 2.5}
                textAnchor="middle"
                className="text-[2.5px] font-bold fill-black bg-white/50"
                style={{ textShadow: "0px 0px 2px white" }}
              >
                {p.label}
              </text>
              <title>Click to remove</title>
            </g>
          ))}
        </svg>

        {/* Modal Overlay */}
        {modalOpen && (
          <div
            className="absolute inset-0 bg-black/40 flex items-center justify-center z-10"
            onClick={() => setModalOpen(false)}
          >
            <div
              className="bg-white p-6 rounded-lg shadow-xl w-64 md:w-80"
              onClick={(e) => e.stopPropagation()}
            >
              <h3 className="text-lg font-bold mb-4">Who/What is this?</h3>
              <form onSubmit={handleAddPoint}>
                <input
                  autoFocus
                  type="text"
                  value={labelInput}
                  onChange={(e) => setLabelInput(e.target.value)}
                  placeholder="e.g. Me, My Dad, Puns"
                  className="w-full border border-gray-300 rounded px-3 py-2 mb-4 focus:outline-none focus:ring-2 focus:ring-black"
                />
                <div className="flex gap-2 justify-end">
                  <button
                    type="button"
                    onClick={() => setModalOpen(false)}
                    className="px-3 py-1 text-gray-500 hover:text-gray-700"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={!labelInput.trim()}
                    className="px-4 py-2 bg-black text-white rounded hover:bg-gray-800 disabled:opacity-50"
                  >
                    Add Dot
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
      <p className="text-gray-500 text-sm mt-4">Click on the graph to add a point. Click a point to remove it.</p>
    </div>
  );
}

export default function HumorGraph() {
  return (
    <Suspense fallback={<div className="p-10 text-center">Loading Humor Graph...</div>}>
      <GraphContent />
    </Suspense>
  );
}
