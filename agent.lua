-- agent.lua — Paxiom HTS Orchestrator
-- AO process that ingests raw HTML/header strings from HackThisSite.org puzzle
-- pages, pattern-scans for non-homogeneous DOM elements, and routes findings
-- to the anchored Seer ZK-prover for Fact → Correlation → Causation proofs.
--
-- Load into an AOS process:
--   aos <your-orchestrator-pid> < agent.lua
--
-- External crawler sends pages as:
--   ao.send({ Target = ORCHESTRATOR_PID,
--             Action = "Scan-Page",
--             Data   = "<raw HTML string>",
--             Tags   = { ["Page-URL"] = "...", ["Level"] = "3" } })

local json = require('json')

-- ── Configuration ────────────────────────────────────────────────────────────

-- Permanently anchored Seer brain (Arweave module TX).
MODULE_ID  = MODULE_ID  or "Iql5WjEcg8T8vkSm4k7d0WxFDTLfZnxooTPcZK8JNl0"

-- Set this once spawn_seer.js returns the live Process ID.
PROVER_PID = PROVER_PID or "GFtPupsXe1BBCFI7HROtoz6hzOaOYSfh2LUv3DnT76o"

-- ── FIFO Buffer (1,000-slot) ──────────────────────────────────────────────────
-- Absorbs rapid-fire page crawls without losing findings.
-- Each slot: { url, level, pattern_type, raw_string, timestamp }

ScanBuffer = ScanBuffer or {}
BUFFER_CAP = 1000
PendingProofs = PendingProofs or {}
ProofSeq = ProofSeq or 0
PendingProofCount = PendingProofCount or 0

-- The current encoder produces a CNF whose polarities are derived from
-- FNV-1a(finding.raw_string), so the proof binds to finding identity (any
-- byte change → different CNF → different proof). It does not yet prove
-- anything semantic about the finding's content; that lives in the future
-- pattern-family encoders. Keep DEMO_PROOF_MODE true until a real
-- semantic-binding encoder is wired in.
DEMO_PROOF_MODE = DEMO_PROOF_MODE ~= false

-- ── Shared CNF derivation ─────────────────────────────────────────────────────
-- FNV-1a 32-bit, byte-accurate over UTF-8. Mirror of seer_eval/claim_encoder.mjs's
-- fnv1a32; the two implementations must produce the same output for the same
-- input so agent.lua and the Node pipeline agree on the CNF for a given fact.
local function fnv1a32(text)
    local hash = 2166136261
    for i = 1, #text do
        hash = bit32.bxor(hash, string.byte(text, i))
        hash = (hash * 16777619) % 4294967296
    end
    return hash
end

-- Derive a 24-variable / 8-clause 3-SAT instance whose polarities are
-- determined by FNV-1a(fact). Mirror of deriveCnfFromFact in claim_encoder.mjs.
local function derive_cnf_from_fact(fact)
    local polarity_hash = fnv1a32(fact or "")
    local seed_hash = fnv1a32((fact or "") .. "|cnf")
    local cnf = {}
    for j = 0, 7 do
        local clause = {}
        for k = 0, 2 do
            local bit_idx = 3 * j + k
            local bit = bit32.band(bit32.rshift(polarity_hash, bit_idx), 1)
            local v = 3 * j + k + 1
            if bit == 1 then
                clause[k + 1] = v
            else
                clause[k + 1] = -v
            end
        end
        cnf[j + 1] = clause
    end
    return cnf, 24, seed_hash
end

local function buffer_push(entry)
    table.insert(ScanBuffer, entry)
    if #ScanBuffer > BUFFER_CAP then
        table.remove(ScanBuffer, 1)   -- evict oldest
    end
end

local function buffer_pop()
    if #ScanBuffer == 0 then return nil end
    return table.remove(ScanBuffer, 1)
end

-- ── DOM Pattern Scanner ───────────────────────────────────────────────────────
-- Identifies non-homogeneous elements that HTS puzzles embed as hints or
-- exploitable surfaces:
--   HIDDEN_INPUT   — <input type="hidden" ...>  (password/token leaks)
--   JS_COMMENT     — <!-- or // comments containing logic hints
--   NONSTANDARD_HDR— Server/X-* headers revealing stack info
--   INLINE_SCRIPT  — <script> blocks with hardcoded values
--   MAILTO_LEAK    — mailto: or plaintext emails as auth hints

local PATTERNS = {
    { name = "HIDDEN_INPUT",    pat = '<input[^>]+type%s*=%s*["\']?hidden'  },
    { name = "JS_COMMENT",      pat = "<!%-%-.-%-%->",                       },
    { name = "INLINE_SCRIPT",   pat = "<script[^>]*>.+</script>"             },
    { name = "MAILTO_LEAK",     pat = "mailto:[%w%.%+%-]+@[%w%.%-]+"        },
    { name = "NONSTANDARD_HDR", pat = "X%-[%w%-]+:%s*.+"                    },
    { name = "PASSWORD_FIELD",  pat = '<input[^>]+name%s*=%s*["\']?passw'   },
}

-- Audit H-7 (#11): walk every match per pattern (was first-match only).
-- Node harness_pipeline.mjs uses matchAll; Lua scan_dom must match
-- semantics or the two scanners diverge on multi-occurrence pages.
-- The per-pattern cap defends against pathological pages allocating
-- huge findings tables before the agent's global buffer cap fires.
local MAX_MATCHES_PER_PATTERN = 100
local function scan_dom(html)
    local findings = {}
    for _, rule in ipairs(PATTERNS) do
        local pos = 1
        local count = 0
        while count < MAX_MATCHES_PER_PATTERN do
            local s, e = string.find(html, rule.pat, pos)
            if not s then break end
            table.insert(findings, {
                pattern_type = rule.name,
                raw_string   = string.sub(html, s, math.min(e, s + 256)),
                offset       = s,
            })
            pos = e + 1
            count = count + 1
        end
    end
    return findings
end

-- ── FCC Handler: Fact → Correlation → Causation ───────────────────────────────
--
-- Fact:        Raw HTML/header string captured from the HTS puzzle page.
-- Correlation: Forward the string pair to the Seer prover to check whether
--              String_A (e.g. a hidden password field value) correlates with
--              Auth_Access_B (the expected credential pattern for this level).
-- Causation:   The Seer generates a Borsh-encoded ZK-proof that supplying
--              Input_X causes State_Change_Y (level submission accepted).
--
-- The prover receives an AoMessage::Solve payload containing a SAT formula
-- encoding the auth constraint; it returns the satisfying assignment (the
-- credential) plus an R1CS witness proving the assignment is valid.

local function fcc_dispatch(finding, level, url, requester)
    requester = requester or ao.env.Process.Owner
    if PROVER_PID == "<PASTE_SPAWN_OUTPUT_HERE>" then
        print("[WARN] PROVER_PID not set — buffering finding for later dispatch")
        buffer_push({
            url          = url,
            level        = level,
            requester    = requester,
            pattern_type = finding.pattern_type,
            raw_string   = finding.raw_string,
            timestamp    = os.time and os.time() or 0,
            pending      = true,
        })
        return
    end

    -- Encode the finding as a SAT-style claim for the Seer.
    -- The "cnf" here is a symbolic encoding of the auth constraint:
    --   [+lit] the hidden value is present  →  credential candidate
    --   [-lit] the pattern is a decoy       →  skip
    -- In production this would be generated by a proper CNF encoder;
    -- for the prototype we send a 3-clause stub the prover can expand.
    -- IMPORTANT: "Action" must be inside the JSON body — the Seer kernel
    -- reads Data as a JSON Request with #[serde(tag = "Action")].
    -- The AO-level Action tag is for message routing only.
    -- context is kept JSON-encoded for compatibility with existing messages;
    -- the Rust kernel accepts it as a JSON value.
    local encoder_mode = DEMO_PROOF_MODE and "demo" or "production"
    ProofSeq = ProofSeq + 1
    local corr_id = ao.id .. "-" .. (os.time and os.time() or "0") .. "-" .. tostring(ProofSeq)
    PendingProofs[corr_id] = {
        requester    = requester,
        url          = url,
        level        = level,
        pattern_type = finding.pattern_type,
        encoder_mode = encoder_mode,
        timestamp    = os.time and os.time() or 0,
    }
    PendingProofCount = PendingProofCount + 1

    local cnf, num_vars, seed = derive_cnf_from_fact(finding.raw_string or "")

    local claim = json.encode({
        Action   = "Prove",
        fact     = finding.raw_string,
        context  = json.encode({
            level = level,
            url = url,
            pattern = finding.pattern_type,
            correlation_id = corr_id,
            encoder_mode = encoder_mode,
        }),
        cnf      = cnf,
        num_vars = num_vars,
        seed     = seed,
    })

    ao.send({
        Target = PROVER_PID,
        Action = "Prove",   -- AO routing tag (not read by kernel)
        Data   = claim,
        Tags   = {
            ["Correlation-Id"] = corr_id,
            ["Level"]          = tostring(level),
            ["Pattern"]        = finding.pattern_type,
            ["Encoder-Mode"]   = encoder_mode,
        },
    })

    print(string.format("[FCC] Dispatched %s finding from level %s to Seer",
                        finding.pattern_type, tostring(level)))
end

-- ── Handler: Scan-Page ────────────────────────────────────────────────────────
-- Receives raw HTML (or header dump) from the external crawler.
-- Runs the DOM scanner and dispatches each finding through FCC.

Handlers.add(
    "Scan-Page",
    Handlers.utils.hasMatchingTag("Action", "Scan-Page"),
    function(msg)
        local html  = msg.Data or ""
        local url   = (msg.Tags and msg.Tags["Page-URL"]) or "unknown"
        local level = (msg.Tags and msg.Tags["Level"])    or "0"

        print(string.format("[SCAN] %d bytes received — level %s — %s",
                            #html, level, url))

        local findings = scan_dom(html)

        if #findings == 0 then
            print("[SCAN] No non-homogeneous elements found")
            return
        end

        print(string.format("[SCAN] %d finding(s) — routing to FCC", #findings))
        for _, f in ipairs(findings) do
            fcc_dispatch(f, level, url, msg.From)
        end
    end
)

-- ── Handler: Proof-Result ─────────────────────────────────────────────────────
-- Receives JSON proof results from the Seer prover.
-- Routes back to the originating crawler or logs the causation proof.

Handlers.add(
    "Proof-Result",
    Handlers.utils.hasMatchingTag("Action", "Proof-Result"),
    function(msg)
        if msg.From ~= PROVER_PID then
            print(string.format("[AUTH] Proof-Result rejected from %s (expected %s)",
                                msg.From, PROVER_PID))
            return
        end
        local corr_id = msg.Tags and msg.Tags["Correlation-Id"] or "unknown"
        local ok, result = pcall(json.decode, msg.Data or "{}")
        if not ok or type(result) ~= "table" then
            print(string.format("[AUTH] Proof-Result %s has unparseable payload — dropping",
                                corr_id))
            return
        end
        if type(result.satisfiable) ~= "boolean" then
            print(string.format("[AUTH] Proof-Result %s missing boolean satisfiable field — dropping",
                                corr_id))
            return
        end

        local pending = PendingProofs[corr_id]
        if not pending then
            print(string.format("[AUTH] Proof-Result %s has no pending request — dropping", corr_id))
            return
        end
        PendingProofs[corr_id] = nil
        PendingProofCount = math.max(0, PendingProofCount - 1)

        if result.satisfiable then
            print(string.format("[PROOF] Correlation-Id %s → SATISFIABLE", corr_id))
            print(string.format("[PROOF] Witness length: %d wires",
                                result.witness and #result.witness or 0))

            local action = "Causation-Proof"
            local result_tag = "LEVEL_CLEAR"
            local out_data = msg.Data
            if pending.encoder_mode == "demo" then
                action = "Demo-Proof-Result"
                result_tag = "DEMO_ONLY"
                -- Audit H-1 (#5): demo-mode results MUST NOT propagate the
                -- prover's `satisfiable=true` and witness verbatim. A
                -- consumer gated only on `Action` would otherwise be
                -- tricked into trusting a demo proof. We emit a distinct
                -- schema with the prover's verdict preserved under a
                -- RENAMED key (`prover_satisfiable`); no `satisfiable`
                -- field at all, so any consumer reading the old key
                -- fails loudly rather than silently.
                local witness_len = 0
                if result.witness and type(result.witness) == "table" then
                    witness_len = #result.witness
                end
                out_data = json.encode({
                    schema                = "demo-proof-result/v1",
                    demo_only             = true,
                    prover_satisfiable    = result.satisfiable,
                    prover_witness_length = witness_len,
                    correlation_id        = corr_id,
                })
                print(string.format("[PROOF] %s used demo CNF — not emitting Causation-Proof", corr_id))
            end

            ao.send({
                Target = pending.requester,
                Action = action,
                Data   = out_data,
                Tags   = {
                    ["Correlation-Id"] = corr_id,
                    ["Result"]         = result_tag,
                    ["Encoder-Mode"]   = pending.encoder_mode,
                    ["Pattern"]        = pending.pattern_type,
                    ["Level"]          = tostring(pending.level),
                },
            })
        else
            print(string.format("[PROOF] Correlation-Id %s → UNSAT (wrong surface)",
                                corr_id))
            ao.send({
                Target = pending.requester,
                Action = "Proof-Unsat",
                Data   = msg.Data,
                Tags   = {
                    ["Correlation-Id"] = corr_id,
                    ["Result"]         = "UNSAT",
                    ["Encoder-Mode"]   = pending.encoder_mode,
                    ["Pattern"]        = pending.pattern_type,
                    ["Level"]          = tostring(pending.level),
                },
            })
        end
    end
)

-- ── Handler: Flush-Buffer ─────────────────────────────────────────────────────
-- Re-dispatches buffered findings after PROVER_PID is set.

Handlers.add(
    "Flush-Buffer",
    Handlers.utils.hasMatchingTag("Action", "Flush-Buffer"),
    function(msg)
        if msg.From ~= ao.env.Process.Owner then
            print(string.format("[AUTH] Flush-Buffer rejected from %s", msg.From))
            return
        end
        local pid = msg.Tags and msg.Tags["Prover-Pid"]
        if pid then
            PROVER_PID = pid
            print(string.format("[CONFIG] PROVER_PID set → %s", PROVER_PID))
        end

        local count = #ScanBuffer
        print(string.format("[BUFFER] Flushing %d pending findings...", count))

        for _ = 1, count do
            local entry = buffer_pop()
            if entry then
                fcc_dispatch(
                    { pattern_type = entry.pattern_type, raw_string = entry.raw_string },
                    entry.level,
                    entry.url,
                    entry.requester
                )
            end
        end
        print("[BUFFER] Flush complete")
    end
)

-- ── Handler: Set-Prover ───────────────────────────────────────────────────────

Handlers.add(
    "Set-Prover",
    Handlers.utils.hasMatchingTag("Action", "Set-Prover"),
    function(msg)
        if msg.From ~= ao.env.Process.Owner then
            print(string.format("[AUTH] Set-Prover rejected from %s", msg.From))
            return
        end
        local pid = msg.Tags and msg.Tags["Prover-Pid"]
        if pid then
            PROVER_PID = pid
            ao.send({ Target = msg.From, Action = "Prover-Set", Data = pid })
            print(string.format("[CONFIG] PROVER_PID updated → %s", PROVER_PID))
        end
    end
)

-- ── Handler: Buffer-Status ────────────────────────────────────────────────────

Handlers.add(
    "Buffer-Status",
    Handlers.utils.hasMatchingTag("Action", "Buffer-Status"),
    function(msg)
        ao.send({
            Target = msg.From,
            Action = "Status-Reply",
            Data   = json.encode({
                buffer_depth = #ScanBuffer,
                buffer_cap   = BUFFER_CAP,
                pending_proofs = PendingProofCount,
                prover_ready = PROVER_PID ~= "<PASTE_SPAWN_OUTPUT_HERE>",
                module_id    = MODULE_ID,
                demo_proof_mode = DEMO_PROOF_MODE,
            }),
        })
    end
)

print("[INIT] Paxiom HTS Orchestrator loaded.")
print(string.format("[INIT] Module ID : %s", MODULE_ID))
print(string.format("[INIT] Prover PID: %s", PROVER_PID))
print("[INIT] Awaiting Scan-Page messages from crawler.")
