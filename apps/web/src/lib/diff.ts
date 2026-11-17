export interface ParsedFileDiff {
  filePath: string;
  oldValue: string;
  newValue: string;
  addedCount: number;
  removedCount: number;
}

function stripPrefix(raw: string): string {
  const path = raw.split("\t")[0].trim();
  if (path.startsWith("a/") || path.startsWith("b/")) {
    return path.slice(2);
  }
  return path;
}

/**
 * Parse a unified diff into per-file before/after strings and line change counts.
 */
export function parseUnifiedDiff(diffText: string): ParsedFileDiff[] {
  if (!diffText.trim()) {
    return [];
  }

  const lines = diffText.split(/\r?\n/);
  const files: ParsedFileDiff[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("--- ") && i + 1 < lines.length && lines[i + 1].startsWith("+++ ")) {
      const oldPath = stripPrefix(line.slice(4));
      const newPath = stripPrefix(lines[i + 1].slice(4));
      const filePath = newPath === "/dev/null" ? oldPath : newPath;
      i += 2;

      const oldLines: string[] = [];
      const newLines: string[] = [];
      let addedCount = 0;
      let removedCount = 0;

      while (i < lines.length && !lines[i].startsWith("--- ") && !lines[i].startsWith("diff --git ")) {
        const hunkLine = lines[i];
        if (hunkLine.startsWith("@@ ")) {
          i += 1;
          continue;
        }
        if (hunkLine.startsWith("+")) {
          newLines.push(hunkLine.slice(1));
          addedCount += 1;
        } else if (hunkLine.startsWith("-")) {
          oldLines.push(hunkLine.slice(1));
          removedCount += 1;
        } else if (hunkLine.startsWith(" ")) {
          oldLines.push(hunkLine.slice(1));
          newLines.push(hunkLine.slice(1));
        }
        i += 1;
      }

      files.push({
        filePath,
        oldValue: oldLines.join("\n"),
        newValue: newLines.join("\n"),
        addedCount,
        removedCount,
      });
    } else {
      i += 1;
    }
  }

  return files;
}
