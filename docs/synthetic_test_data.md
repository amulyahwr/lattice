# Synthetic Test Data

Sample atoms and conversation chunks for manual testing without real user data.

---

## Quick capture set (paste into `lc` or Telegram)

```
I prefer dark roast coffee, no sugar
Decided to use Postgres for the new project instead of SQLite
Hiking in Patagonia is on my bucket list
I work best in the mornings before 10am
Dog is named Max, a golden retriever
Prefer window seats on long flights
Standing desk helps with focus — bought one in March
Allergic to shellfish
```

Run all at once:

```bash
lc "I prefer dark roast coffee, no sugar"
lc "Decided to use Postgres for the new project instead of SQLite"
lc "Hiking in Patagonia is on my bucket list"
lc "I work best in the mornings before 10am"
lc "Dog is named Max, a golden retriever"
lc "Prefer window seats on long flights"
lc "Standing desk helps with focus — bought one in March"
lc "Allergic to shellfish"
```

---

## Recall questions to verify retrieval

| Question | Expected atom |
|---|---|
| What do I prefer about coffee? | dark roast, no sugar |
| What database did I decide on? | Postgres |
| What's on my travel bucket list? | Patagonia hiking |
| When do I work best? | mornings before 10am |
| What's my dog's name? | Max, golden retriever |
| What do I prefer on planes? | window seats |
| What did I buy for focus? | standing desk |
| Any food allergies? | shellfish |

---

## Conversation chunk (for inbox drop or session save)

Save as `~/.lattice/inbox/test-session.md`:

```
user: I've been thinking about my workout routine
assistant: What are you considering changing?
user: I want to start swimming instead of running. My knees are bothering me.
assistant: That makes sense. Swimming is much lower impact. Have you swum regularly before?
user: Yes, I used to swim competitively in college. I'd like to get back to 3x per week.
assistant: Great foundation. Starting at 3x per week sounds realistic given your background.
```

---

## Old atom (for rediscovery highlight testing)

To test the 30-day rediscovery highlight, manually edit an atom's `ingested_at` field:

```bash
# Find an atom file
ls ~/.lattice/*.md | head -3

# Edit frontmatter — change ingested_at to 35 days ago
# Example:
# ingested_at: 2026-05-01T10:00:00+00:00
```

Then ask a question that retrieves that atom — the citation should glow amber in the web UI and Telegram should append a "from 35 days ago" note.

---

## Topic depth testing (for STORY-031)

To hit the 5-atom threshold for one subject quickly:

```bash
for i in 1 2 3 4 5; do
  lc "coffee preference $i: I prefer dark roast"
done
curl "http://localhost:7337/api/topic/depth?subject=coffee%20preference%201" | python3 -m json.tool
```

Note: the subject is extracted by the LLM during ingest — the exact subject string may differ from the input text. Check `lc status` to see what subjects were stored.
