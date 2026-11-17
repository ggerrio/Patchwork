"use client";

import { FileCode2 } from "lucide-react";
import ReactDiffViewer, { DiffMethod } from "react-diff-viewer-continued";

import { parseUnifiedDiff } from "@/lib/diff";

export function DiffViewer({ proposedDiff }: { proposedDiff: string | null }) {
  if (!proposedDiff || !proposedDiff.trim()) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6 text-sm text-slate-400">
        No patch diff has been generated for this incident yet.
      </div>
    );
  }

  const parsedFiles = parseUnifiedDiff(proposedDiff);

  if (parsedFiles.length === 0) {
    return (
      <pre className="overflow-auto rounded-xl border border-slate-800 bg-slate-950 p-4 font-mono text-xs text-slate-200">
        {proposedDiff}
      </pre>
    );
  }

  return (
    <div className="space-y-4">
      {parsedFiles.map((file) => (
        <div
          key={file.filePath}
          className="overflow-hidden rounded-xl border border-slate-800 bg-slate-950"
        >
          <div className="flex items-center gap-2 border-b border-slate-800 bg-slate-900 px-4 py-2.5 text-xs font-mono text-slate-200">
            <FileCode2 className="h-4 w-4 text-sky-400" />
            {file.filePath}
          </div>
          <div className="overflow-x-auto text-xs">
            <ReactDiffViewer
              oldValue={file.oldValue}
              newValue={file.newValue}
              splitView={true}
              useDarkTheme={true}
              compareMethod={DiffMethod.WORDS}
              leftTitle="Original"
              rightTitle="Proposed Patch"
            />
          </div>
        </div>
      ))}
    </div>
  );
}

