'use client';

import React, { useState, useEffect, useRef } from 'react';
import {
  Play, Square, Activity, ShieldAlert, BrainCircuit, Network,
  Terminal, CheckCircle2, Loader2,
  Database, Zap, AlertTriangle, TrendingUp, Info, AlertCircle,
  PauseCircle, BookOpen
} from 'lucide-react';
import { EvidenceDrawer, type EvidenceItem } from './components/EvidenceDrawer';
import { KnowledgeGraph } from './components/KnowledgeGraph';

type JsonRecord = Record<string, unknown>;

type LogEntry = {
  id: string;
  time: string;
  node: string;
  title: string;
  data: unknown;
};

type FinanceData = JsonRecord & {
  debt_ratio?: number | string;
  insight?: string;
  source?: string;
};

type RiskData = JsonRecord & {
  risk_points?: string[];
  severity?: string;
};

type RetrievalContext = JsonRecord & {
  mode?: string;
  graph_results?: {
    nodes?: string[];
    edges?: string[];
  };
};

type OrchestratorMessage = {
  content?: string;
};

type OrchestratorData = JsonRecord & {
  summary?: string;
  messages?: OrchestratorMessage[];
  consensus_reached?: boolean;
  knowledge_graph_nodes?: unknown[];
};

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null;
}

const NODE_TITLES: Record<string, string> = {
  system: 'System Activity',
  stream_start: 'Stream Started',
  stream_resume: 'Stream Resumed',
  intent_classifier: 'Intent Classifier',
  retrieve_context: 'Hybrid Retrieval',
  finance_analyst: 'Financial Quantitative Analysis',
  risk_compliance: 'Regulatory & Compliance Risk',
  critic: 'Critic Verification',
  reflector: 'Reflexion (re-plan)',
  orchestrator: 'Final Consensus & Graph Synthesis',
  generate_final_report: 'Final Report',
};

export default function GraphRAGDashboard() {
  const [query, setQuery] = useState("카카오의 2024년 3분기 실적과, 자회사 카카오게임즈의 규제 리스크가 본사에 미치는 영향을 분석해.");
  const [status, setStatus] = useState<'idle' | 'analyzing' | 'complete' | 'error'>('idle');
  const [logs, setLogs] = useState<LogEntry[]>([]);

  const [finance, setFinance] = useState<FinanceData | null>(null);
  const [risk, setRisk] = useState<RiskData | null>(null);
  const [retrievedContext, setRetrievedContext] = useState<RetrievalContext | null>(null);
  const [orchestrator, setOrchestrator] = useState<OrchestratorData | null>(null);

  const [threadId, setThreadId] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [activeNode, setActiveNode] = useState<string | null>(null);
  const [disagreementScore, setDisagreementScore] = useState<number | null>(null);
  const [intentLabel, setIntentLabel] = useState<string | null>(null);
  const [streamingText, setStreamingText] = useState<string>('');

  const logContainerRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  useEffect(() => {
    const container = logContainerRef.current;
    if (!container) return;
    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    if (distanceFromBottom < 80) {
      container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
    }
  }, [logs]);

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  const getNodeTitle = (node: string) => NODE_TITLES[node] || 'Agent Activity';

  const closeStream = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  };

  const handleStop = async () => {
    if (threadId) {
      try {
        await fetch(`${API_BASE}/api/v1/analyze/interrupt/${threadId}?reason=user_stop`, {
          method: 'POST',
        });
      } catch (err) {
        console.warn('interrupt request failed', err);
      }
    }
    closeStream();
    setStatus('idle');
  };

  const resetState = () => {
    setLogs([]);
    setFinance(null);
    setRisk(null);
    setRetrievedContext(null);
    setOrchestrator(null);
    setEvidence([]);
    setDisagreementScore(null);
    setIntentLabel(null);
    setActiveNode(null);
    setStreamingText('');
  };

  const handleV2Event = (payload: JsonRecord) => {
    const type = String(payload.type || '');
    if (type === 'evidence_added') {
      const item: EvidenceItem = {
        evidence_id: String(payload.evidence_id || ''),
        source_type: payload.source_type ? String(payload.source_type) : undefined,
        company_name: payload.company_name ? String(payload.company_name) : undefined,
        preview: payload.preview ? String(payload.preview) : undefined,
      };
      if (item.evidence_id) {
        setEvidence(prev => [...prev, item]);
      }
      return true;
    }
    if (type === 'node_start' && payload.node) {
      setActiveNode(String(payload.node));
      if (payload.node === 'orchestrator' || payload.node === 'generate_final_report') {
        setStreamingText('');
      }
      return true;
    }
    if (type === 'token' && typeof payload.delta === 'string') {
      setStreamingText(prev => prev + payload.delta);
      return true;
    }
    if (type === 'node_end' && payload.node) {
      const summary = isRecord(payload.summary) ? payload.summary : null;
      if (summary?.disagreement_score !== undefined) {
        const value = Number(summary.disagreement_score);
        if (!Number.isNaN(value)) setDisagreementScore(value);
      }
      if (summary?.intent !== undefined && summary.intent) {
        setIntentLabel(String(summary.intent));
      }
      return true;
    }
    if (type === 'interrupt_requested') {
      setStatus('idle');
      return true;
    }
    if (type === 'done') {
      setStatus('complete');
      return true;
    }
    if (type === 'error') {
      setStatus('error');
      return true;
    }
    if (type === 'ping' || type === 'stream_start' || type === 'stream_resume') {
      return true;
    }
    return false;
  };

  const handleV1Update = (payload: JsonRecord) => {
    const [node, value] = Object.entries(payload)[0] || ["system", payload];
    setLogs(prev => [...prev, {
      id: crypto.randomUUID(),
      time: new Date().toLocaleTimeString(),
      node: String(node),
      title: getNodeTitle(String(node)),
      data: value,
    }]);

    if (node === "retrieve_context" && isRecord(value) && isRecord(value.retrieved_context)) {
      setRetrievedContext(value.retrieved_context as RetrievalContext);
    } else if (node === "finance_analyst" && isRecord(value)) {
      const financeValue = isRecord(value.finance_metrics) ? value.finance_metrics : value;
      setFinance(financeValue as FinanceData);
    } else if (node === "risk_compliance") {
      setRisk(isRecord(value) ? (value as RiskData) : { raw: value });
    } else if (node === "orchestrator") {
      setOrchestrator(isRecord(value) ? (value as OrchestratorData) : { raw: value });
    } else if (node === "intent_classifier" && isRecord(value)) {
      if (value.intent) setIntentLabel(String(value.intent));
    }
  };

  const startAnalysis = async () => {
    if (!query.trim() || status === 'analyzing') return;

    setStatus('analyzing');
    resetState();
    setThreadId(null);

    try {
      const res = await fetch(`${API_BASE}/api/v1/analyze/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
      });

      if (!res.ok) {
        if (res.status === 400) {
          setStatus('error');
          setLogs([{
            id: crypto.randomUUID(),
            time: new Date().toLocaleTimeString(),
            node: 'system',
            title: 'Request Blocked',
            data: { message: '입력이 가드레일에 의해 차단되었습니다 (prompt injection).' },
          }]);
          return;
        }
        throw new Error('서버 요청 실패');
      }

      const { thread_id } = await res.json();
      setThreadId(thread_id);

      setLogs(prev => [...prev, {
        id: crypto.randomUUID(),
        time: new Date().toLocaleTimeString(),
        node: 'system',
        title: 'Connection Established',
        data: { message: `Thread ID: ${thread_id} 할당됨. 스트리밍 대기 중...` }
      }]);

      eventSourceRef.current = new EventSource(`${API_BASE}/api/v1/analyze/stream/${thread_id}`);

      eventSourceRef.current.onmessage = (ev) => {
        if (ev.data === "[DONE]") {
          setStatus(prev => (prev === 'analyzing' ? 'complete' : prev));
          closeStream();
          return;
        }
        try {
          const payload = JSON.parse(ev.data) as JsonRecord;
          if (typeof payload.type === 'string') {
            const handled = handleV2Event(payload);
            if (handled) return;
          }
          handleV1Update(payload);
        } catch (e) {
          console.error("Parse Error:", e);
        }
      };

      eventSourceRef.current.onerror = () => {
        setStatus(prev => (prev === 'complete' ? prev : 'error'));
        setLogs(prev => [...prev, {
          id: crypto.randomUUID(),
          time: new Date().toLocaleTimeString(),
          node: 'system',
          title: 'Connection Error',
          data: { message: "SSE 연결이 끊어졌거나 서버 응답이 없습니다." }
        }]);
        closeStream();
      };

    } catch (error) {
      setStatus('error');
      const message = error instanceof Error ? error.message : '알 수 없는 오류';
      setLogs([{
        id: crypto.randomUUID(),
        time: new Date().toLocaleTimeString(),
        node: 'system',
        title: 'Initialization Failed',
        data: { error: message }
      }]);
    }
  };

  const renderFinanceUI = () => {
    if (!finance) return null;
    if ('debt_ratio' in finance && 'insight' in finance) {
      const ratio = Number(finance.debt_ratio);
      const isWarning = ratio >= 150;
      return (
        <div className="space-y-4 animate-in fade-in zoom-in-95">
          <div className="grid grid-cols-2 gap-3">
            <div className={`border rounded-xl p-4 flex flex-col justify-center relative overflow-hidden ${isWarning ? 'bg-rose-950/20 border-rose-900/50' : 'bg-emerald-950/20 border-emerald-900/50'}`}>
              <div className="absolute -right-2 -bottom-2 opacity-10"><TrendingUp className="w-16 h-16" /></div>
              <p className="text-[10px] uppercase tracking-widest text-zinc-500 mb-1 font-semibold z-10">Debt Ratio</p>
              <div className="flex items-baseline gap-1 z-10">
                <span className={`text-3xl font-bold tracking-tighter ${isWarning ? 'text-rose-400' : 'text-emerald-400'}`}>{ratio.toFixed(1)}</span>
                <span className="text-zinc-500 font-medium">%</span>
              </div>
            </div>
            <div className="bg-black/30 border border-white/5 rounded-xl p-4 flex flex-col justify-between">
              <div>
                <p className="text-[10px] uppercase tracking-widest text-zinc-500 mb-1 font-semibold">Data Source</p>
                <div className="inline-flex items-center gap-1.5 px-2 py-1 rounded bg-zinc-800/80 border border-zinc-700 text-xs font-mono text-zinc-300">
                  <Database className="w-3 h-3 text-indigo-400" />{finance.source || 'unknown'}
                </div>
              </div>
            </div>
          </div>
          <div className="bg-blue-950/20 border border-blue-900/40 rounded-xl p-4 relative">
            <div className="flex gap-3">
              <Info className="w-5 h-5 text-blue-400 shrink-0 mt-0.5" />
              <div>
                <p className="text-[10px] uppercase tracking-widest text-blue-400/80 mb-1.5 font-semibold">Analytical Insight</p>
                <p className="text-sm text-blue-100/90 leading-relaxed">{finance.insight}</p>
              </div>
            </div>
          </div>
        </div>
      );
    }
    return (
      <div className="text-zinc-400 bg-black/20 p-3 rounded border border-white/5 overflow-x-auto text-xs font-mono">
        <pre>{JSON.stringify(finance, null, 2)}</pre>
      </div>
    );
  };

  const getOrchestratorSummary = () => {
    if (!orchestrator) return null;
    if (typeof orchestrator.summary === 'string') return orchestrator.summary;
    if (Array.isArray(orchestrator.messages) && orchestrator.messages.length > 0) {
      return orchestrator.messages[orchestrator.messages.length - 1].content;
    }
    return "요약 데이터를 추출할 수 없습니다.";
  };

  const isConsensusReached = orchestrator?.consensus_reached === true;
  const graphNodes = Array.isArray(retrievedContext?.graph_results?.nodes)
    ? retrievedContext.graph_results.nodes
    : [];
  const graphEdges = Array.isArray(retrievedContext?.graph_results?.edges)
    ? retrievedContext.graph_results.edges
    : [];

  return (
    <div className="min-h-screen bg-[#09090b] text-zinc-300 font-sans flex flex-col selection:bg-indigo-500/30">
      <nav className="h-14 border-b border-white/5 bg-[#09090b]/80 backdrop-blur-md flex items-center justify-between px-6 z-50 sticky top-0">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded bg-indigo-500 flex items-center justify-center shadow-[0_0_15px_rgba(99,102,241,0.4)]">
            <Network className="w-4 h-4 text-white" />
          </div>
          <span className="font-semibold text-zinc-100 tracking-tight text-sm">FinGraph Insight</span>
        </div>
        <div className="flex items-center gap-4 text-xs font-mono">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            className="inline-flex items-center gap-1 px-2 py-1 rounded border border-white/10 hover:bg-white/5 text-zinc-300"
          >
            <BookOpen className="w-3.5 h-3.5" />
            Evidence ({evidence.length})
          </button>
          {intentLabel && (
            <span className="px-2 py-1 rounded bg-indigo-500/10 border border-indigo-500/20 text-indigo-300">
              intent: {intentLabel}
            </span>
          )}
          {disagreementScore !== null && (
            <span className={`px-2 py-1 rounded border ${
              disagreementScore <= 0.2
                ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300'
                : 'bg-amber-500/10 border-amber-500/20 text-amber-300'
            }`}>
              critic: {disagreementScore.toFixed(2)}
            </span>
          )}
          <div className="flex items-center gap-2">
            <Zap className="w-3.5 h-3.5 text-zinc-500" />
            <span className="text-zinc-400">Status: <span className={status === 'analyzing' ? 'text-amber-400' : status === 'error' ? 'text-red-400' : 'text-emerald-400'}>{status.toUpperCase()}</span></span>
          </div>
        </div>
      </nav>

      <main className="flex-1 flex overflow-hidden p-6 gap-6 max-w-[1800px] mx-auto w-full">
        <section className="w-[45%] flex flex-col gap-4">
          <div className="bg-[#121214] border border-white/10 rounded-xl p-1.5 focus-within:border-indigo-500/50 focus-within:ring-1 focus-within:ring-indigo-500/50 transition-all shadow-lg">
            <div className="flex items-start">
              <div className="pt-3 pl-3">
                <Terminal className="w-4 h-4 text-indigo-400" />
              </div>
              <textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="분석할 기업 및 리스크 요인을 입력하세요..."
                className="w-full bg-transparent border-none text-sm text-zinc-200 px-3 py-2.5 focus:outline-none resize-none h-20 placeholder:text-zinc-600"
                disabled={status === 'analyzing'}
              />
            </div>
            <div className="flex justify-between items-center px-2 pb-1 pt-2 border-t border-white/5">
              <span className="text-[10px] text-zinc-500 font-mono">Real-time LangGraph Execution · v2 events</span>
              <div className="flex gap-2">
                {status === 'analyzing' && (
                  <button
                    type="button"
                    onClick={handleStop}
                    className="flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium bg-amber-500/10 text-amber-300 border border-amber-500/20 hover:bg-amber-500/20"
                  >
                    <PauseCircle className="w-3.5 h-3.5" />
                    INTERRUPT
                  </button>
                )}
                <button
                  onClick={status === 'analyzing' ? handleStop : startAnalysis}
                  className={`flex items-center gap-2 px-4 py-1.5 rounded-md text-xs font-medium transition-all ${
                    status === 'analyzing'
                      ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20 hover:bg-rose-500/20'
                      : 'bg-indigo-500 text-white hover:bg-indigo-400 shadow-[0_0_10px_rgba(99,102,241,0.2)]'
                  }`}
                >
                  {status === 'analyzing' ? <Square className="w-3.5 h-3.5 fill-current" /> : <Play className="w-3.5 h-3.5 fill-current" />}
                  {status === 'analyzing' ? 'HALT ENGINE' : 'RUN ANALYSIS'}
                </button>
              </div>
            </div>
          </div>

          <div className="flex-1 bg-[#0c0c0e] border border-white/5 rounded-xl flex flex-col overflow-hidden shadow-inner relative">
            <div className="h-10 border-b border-white/5 bg-[#121214] flex items-center px-4 justify-between">
              <span className="text-xs font-medium text-zinc-400 flex items-center gap-2">
                <Activity className="w-3.5 h-3.5" /> Event Stream
                {activeNode && (
                  <span className="px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 text-[10px] font-mono">
                    @ {activeNode}
                  </span>
                )}
              </span>
              {status === 'analyzing' && <Loader2 className="w-3.5 h-3.5 text-indigo-400 animate-spin" />}
            </div>

            <div
              ref={logContainerRef}
              className="app-scrollbar flex-1 overflow-y-auto p-4 font-mono text-xs space-y-4"
            >
              {logs.length === 0 && status === 'idle' ? (
                <div className="h-full flex items-center justify-center text-zinc-600">Awaiting execution...</div>
              ) : (
                logs.map((log) => (
                  <div key={log.id} className="animate-in fade-in slide-in-from-left-2 duration-300">
                    <div className="flex items-center gap-2 mb-1.5 opacity-70">
                      <span className="text-zinc-500">[{log.time}]</span>
                      <span className={log.node === 'system' ? 'text-zinc-400' : 'text-indigo-400'}>@{log.node}</span>
                    </div>
                    <div className="pl-4 border-l-2 border-zinc-800/50 space-y-1">
                      <span className="text-zinc-300 block">{log.title}</span>
                      <div className="app-scrollbar text-zinc-500 bg-black/20 p-2 rounded border border-white/5 mt-1 overflow-x-auto">
                        <pre>{JSON.stringify(log.data, null, 2)}</pre>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </section>

        <section className="app-scrollbar flex-1 flex flex-col overflow-y-auto pr-2 space-y-6 pb-12">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-zinc-100 tracking-tight">Synthesized Intelligence</h2>
            {status === 'complete' && orchestrator && (
              <span className={`flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full border ${isConsensusReached ? 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20' : 'text-amber-400 bg-amber-400/10 border-amber-400/20'}`}>
                {isConsensusReached ? <CheckCircle2 className="w-3.5 h-3.5" /> : <AlertCircle className="w-3.5 h-3.5" />}
                {isConsensusReached ? 'Consensus Reached' : 'Consensus Failed'}
              </span>
            )}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className={`p-5 rounded-2xl border transition-all duration-700 ${finance ? 'bg-[#121214] border-white/10 shadow-lg' : 'bg-[#121214] border-white/5 opacity-40'}`}>
              <div className="flex items-center gap-2 mb-5">
                <div className={`p-1.5 rounded-md ${finance ? 'bg-blue-500/20 text-blue-400' : 'bg-zinc-800 text-zinc-500'}`}>
                  <Activity className="w-4 h-4" />
                </div>
                <h3 className="text-sm font-medium text-zinc-300">Quantitative Metrics</h3>
              </div>
              {finance ? renderFinanceUI() : <div className="h-24 flex items-center justify-center"><Loader2 className="w-5 h-5 text-zinc-600 animate-spin" /></div>}
            </div>

            <div className={`p-5 rounded-2xl border transition-all duration-700 ${risk ? 'bg-rose-950/10 border-rose-900/30 shadow-lg shadow-rose-900/5' : 'bg-[#121214] border-white/5 opacity-40'}`}>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <div className={`p-1.5 rounded-md ${risk ? 'bg-rose-500/20 text-rose-400' : 'bg-zinc-800 text-zinc-500'}`}>
                    <ShieldAlert className="w-4 h-4" />
                  </div>
                  <h3 className="text-sm font-medium text-zinc-300">Compliance Risk</h3>
                </div>
                {risk?.severity && <span className="text-[10px] font-bold bg-rose-500/20 px-2 py-0.5 rounded text-rose-500 border border-rose-500/30">{risk.severity}</span>}
              </div>
              {risk ? (
                <div className="space-y-2.5 animate-in fade-in zoom-in-95">
                  {Array.isArray(risk?.risk_points) ? risk.risk_points.map((pt: string, i: number) => (
                    <div key={i} className="flex gap-3 bg-rose-950/20 border border-rose-900/20 p-3 rounded-lg items-start">
                      <AlertTriangle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
                      <p className="text-sm text-rose-200/90 leading-snug">{pt}</p>
                    </div>
                  )) : (
                    <div className="app-scrollbar text-zinc-400 bg-black/20 p-3 rounded border border-white/5 overflow-x-auto text-xs font-mono">
                      <pre>{JSON.stringify(risk, null, 2)}</pre>
                    </div>
                  )}
                </div>
              ) : (
                <div className="h-24 flex items-center justify-center">
                  <Loader2 className="w-5 h-5 text-zinc-600 animate-spin" />
                </div>
              )}
            </div>
          </div>

          <div className={`p-6 rounded-2xl border transition-all duration-700 flex-1 ${orchestrator ? 'bg-[#121214] border-indigo-500/20 shadow-2xl shadow-indigo-900/10 relative overflow-hidden' : 'bg-[#121214] border-white/5 opacity-40'}`}>
            {orchestrator && <div className="absolute top-0 left-1/2 -translate-x-1/2 w-2/3 h-px bg-gradient-to-r from-transparent via-indigo-500 to-transparent opacity-50"></div>}

            <div className="flex items-center gap-2 mb-6">
              <div className={`p-1.5 rounded-md ${orchestrator ? 'bg-indigo-500/20 text-indigo-400' : 'bg-zinc-800 text-zinc-500'}`}>
                <BrainCircuit className="w-5 h-5" />
              </div>
              <h3 className="text-base font-medium text-zinc-200">Orchestrator Consensus</h3>
            </div>

            {orchestrator ? (
              <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4">
                <div>
                  <h4 className="text-[11px] font-bold text-zinc-500 uppercase tracking-widest mb-2">Executive Summary</h4>
                  <div className={`p-4 rounded-xl border ${isConsensusReached ? 'bg-indigo-950/20 border-indigo-900/50' : 'bg-amber-950/20 border-amber-900/50'}`}>
                    <p className={`text-base font-medium leading-relaxed ${isConsensusReached ? 'text-indigo-100' : 'text-amber-100'}`}>
                      {streamingText || getOrchestratorSummary()}
                      {streamingText && status === 'analyzing' && (
                        <span className="ml-1 inline-block w-2 h-4 align-middle bg-indigo-300/80 animate-pulse" aria-hidden />
                      )}
                    </p>
                  </div>
                </div>

                {(graphNodes.length > 0 || graphEdges.length > 0) && (
                  <div className="space-y-3">
                    <h4 className="text-[11px] font-bold text-zinc-500 uppercase tracking-widest">Knowledge Graph Live View</h4>
                    <div className="p-4 rounded-xl border border-white/5 bg-black/20 space-y-3">
                      <KnowledgeGraph
                        nodes={graphNodes}
                        edges={graphEdges}
                        highlightNode={null}
                      />
                      {graphNodes.length > 0 && (
                        <div className="space-y-2">
                          <p className="text-xs text-zinc-400">Linked Nodes</p>
                          <div className="flex flex-wrap gap-2">
                            {graphNodes.map((nodeName, index) => (
                              <span
                                key={`${nodeName}-${index}`}
                                className="px-2.5 py-1 rounded-full bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 text-xs"
                              >
                                {nodeName}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                      {retrievedContext?.mode && (
                        <div className="pt-1 text-xs text-zinc-500">
                          Retrieval mode: <span className="text-zinc-300">{retrievedContext.mode}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="h-32 flex flex-col items-center justify-center text-zinc-500 gap-3">
                <Network className="w-8 h-8 opacity-20" />
                <p className="text-sm">Awaiting graph synthesis and consensus...</p>
              </div>
            )}
          </div>
        </section>
      </main>

      <EvidenceDrawer
        open={drawerOpen}
        items={evidence}
        onClose={() => setDrawerOpen(false)}
      />
    </div>
  );
}
