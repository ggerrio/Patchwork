"use client";

import { useState } from "react";
import { Check, Copy, FileCode2 } from "lucide-react";
import ReactDiffViewer, { DiffMethod } from "react-diff-viewer-continued";

import { parseUnifiedDiff } from "@/lib/diff";

const TACTILE_DIFF_STYLES = {
  variables: {
    dark: {
      diffViewerBackground: "#0B0C0E",
      diffViewerColor: "#F4F4F5",
      addedBackground: "#0F241D",
      addedColor: "#F4F4F5",
      removedBackground: "#261216",
      removedColor: "#F4F4F5",
      wordAddedBackground: "#10B98133",
      wordRemovedBackground: "#EF444433",
      addedGutterBackground: "#0C1D17",
      removedGutterBackground: "#1E0E11",
      gutterBackground: "#13151A",
      gutterBackgroundDark: "#0B0C0E",
      highlightBackground: "#13151A",
      highlightGutterBackground: "#13151A",
      codeFoldGutterBackground: "#13151A",
      codeFoldBackground: "#13151A",
      emptyLineBackground: "#0B0C0E",
      gutterColor: "#9CA3AF",
      addedGutterColor: "#10B981",
      removedGutterColor: "#EF4444",
      codeFoldContentColor: "#9CA3AF",
      diffViewerTitleBackground: "#13151A",
      diffViewerTitleColor: "#F4F4F5",
      diffViewerTitleBorderColor: "#23262F",
    },
  },
};

export function DiffViewer({ proposedDiff }: { proposedDiff: string | null }) {
  const [copiedFile, setCopiedFile] = useState<string | null>(null);

  if (!proposedDiff || !proposedDiff.trim()) {
    return (
      <div className="tactile-card rounded-lg p-6 text-sm text-[#9CA3AF]">
        No patch diff has been generated for this incident yet.
      </div>
    );
  }

  const parsedFiles = parseUnifiedDiff(proposedDiff);

  async function copyContent(key: string, text: string) {
    await navigator.clipboard.writeText(text);
    setCopiedFile(key);
    setTimeout(() => setCopiedFile(null), 2000);
  }

  if (parsedFiles.length === 0) {
    return (
      <pre className="tactile-card overflow-auto rounded-lg p-5 font-mono text-xs leading-relaxed text-[#F4F4F5]">
        {proposedDiff}
      </pre>
    );
  }

  return (
    <div className="space-y-5">
      {parsedFiles.map((file) => {
        const isCopied = copiedFile === file.filePath;
        return (
          <div
            key={file.filePath}
            className="tactile-card overflow-hidden rounded-lg"
          >
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#23262F] bg-[#13151A] px-4 py-3 font-mono text-xs">
              <div className="flex items-center gap-3">
                <span className="inline-flex items-center gap-2 font-medium text-[#F4F4F5]">
                  <FileCode2 className="h-4 w-4 text-[#10B981]" />
                  {file.filePath}
                </span>

                <div className="flex items-center gap-1.5 rounded bg-[#0B0C0E] px-2 py-0.5 text-[11px]">
                  <span className="font-semibold text-[#10B981]">
                    +{file.addedCount}
                  </span>
                  <span className="font-semibold text-[#EF4444]">
                    -{file.removedCount}
                  </span>
                </div>
              </div>

              <button
                type="button"
                onClick={() => void copyContent(file.filePath, proposedDiff)}
                className="inline-flex items-center gap-1.5 rounded-md border border-[#23262F] bg-[#0B0C0E] px-2.5 py-1 text-[11px] font-medium text-[#9CA3AF] transition hover:border-[#373B47] hover:text-[#F4F4F5]"
              >
                {isCopied ? (
                  <>
                    <Check className="h-3.5 w-3.5 text-[#10B981]" />
                    Copied
                  </>
                ) : (
                  <>
                    <Copy className="h-3.5 w-3.5" />
                    Copy Diff
                  </>
                )}
              </button>
            </div>

            <div className="overflow-x-auto text-xs">
              <ReactDiffViewer
                oldValue={file.oldValue}
                newValue={file.newValue}
                splitView={true}
                useDarkTheme={true}
                compareMethod={DiffMethod.WORDS}
                styles={TACTILE_DIFF_STYLES}
                leftTitle="Original"
                rightTitle="Proposed Patch"
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
