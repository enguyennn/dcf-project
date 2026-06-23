---
description: 'Rules for code examples in documentation — pseudo-code vs implementation, public vs internal types.'
applyTo: '**/artifacts/scenarios/eng-docs/**/*.md'
---

# Code in Documentation

## What to Include vs Avoid

| Include | Avoid |
|---------|-------|
| Pseudo-code algorithms | Actual implementation code |
| Configuration examples (JSON, YAML) | Internal class implementations |
| Public API signatures | Private method details |
| Integration patterns | Step-by-step code walkthroughs |
| Public SDK/API types | Internal schema types |

**Rationale:** Code snippets become stale. Pseudo-code captures logic without coupling to implementation.

## Customer-Facing Types

- Reference **public SDK/API types** that consumers actually use
- Avoid **internal schema/implementation types** even if they're what the service uses internally
- If the public API accepts `string` but internal code uses `CultureInfo?`, documentation shows `string`

## File Path References

| Link to file path | Just name the class |
|-------------------|-------------------|
| Entry points (Startup.cs, main Worker) | Implementation details |
| Configuration files (appsettings, config.json) | Internal helper classes |
| Extension points (interfaces consumers implement) | Private/internal types |

**Verification required:** Before adding a file link, verify the path exists. Don't assume conventional folder structures.

**Pattern:** Use an "Entry Points" section with 2-3 verified links instead of scattering paths throughout:
```markdown
### Entry Points
- **Service registration:** [Startup.cs](../../src/Service.X/Startup.cs)
- **Job execution:** [XJob.cs](../../src/Service.X/Worker/Jobs/XJob.cs)
```
