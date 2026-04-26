// seer_eval/report_exporter.mjs - export verified-finding reports to markdown and JSON bundles.

import { mkdirSync, writeFileSync } from 'fs';
import path from 'path';

import {
  buildReportSummary,
  renderEngineeringHandoff,
  renderFindingReport,
  renderFindingReportSet,
} from './report_renderer.mjs';

function slug(value, fallback = 'artifact') {
  const normalized = String(value ?? fallback)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return normalized || fallback;
}

function ensureDir(dirPath) {
  mkdirSync(dirPath, { recursive: true });
  return dirPath;
}

export function exportFindingReportBundle(artifact, outputDir) {
  const findingId = artifact?.finding_id ?? 'unknown-finding';
  const bundleDir = ensureDir(path.join(outputDir, slug(findingId, 'finding')));
  const reportPath = path.join(bundleDir, 'report.md');
  const artifactPath = path.join(bundleDir, 'artifact.json');

  writeFileSync(reportPath, `${renderFindingReport(artifact)}\n`, 'utf-8');
  writeFileSync(artifactPath, `${JSON.stringify(artifact, null, 2)}\n`, 'utf-8');

  return {
    finding_id: findingId,
    bundle_dir: bundleDir,
    report_path: reportPath,
    artifact_path: artifactPath,
  };
}

export function exportFindingReportSet(artifacts = [], outputDir, options = {}) {
  const rootDir = ensureDir(outputDir);
  const handoffPath = path.join(rootDir, 'engineering_handoff.md');
  const indexPath = path.join(rootDir, 'index.md');
  const manifestPath = path.join(rootDir, 'manifest.json');
  const bundles = artifacts.map(artifact => exportFindingReportBundle(artifact, rootDir));
  const summary = buildReportSummary(artifacts, { title: options.title });

  writeFileSync(
    handoffPath,
    `${renderEngineeringHandoff(artifacts, { title: options.title })}\n`,
    'utf-8'
  );
  writeFileSync(
    indexPath,
    `${renderFindingReportSet(artifacts, { title: options.title })}\n`,
    'utf-8'
  );
  writeFileSync(
    manifestPath,
    `${JSON.stringify(
      {
        ...summary,
        bundles,
      },
      null,
      2
    )}\n`,
    'utf-8'
  );

  return {
    root_dir: rootDir,
    handoff_path: handoffPath,
    index_path: indexPath,
    manifest_path: manifestPath,
    summary,
    bundles,
  };
}
