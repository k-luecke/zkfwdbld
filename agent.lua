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

-- Audit M-2 (#13): defaults are placeholders, not real anchored IDs.
-- Operators MUST set these (e.g. via `aos> MODULE_ID = "..."` before
-- `.load agent.lua`, or via the `Set-Prover` handler at runtime). A
-- mis-anchored default would silently route every finding to a wrong
-- process; we refuse to dispatch until both are explicitly configured.
-- We do NOT add a probe handshake here: the Seer kernel (src/lib.rs)
-- only handles Prove/Verify — there is no Ping/Probe/Info action to
-- roundtrip, and adding one without prover-side cooperation would
-- wedge dispatch behind an unanswerable message.
MODULE_ID  = MODULE_ID  or "UNSET"
PROVER_PID = PROVER_PID or "UNSET"

local function prover_configured()
    return PROVER_PID ~= "UNSET"
        and PROVER_PID ~= ""
        and PROVER_PID ~= "<PASTE_SPAWN_OUTPUT_HERE>"
end

-- ── Audit M-3 (#14): admin allowlist + two-admin handshake ───────────────────
-- The audit observed that gating Set-Prover / Flush-Buffer on
-- `msg.From == ao.env.Process.Owner` makes a single owner-key compromise
-- equivalent to total system compromise: an attacker can redirect every
-- outbound proof request (and the embedded raw_string findings) to an
-- attacker-controlled PROVER_PID and then forge "Causation-Proof"
-- replies (msg.From == attacker PROVER_PID passes the Proof-Result gate).
--
-- AOS has no built-in multi-sig primitive; we build it from the persistent
-- globals AOS already preserves across messages. The design:
--
--   1. Admins is a set (table keyed by address → true). It starts as
--      `{Owner: true}` so Phase 0 single-operator deploys keep working.
--      Operators on Phase 1+ can add a second admin via Add-Admin
--      (current Owner-only) and then narrow further via Revoke-Admin
--      (any admin can drop themselves or another, no resurrection).
--   2. Set-Prover and Flush-Buffer require an admin sender. When there
--      is only ONE admin, Set-Prover commits immediately (Phase 0 story
--      preserved). When there are TWO OR MORE admins, Set-Prover writes
--      a PendingProverChange and a *distinct* admin must Confirm-Set-Prover
--      with the matching nonce to commit it. This is the literal multi-sig
--      the audit recommended, but it auto-degrades to single-sig in
--      Phase 0 so we don't ship a footgun the operator can't unlock.
--   3. Revoke is one-way: Add-Admin is gated on the current Owner only,
--      so a compromised non-Owner admin cannot bring in attacker keys.
--      Revoke-Admin is admin-gated so a compromised Owner cannot stop a
--      legitimate admin from evicting them.
--
-- This is intentionally NOT a generic role system. The threat model is
-- "one wallet key was stolen"; the mitigation is "a second key must
-- co-sign before outbound routing changes."

Admins = Admins or nil  -- lazily initialised on first message (Owner not
                        -- known until ao.env is populated under aos)
PendingProverChange = PendingProverChange or nil
ProverChangeNonceSeq = ProverChangeNonceSeq or 0

local function ensure_admins()
    if Admins == nil then
        Admins = {}
        local owner = ao.env and ao.env.Process and ao.env.Process.Owner
        if owner then Admins[owner] = true end
    end
    return Admins
end

local function admin_count()
    ensure_admins()
    local n = 0
    for _ in pairs(Admins) do n = n + 1 end
    return n
end

local function is_admin(addr)
    ensure_admins()
    return addr ~= nil and Admins[addr] == true
end

local function is_owner(addr)
    return addr ~= nil
        and ao.env and ao.env.Process
        and addr == ao.env.Process.Owner
end

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
    if not prover_configured() then
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
-- Audit M-3 (#14): admin-gated, not Owner-gated. Flush-Buffer no longer
-- accepts a Prover-Pid tag — that path was a back-door equivalent of
-- Set-Prover that bypassed the two-admin handshake. PID changes go through
-- Set-Prover / Confirm-Set-Prover only.

Handlers.add(
    "Flush-Buffer",
    Handlers.utils.hasMatchingTag("Action", "Flush-Buffer"),
    function(msg)
        if not is_admin(msg.From) then
            print(string.format("[AUTH] Flush-Buffer rejected from %s (not admin)", msg.From))
            return
        end
        if msg.Tags and msg.Tags["Prover-Pid"] then
            print("[AUTH] Flush-Buffer ignoring Prover-Pid tag — use Set-Prover")
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
-- Audit M-3 (#14): admin-gated, with auto-degrading two-admin handshake.
--   admin_count == 1 → commit immediately (Phase 0 single-operator story)
--   admin_count >= 2 → record PendingProverChange; require a *distinct*
--                      admin to call Confirm-Set-Prover with the nonce.

Handlers.add(
    "Set-Prover",
    Handlers.utils.hasMatchingTag("Action", "Set-Prover"),
    function(msg)
        if not is_admin(msg.From) then
            print(string.format("[AUTH] Set-Prover rejected from %s (not admin)", msg.From))
            return
        end
        local pid = msg.Tags and msg.Tags["Prover-Pid"]
        if not pid or pid == "" then
            print("[CONFIG] Set-Prover missing Prover-Pid tag — ignored")
            return
        end

        if admin_count() < 2 then
            -- Phase 0: single admin commits directly.
            PROVER_PID = pid
            ao.send({ Target = msg.From, Action = "Prover-Set", Data = pid })
            print(string.format("[CONFIG] PROVER_PID updated → %s (single-admin commit)", PROVER_PID))
            return
        end

        -- Phase 1+: stage the change, require distinct-admin confirmation.
        ProverChangeNonceSeq = ProverChangeNonceSeq + 1
        local nonce = tostring(ProverChangeNonceSeq) .. "-" .. tostring(os.time and os.time() or 0)
        PendingProverChange = {
            pid       = pid,
            proposer  = msg.From,
            nonce     = nonce,
            timestamp = os.time and os.time() or 0,
        }
        ao.send({
            Target = msg.From,
            Action = "Prover-Change-Pending",
            Data   = json.encode({ pid = pid, nonce = nonce }),
            Tags   = { ["Nonce"] = nonce, ["Proposed-Pid"] = pid },
        })
        print(string.format("[CONFIG] PROVER_PID change to %s staged by %s (nonce=%s) — awaiting confirm",
                            pid, msg.From, nonce))
    end
)

-- ── Handler: Confirm-Set-Prover ───────────────────────────────────────────────
-- Audit M-3 (#14): second admin co-signs a staged Set-Prover. Confirmer
-- must be an admin AND must not be the proposer (literal multi-sig).

Handlers.add(
    "Confirm-Set-Prover",
    Handlers.utils.hasMatchingTag("Action", "Confirm-Set-Prover"),
    function(msg)
        if not is_admin(msg.From) then
            print(string.format("[AUTH] Confirm-Set-Prover rejected from %s (not admin)", msg.From))
            return
        end
        local pending = PendingProverChange
        if not pending then
            print("[CONFIG] Confirm-Set-Prover with no pending change — ignored")
            return
        end
        local nonce = msg.Tags and msg.Tags["Nonce"]
        if nonce ~= pending.nonce then
            print(string.format("[AUTH] Confirm-Set-Prover nonce mismatch (got %s, want %s)",
                                tostring(nonce), pending.nonce))
            return
        end
        if msg.From == pending.proposer then
            print(string.format("[AUTH] Confirm-Set-Prover rejected: %s is proposer (need distinct admin)",
                                msg.From))
            return
        end
        PROVER_PID = pending.pid
        local committed_pid = pending.pid
        PendingProverChange = nil
        ao.send({ Target = msg.From,        Action = "Prover-Set", Data = committed_pid })
        ao.send({ Target = pending.proposer, Action = "Prover-Set", Data = committed_pid })
        print(string.format("[CONFIG] PROVER_PID updated → %s (confirmed by %s)",
                            PROVER_PID, msg.From))
    end
)

-- ── Handler: Cancel-Set-Prover ────────────────────────────────────────────────
-- Either admin can drop a staged change (e.g. wrong PID typed). No commit.

Handlers.add(
    "Cancel-Set-Prover",
    Handlers.utils.hasMatchingTag("Action", "Cancel-Set-Prover"),
    function(msg)
        if not is_admin(msg.From) then
            print(string.format("[AUTH] Cancel-Set-Prover rejected from %s (not admin)", msg.From))
            return
        end
        if not PendingProverChange then return end
        print(string.format("[CONFIG] PendingProverChange cancelled by %s (was nonce=%s)",
                            msg.From, PendingProverChange.nonce))
        PendingProverChange = nil
    end
)

-- ── Handler: Add-Admin ────────────────────────────────────────────────────────
-- Audit M-3 (#14): Owner-gated. Adds a co-signer so Phase 1+ engages the
-- two-admin handshake. The asshole's critique applies: a compromised Owner
-- can add an attacker here, defeating the handshake. Mitigation: deploy
-- runbook adds the second admin BEFORE the operator rotates the PROVER_PID
-- the first time, and Revoke-Admin (below) is admin-gated so a legitimate
-- second admin can evict a compromised Owner without Owner cooperation.

Handlers.add(
    "Add-Admin",
    Handlers.utils.hasMatchingTag("Action", "Add-Admin"),
    function(msg)
        ensure_admins()
        if not is_owner(msg.From) then
            print(string.format("[AUTH] Add-Admin rejected from %s (not Owner)", msg.From))
            return
        end
        local addr = msg.Tags and msg.Tags["Admin"]
        if not addr or addr == "" then
            print("[CONFIG] Add-Admin missing Admin tag — ignored")
            return
        end
        Admins[addr] = true
        ao.send({ Target = msg.From, Action = "Admin-Added", Data = addr })
        print(string.format("[CONFIG] Admin added: %s (count=%d)", addr, admin_count()))
    end
)

-- ── Handler: Revoke-Admin ─────────────────────────────────────────────────────
-- Audit M-3 (#14): admin-gated and one-way. Any admin may revoke any admin
-- (including themselves and the Owner). This is the "Revoke-only floor"
-- the asshole asked for: once admin_count >= 2, a compromised Owner cannot
-- prevent the legitimate co-admin from evicting them. We refuse to drop
-- below 1 admin to avoid bricking the process.

Handlers.add(
    "Revoke-Admin",
    Handlers.utils.hasMatchingTag("Action", "Revoke-Admin"),
    function(msg)
        if not is_admin(msg.From) then
            print(string.format("[AUTH] Revoke-Admin rejected from %s (not admin)", msg.From))
            return
        end
        local addr = msg.Tags and msg.Tags["Admin"]
        if not addr or addr == "" then
            print("[CONFIG] Revoke-Admin missing Admin tag — ignored")
            return
        end
        if not Admins[addr] then
            print(string.format("[CONFIG] Revoke-Admin: %s is not an admin — no-op", addr))
            return
        end
        if admin_count() <= 1 then
            print(string.format("[AUTH] Revoke-Admin refused: would leave 0 admins (last=%s)", addr))
            return
        end
        Admins[addr] = nil
        -- A staged change loses meaning if its proposer was just evicted.
        if PendingProverChange and PendingProverChange.proposer == addr then
            print(string.format("[CONFIG] Dropping PendingProverChange (proposer %s revoked)", addr))
            PendingProverChange = nil
        end
        ao.send({ Target = msg.From, Action = "Admin-Revoked", Data = addr })
        print(string.format("[CONFIG] Admin revoked: %s (count=%d)", addr, admin_count()))
    end
)

-- ── Handler: List-Admins ──────────────────────────────────────────────────────
-- Read-only introspection so an operator can audit the current set.

Handlers.add(
    "List-Admins",
    Handlers.utils.hasMatchingTag("Action", "List-Admins"),
    function(msg)
        ensure_admins()
        local list = {}
        for addr in pairs(Admins) do table.insert(list, addr) end
        local pending = nil
        if PendingProverChange then
            pending = {
                pid       = PendingProverChange.pid,
                proposer  = PendingProverChange.proposer,
                nonce     = PendingProverChange.nonce,
                timestamp = PendingProverChange.timestamp,
            }
        end
        ao.send({
            Target = msg.From,
            Action = "Admins-Reply",
            Data   = json.encode({
                admins                  = list,
                count                   = admin_count(),
                pending_prover_change   = pending,
            }),
        })
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
                prover_ready = prover_configured(),
                module_id    = MODULE_ID,
                demo_proof_mode = DEMO_PROOF_MODE,
                admin_count  = admin_count(),
                prover_change_pending = PendingProverChange ~= nil,
            }),
        })
    end
)

print("[INIT] Paxiom HTS Orchestrator loaded.")
print(string.format("[INIT] Module ID : %s", MODULE_ID))
print(string.format("[INIT] Prover PID: %s", PROVER_PID))
print("[INIT] Awaiting Scan-Page messages from crawler.")
