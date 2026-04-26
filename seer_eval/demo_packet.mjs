// seer_eval/demo_packet.mjs - build a customer-facing demo packet from verified finding exports.

import { mkdirSync, writeFileSync } from 'fs';
import path from 'path';

function ensureDir(dirPath) {
  mkdirSync(dirPath, { recursive: true });
  return dirPath;
}

function relativeFrom(rootDir, targetPath) {
  return path.relative(rootDir, targetPath).replace(/\\/g, '/');
}

function buildOverview(results = {}, options = {}) {
  const generatedAt = options.generated_at ?? new Date().toISOString();
  const harnessSummary = results.harness?.summary ?? {};
  const scannerSummary = results.scanner?.summary ?? {};
  const messagesSummary = results.messages?.summary ?? {};

  return [
    '# Polsia Demo Packet',
    '',
    `Generated: ${generatedAt}`,
    '',
    '## Product Story',
    'zkfwdbld is presented here as a trust layer for agentic actions.',
    'Instead of replacing scanners or agent tooling, it adds:',
    '- a normalized artifact for findings or actions',
    '- a trace of the evidence and policy context',
    '- a verification or bounded-policy decision for supported families',
    '- a handoff-ready report for the next operational step',
    '',
    '## What This Packet Shows',
    '- the same trust-layer product surface from a controlled harness source',
    '- the same trust-layer product surface from a mocked scanner export source',
    '- the same trust-layer product surface from a native outbound-message ops queue',
    '- one verified finding family, `HIDDEN_INPUT`, with prove/verify results',
    '- one bounded policy action family, outbound message approval, with `ready_to_send` vs `needs_review` states',
    '- explicit separation between trusted, reviewable, and demo-only outputs',
    '',
    '## Included Bundles',
    `- Harness bundle: ${results.harness ? relativeFrom(options.root_dir, results.harness.root_dir) : 'n/a'}`,
    `- Scanner bundle: ${results.scanner ? relativeFrom(options.root_dir, results.scanner.root_dir) : 'n/a'}`,
    `- Ops bundle: ${results.messages ? relativeFrom(options.root_dir, results.messages.root_dir) : 'n/a'}`,
    '',
    '## Handoff Snapshot',
    `- Harness readiness: ${harnessSummary.handoff_readiness ?? 'n/a'}`,
    `- Scanner readiness: ${scannerSummary.handoff_readiness ?? 'n/a'}`,
    `- Ops readiness: ${messagesSummary.handoff_readiness ?? 'n/a'}`,
    '',
    '## Suggested Walkthrough',
    '1. Open `overview.md` to frame the product as a trust layer rather than a replacement scanner or agent.',
    '2. Open the harness `engineering_handoff.md` to show verified findings beside clearly labeled demo-only findings.',
    '3. Open the scanner `engineering_handoff.md` to show the same verified finding family from a second source.',
    '4. Open the ops-loop `engineering_handoff.md` to show a non-security action family with `ready_to_send` vs `needs_review` states.',
    '5. Open one per-item `report.md` to inspect trust rationale, evidence, and recommended action.',
    '6. Open the corresponding `artifact.json` to show the machine-readable contract under the report.',
    '',
    '## Why This Matters',
    'The point of the demo is not just that a proof exists.',
    'The point is that an operator can quickly see what is ready for the next step, what still needs review, and why.',
  ].join('\n');
}

function buildTalkTrack(results = {}, options = {}) {
  const harnessSummary = results.harness?.summary ?? {};
  const scannerSummary = results.scanner?.summary ?? {};
  const messagesSummary = results.messages?.summary ?? {};

  return [
    '# Polsia Demo Talk Track',
    '',
    '## Opening',
    'zkfwdbld is not trying to replace the tools autonomous teams already use.',
    'The product story is that it sits on top of those tools and turns low-trust findings or actions into something teams can verify, explain, and hand to the next workflow step with more confidence.',
    '',
    '## What To Show First',
    'Start with `overview.md` so the audience sees the product framing before the details.',
    'Then open the harness, scanner, and ops-loop handoff documents to show that the same trust-layer format works across different input sources and action types.',
    '',
    '## Two-Minute Walkthrough',
    '1. Show the packet overview and say this is a trust layer, not a replacement scanner or autonomous platform.',
    `2. Show the harness handoff doc and say: ${harnessSummary.handoff_readiness ?? 'Some findings are ready for handoff.'} This makes the review boundary explicit.`,
    `3. Show the scanner handoff doc and say: ${scannerSummary.handoff_readiness ?? 'Verified findings can move directly to engineering.'}`,
    `4. Show the ops-loop handoff doc and say: ${messagesSummary.handoff_readiness ?? 'Some actions can proceed while others need review.'}`,
    '5. Open one verified or ready-to-send per-item report and highlight recommended action, trust rationale, and supporting evidence.',
    '6. Open the matching `artifact.json` briefly to show that the report is backed by a machine-readable contract.',
    '',
    '## Key Lines To Use',
    '- "Your existing tools found this. zkfwdbld made it easier to trust and route."',
    '- "We separate what is verified from what still needs analyst review."',
    '- "The goal is not just proof generation. The goal is a cleaner handoff boundary for autonomous actions."',
    '- "This helps teams spend less time re-validating actions they already suspected were safe or unsafe."',
    '- "The same trust layer can also govern non-security agent actions like outbound messages."',
    '',
    '## Questions To Expect',
    '- Which claim families are truly supported today?',
    '- How would this connect to our existing scanners or agent workflows?',
    '- What happens to findings that are not yet supported?',
    '- Can the same artifact model cover broader agent actions?',
    '- Can this artifact be attached to tickets or downstream workflow systems?',
    '',
    '## Honest Boundaries',
    '- `HIDDEN_INPUT` is the first supported claim family.',
    '- The scanner integration in this packet is still mocked, while the ops-loop path is driven by a native queue file.',
    '- Outbound message approval is currently a bounded policy-check path, not a proof of message quality.',
    '- Demo-only findings are clearly labeled and should not be oversold.',
    '',
    '## Closing',
    'The point to leave with is simple: zkfwdbld helps teams see which automated findings or actions are ready for the next step, and why.',
  ].join('\n');
}

export function buildDemoPacket(results = {}, outputDir, options = {}) {
  const rootDir = ensureDir(outputDir);
  const overviewPath = path.join(rootDir, 'overview.md');
  const talkTrackPath = path.join(rootDir, 'demo_talk_track.md');
  const manifestPath = path.join(rootDir, 'packet_manifest.json');
  const overview = buildOverview(results, {
    ...options,
    root_dir: rootDir,
  });
  const talkTrack = buildTalkTrack(results, options);

  const manifest = {
    generated_at: options.generated_at ?? new Date().toISOString(),
    packet_type: 'polsia_demo_packet',
    overview_path: overviewPath,
    bundles: {
      harness: results.harness
        ? {
            root_dir: results.harness.root_dir,
            handoff_path: results.harness.handoff_path,
            index_path: results.harness.index_path,
            manifest_path: results.harness.manifest_path,
            summary: results.harness.summary ?? null,
          }
        : null,
      scanner: results.scanner
        ? {
            root_dir: results.scanner.root_dir,
            handoff_path: results.scanner.handoff_path,
            index_path: results.scanner.index_path,
            manifest_path: results.scanner.manifest_path,
            summary: results.scanner.summary ?? null,
          }
        : null,
      messages: results.messages
        ? {
            root_dir: results.messages.root_dir,
            handoff_path: results.messages.handoff_path,
            index_path: results.messages.index_path,
            manifest_path: results.messages.manifest_path,
            summary: results.messages.summary ?? null,
          }
        : null,
    },
  };

  writeFileSync(overviewPath, `${overview}\n`, 'utf-8');
  writeFileSync(talkTrackPath, `${talkTrack}\n`, 'utf-8');
  writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf-8');

  return {
    root_dir: rootDir,
    overview_path: overviewPath,
    talk_track_path: talkTrackPath,
    manifest_path: manifestPath,
    bundles: manifest.bundles,
  };
}
