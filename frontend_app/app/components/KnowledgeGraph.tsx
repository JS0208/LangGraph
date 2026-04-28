'use client';

import React, { useMemo } from 'react';

type Props = {
  nodes: string[];
  edges: string[];
  highlightNode?: string | null;
};

const ROOT_NODE = '__ROOT__';

export function KnowledgeGraph({ nodes, edges, highlightNode }: Props) {
  const layout = useMemo(() => {
    const width = 360;
    const height = 240;
    const cx = width / 2;
    const cy = height / 2;
    const ringRadius = 90;

    const positions: Record<string, { x: number; y: number }> = {};
    if (nodes.length === 0) {
      return { width, height, positions };
    }
    positions[ROOT_NODE] = { x: cx, y: cy };
    nodes.forEach((name, idx) => {
      const angle = (idx / nodes.length) * Math.PI * 2;
      positions[name] = {
        x: cx + Math.cos(angle) * ringRadius,
        y: cy + Math.sin(angle) * ringRadius,
      };
    });
    return { width, height, positions };
  }, [nodes]);

  if (nodes.length === 0) {
    return (
      <div className="h-32 flex items-center justify-center text-xs text-zinc-500 border border-dashed border-white/5 rounded-lg">
        Knowledge graph가 아직 비어 있습니다.
      </div>
    );
  }

  return (
    <svg
      viewBox={`0 0 ${layout.width} ${layout.height}`}
      className="w-full max-w-md mx-auto"
      role="img"
      aria-label="Knowledge graph live view"
    >
      <defs>
        <radialGradient id="kgRoot" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0%" stopColor="rgba(99,102,241,0.85)" />
          <stop offset="100%" stopColor="rgba(99,102,241,0.1)" />
        </radialGradient>
      </defs>
      {/* edges */}
      {nodes.map((name) => {
        const target = layout.positions[name];
        const root = layout.positions[ROOT_NODE];
        if (!target || !root) return null;
        return (
          <line
            key={`edge-${name}`}
            x1={root.x}
            y1={root.y}
            x2={target.x}
            y2={target.y}
            stroke={highlightNode === name ? 'rgba(16,185,129,0.7)' : 'rgba(99,102,241,0.35)'}
            strokeWidth={highlightNode === name ? 1.4 : 0.8}
          />
        );
      })}
      {/* root */}
      <circle cx={layout.positions[ROOT_NODE]?.x} cy={layout.positions[ROOT_NODE]?.y} r={26} fill="url(#kgRoot)" />
      <text
        x={layout.positions[ROOT_NODE]?.x}
        y={layout.positions[ROOT_NODE]?.y}
        textAnchor="middle"
        dominantBaseline="central"
        className="fill-zinc-100"
        style={{ fontSize: 9, fontWeight: 600 }}
      >
        Query
      </text>
      {/* leaves */}
      {nodes.map((name) => {
        const pos = layout.positions[name];
        if (!pos) return null;
        const isHi = highlightNode === name;
        return (
          <g key={`node-${name}`}>
            <circle
              cx={pos.x}
              cy={pos.y}
              r={14}
              fill={isHi ? 'rgba(16,185,129,0.25)' : 'rgba(99,102,241,0.18)'}
              stroke={isHi ? 'rgba(16,185,129,0.85)' : 'rgba(99,102,241,0.55)'}
              strokeWidth={isHi ? 1.4 : 1}
            />
            <text
              x={pos.x}
              y={pos.y}
              textAnchor="middle"
              dominantBaseline="central"
              className={isHi ? 'fill-emerald-200' : 'fill-indigo-100'}
              style={{ fontSize: 8, fontWeight: 500 }}
            >
              {truncate(name, 6)}
            </text>
          </g>
        );
      })}
      {/* edges legend */}
      {edges.length > 0 && (
        <text
          x={6}
          y={layout.height - 6}
          className="fill-zinc-500"
          style={{ fontSize: 8 }}
        >
          relations: {edges.slice(0, 4).join(', ')}
          {edges.length > 4 ? '…' : ''}
        </text>
      )}
    </svg>
  );
}

function truncate(text: string, maxChars: number) {
  if (text.length <= maxChars) return text;
  return `${text.slice(0, maxChars)}…`;
}
