import path from 'path';

import { buildDemoPacket } from '../seer_eval/demo_packet.mjs';
import { verifiedHarnessArtifacts } from '../seer_eval/harness_pipeline.mjs';
import { reviewedOutboundMessageArtifacts } from '../seer_eval/message_pipeline.mjs';
import { exportFindingReportSet } from '../seer_eval/report_exporter.mjs';
import { defaultScannerFindings, verifiedScannerArtifacts } from '../seer_eval/scanner_pipeline.mjs';
import { buildReportSummary } from '../seer_eval/report_renderer.mjs';

const outputDir =
  process.argv[2] ?? path.join(process.cwd(), 'artifacts', 'polsia-demo-packet');
const harnessDir = path.join(outputDir, 'harness');
const scannerDir = path.join(outputDir, 'scanner');
const messageDir = path.join(outputDir, 'messages');

const harnessArtifacts = verifiedHarnessArtifacts();
const harnessExport = exportFindingReportSet(harnessArtifacts, harnessDir, {
  title: 'Harness Verified Findings Report',
});
const scannerArtifacts = verifiedScannerArtifacts(defaultScannerFindings());
const scannerExport = exportFindingReportSet(scannerArtifacts, scannerDir, {
  title: 'Scanner Verified Findings Report',
});
const messageArtifacts = reviewedOutboundMessageArtifacts();
const messageExport = exportFindingReportSet(messageArtifacts, messageDir, {
  title: 'Outbound Message Action Review',
});

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
      ...messageExport,
      summary: buildReportSummary(messageArtifacts, { title: 'Outbound Message Action Review' }),
    },
  },
  outputDir
);

console.log(JSON.stringify(packet, null, 2));
