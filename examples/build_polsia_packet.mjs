import path from 'path';

import { buildDemoPacket } from '../seer_eval/demo_packet.mjs';
import { verifiedHarnessArtifacts } from '../seer_eval/harness_pipeline.mjs';
import { defaultOpsPaths, runOutboundMessageOpsLoop } from '../seer_eval/ops_runner.mjs';
import { exportFindingReportSet } from '../seer_eval/report_exporter.mjs';
import { defaultScannerFindings, verifiedScannerArtifacts } from '../seer_eval/scanner_pipeline.mjs';
import { buildReportSummary } from '../seer_eval/report_renderer.mjs';

const outputDir =
  process.argv[2] ?? path.join(process.cwd(), 'artifacts', 'polsia-demo-packet');
const harnessDir = path.join(outputDir, 'harness');
const scannerDir = path.join(outputDir, 'scanner');
const opsDir = path.join(outputDir, 'ops-loop');

const harnessArtifacts = verifiedHarnessArtifacts();
const harnessExport = exportFindingReportSet(harnessArtifacts, harnessDir, {
  title: 'Harness Verified Findings Report',
});
const scannerArtifacts = verifiedScannerArtifacts(defaultScannerFindings());
const scannerExport = exportFindingReportSet(scannerArtifacts, scannerDir, {
  title: 'Scanner Verified Findings Report',
});
const opsPaths = defaultOpsPaths(process.cwd());
const opsExport = runOutboundMessageOpsLoop(opsPaths.queue_path, opsDir);

const packet = buildDemoPacket(
  {
    harness: {
      ...harnessExport,
      summary: buildReportSummary(harnessArtifacts, { title: 'Harness Verified Findings Report' }),
    },
    scanner: {
      ...scannerExport,
      summary: buildReportSummary(scannerArtifacts, { title: 'Scanner Verified Findings Report' }),
    },
    messages: {
      ...opsExport,
      summary: opsExport.summary,
    },
  },
  outputDir
);

console.log(JSON.stringify(packet, null, 2));
