'use client';

import React from 'react';
import { X, FileText, Network as NetworkIcon } from 'lucide-react';

export type EvidenceItem = {
  evidence_id: string;
  source_type?: string;
  company_name?: string;
  preview?: string;
};

type Props = {
  open: boolean;
  items: EvidenceItem[];
  onClose: () => void;
};

export function EvidenceDrawer({ open, items, onClose }: Props) {
  return (
    <div
      className={`fixed inset-y-0 right-0 z-40 w-[420px] max-w-[90vw] transform transition-transform duration-300 ${
        open ? 'translate-x-0' : 'translate-x-full'
      }`}
      aria-hidden={!open}
    >
      <div className="h-full bg-[#0c0c0e] border-l border-white/10 flex flex-col shadow-2xl">
        <div className="h-12 flex items-center justify-between px-4 border-b border-white/5">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-indigo-400" />
            <span className="text-sm font-medium text-zinc-200">
              Evidence Drawer
              <span className="ml-2 text-xs text-zinc-500">{items.length} items</span>
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded hover:bg-white/5 text-zinc-400"
            aria-label="Close evidence drawer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto app-scrollbar p-4 space-y-3">
          {items.length === 0 && (
            <div className="text-xs text-zinc-500">아직 도착한 근거가 없습니다.</div>
          )}
          {items.map((it) => (
            <div
              key={it.evidence_id}
              className="rounded-lg border border-white/5 bg-black/30 p-3 space-y-1"
            >
              <div className="flex items-center justify-between text-[11px]">
                <span className="font-mono text-indigo-300">{it.evidence_id}</span>
                <span className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-white/5">
                  {it.source_type || 'UNKNOWN'}
                </span>
              </div>
              {it.company_name && (
                <div className="text-xs text-zinc-300 inline-flex items-center gap-1">
                  <NetworkIcon className="w-3 h-3 text-emerald-400" />
                  {it.company_name}
                </div>
              )}
              {it.preview && (
                <p className="text-xs text-zinc-400 leading-relaxed whitespace-pre-wrap">
                  {it.preview}
                </p>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
