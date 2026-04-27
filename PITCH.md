# Lattice — The Pitch

_For executive audiences. No jargon, all business._

---

## The Problem

Every enterprise is deploying AI agents — sales bots, engineering assistants, HR helpers, customer support copilots. But these agents hit the same wall:

**They're either stupid or dangerous.**

**Stupid** because they don't have the right context. A sales agent that can't see the latest pipeline numbers is useless. An engineering bot without access to the runbook is guessing.

**Dangerous** because there's no control over what they see. Most companies either give agents access to everything (security nightmare) or nothing (useless). There's no middle ground.

**The result:** Every team builds their own retrieval pipeline, their own access controls, their own data integrations. It's fragmented, slow, expensive, and impossible to govern.

---

## What Lattice Does

Lattice is a **context broker** — it sits between your company's knowledge and all your AI agents.

Think of it as a **smart librarian for AI agents.**

When your sales bot asks "What's our Q2 outlook?", Lattice:

1. **Knows what the agent is allowed to see** — sales data, yes. HR compensation data, no.
2. **Delivers pre-prepared, concise answers** — not raw 50-page documents, but the specific facts the agent needs.
3. **Does it in milliseconds** — because the heavy work happened when the data was ingested, not when the agent asks.

---

## Five Things That Make Lattice Different

### 1. It compiles knowledge, not just searches it.

Traditional systems search your documents every time an agent asks a question. That's slow and expensive.

Lattice processes documents **once** when they're added — breaks them into atomic facts, understands the relationships, and pre-packages them. When an agent asks a question, it's just a cache lookup.

It's the difference between Google searching the web live every time vs. having the answer pre-indexed and ready.

### 2. Access control is built into the data, not bolted on.

Every piece of knowledge carries a label: _"who can see this."_
Every agent carries an identity: _"what am I allowed to see."_

Checking access takes **nanoseconds**, not seconds. This is how you give 100 agents access to company knowledge without losing control.

### 3. Same question, different context — automatically.

When the sales bot asks _"How are we doing this quarter?"_, it gets revenue numbers.
When the engineering bot asks the same question, it gets uptime metrics.

Lattice knows what's relevant based on who's asking. No manual configuration needed.

### 4. It understands what you're asking, not just the words you used.

Lattice doesn't just embed your query and search. It generates multiple diverse interpretations of your question — from different angles — then fuses the results using Reciprocal Rank Fusion. An atom that appears across several interpretations gets scored higher than one that matched only once.

If your query has a time period ("Q2") or a subject ("revenue"), Lattice extracts that structure and applies it as a SQL pre-filter before cosine search runs. Searching for "Q2 revenue" never surfaces Q3 atoms.

The result: a system that finds the right context even when your words don't exactly match how the knowledge is stored.

### 5. It knows when facts change — and keeps the history.

Enterprise knowledge is not static. Headcount changes. Deals close. Policies get revised.

When Lattice sees a new fact that contradicts, refines, or replaces an existing one, it doesn't silently overwrite — it classifies the relationship and records the transition. Agents always get the current version. Auditors can ask "what did the system believe on March 15th?" and get an exact answer.

This is the temporal knowledge layer. No other AI context system does this out of the box.

---

## The Demo

Two screens that tell the whole story:

### 1. The Knowledge Graph

Open the **Atom Explorer** and see your entire enterprise knowledge visualized as an interactive network:

- **Every atom** is a node (facts, decisions, metrics, relationships)
- **Every connection** is a purple line showing how knowledge relates
- **Click any atom** to see full details in a modal overlay
- **Navigate the graph** by clicking linked atoms

**What you see:** Your company's knowledge structure at a glance. Sales data connects to revenue metrics. Engineering decisions link to system events. Everything is visible, everything is connected.

### 2. The Context Playground

Type a question — _"What's our Q2 outlook?"_ — and run it as two different agents:

|              | Sales Assistant                          | Engineering Bot                              |
| ------------ | ---------------------------------------- | -------------------------------------------- |
| **Result 1** | EMEA Q2 pipeline: $4.2M, up 12% from Q1  | Platform uptime Q2: 99.97%                   |
| **Result 2** | Board approved EMEA enterprise expansion | 3 P1 incidents, all resolved under 4h MTTR   |
| **Result 3** | Top deals: Acme ($800K), Globex ($650K)  | Infra team prioritizing K8s migration for Q3 |
| **Speed**    | 🔍 ~150ms (smart search: 3 hypotheses + RRF) | 🔍 ~160ms (smart search: 3 hypotheses + RRF) |
| **Access**   | 8 atoms served, 2 filtered               | 6 atoms served, 5 filtered                   |

**Same question. Completely different — and completely appropriate — answers.**

The sales bot never sees engineering incidents. The engineering bot never sees deal values. Smart search generates 3 diverse interpretations of the question and fuses results via Reciprocal Rank Fusion — in ~150ms total.

---

## Data Ownership

Lattice is a **broker, not a data lake.**

Your data stays where it already lives — Confluence, SharePoint, Slack, databases, wherever. Lattice only stores compiled summaries ("index cards, not photocopies") and metadata.

- **Security teams** don't worry about another copy of sensitive data
- **Compliance** is simpler — data doesn't change regions
- **You keep full ownership** — Lattice is a read-only consumer with a compiled cache

---

## The Market

Every enterprise deploying AI agents needs this. That's all of them.

The alternative is every team building their own retrieval pipeline — fragmented, ungoverned, slow, expensive to maintain. Lattice is the centralized layer that makes **all** agents smarter and safer.

---

## The Moat

1. **Compiler + cache architecture** — once enterprise knowledge is compiled into atoms with access controls, switching costs are high
2. **Network effects** — more agents using Lattice means better cache hit rates, better frame optimization, lower latency for everyone
3. **Intelligence layer** — the system learns which context agents actually use and optimizes serving accordingly; gets better with scale

---

## FAQ

**"How is this different from just using RAG?"**

RAG searches documents at query time with a single embedding. Lattice compiles knowledge at ingest time, then at query time generates 3 diverse interpretations of your question and fuses results via Reciprocal Rank Fusion — which means a much higher probability of surfacing the right atom even when your phrasing doesn't match how the knowledge is stored. Plus, RAG has no built-in access control, no deduplication intelligence, and no temporal tracking — Lattice does all three. It's like comparing a library where you search the shelves yourself vs. a librarian who understands what you meant, already pulled the right books, knows which edition is current, and can tell you what the shelf looked like last Tuesday.

**"Why can't we just use a vector database?"**

A vector database is a storage engine — one component. Lattice is the intelligence layer on top: atomization, distillation, access control, caching, agent profiles, and audit logging. That's like asking "why can't we just use a hard drive instead of a search engine?"

**"Is our data safe?"**

Yes. Lattice stores compiled summaries, not your raw data. Original documents stay in your systems. Every access decision is logged. Bitmask access control ensures agents only see what they're authorized to see. Supports on-prem / air-gapped deployment.

**"What about compliance (GDPR, HIPAA, SOC 2)?"**

Data doesn't move regions — Lattice runs where you need it. Full audit trail for every access decision. Right-to-deletion cascades from source to atoms. Classification-based access tiers.

---

## One Line

> **Lattice gives every AI agent the right knowledge, with the right permissions, at the right point in time — in milliseconds.**

---

_See [ARCHITECTURE.md](./ARCHITECTURE.md) for the technical deep dive._
