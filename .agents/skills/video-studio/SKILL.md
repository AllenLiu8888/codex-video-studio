---
name: video-studio
description: Turn a script or topic into a branded narrated video in this repository, or resume an existing episode through planning, asset creation, editing, and delivery.
---

# Video Studio

Use this skill from the repository that contains `studio.py`. Its shared references live in that repository; copying this skill folder alone is insufficient.

## Start from the requested stage

Read the root `AGENTS.md`, project state if present, and [workflow](../../../docs/workflow.md). Resolve the user's explicit episode path before any current-episode navigation. Read only the domain section needed in [domain packs](../../../docs/domains.md).

- **Only a topic or idea:** clarify the audience or publishing purpose if it changes the result; otherwise record a reasonable draft assumption. Use the topic-to-script branch in the workflow. A supplied approved script skips this branch.
- **No usable brand:** use the sibling `brand-seed` skill. A character is optional. Existing approved references skip brand design.
- **Script to final film:** initialize a unique episode with `studio.py init`, preserve the submitted original, then follow the stages below through local delivery. A script-only request remains script-only.
- **Revision:** read the existing episode's brief and delivery record, identify the earliest affected stage, preserve its outputs, and rerun only affected work.

## Production

1. Resolve brand, voice, rhythm, music, format and authorization from project defaults plus explicit episode overrides. Freeze inputs. Ask only about a material conflict, new expense outside the agreed scope, or a decision the user reserved.
2. Use `storyboard-director` to produce the semantic shot plan, method choices, actual task prompts and separate voice-direction handoff. Complete plan review before expensive batch generation.
3. Follow [voice and provider guidance](../../../docs/providers.md). Preserve clean narration separately from the actual synthesis request. Obtain an independent rhythm review where available, then synthesize or ingest authorized local audio. Use measured timestamps to determine shot lengths.
4. Produce each shot using its selected method. The image-generation tool is invoked by Codex when available; it is not a hidden feature of the Python renderer. Keep actual prompts, reference roles, outputs and hashes. Use accurate post-production text rather than hoping the image model spells labels correctly.
5. Review real image compositions, set caption boxes, preview with the actual audio, then render using the runtime stages described in `python3 studio.py --help`. `validate` and a placeholder preview do not substitute for image review.
6. Verify the final output and save [delivery](../../../templates/delivery.md), sources, attribution, technical results and any unperformed listening/viewing checks. Local delivery does not imply permission to publish.

## Evidence and fallback

Read [provenance and review](../../../docs/provenance-and-review.md) when saving generation records, reviewing sourced media, or deciding whether a past review still applies. A review record describes a real review; it never exists merely to make a validator pass.

When a required tool is unavailable, continue independent preparation and report the concrete missing capability. A separate main-agent review can be recorded as such if no subagent exists; never invent an independent reviewer. A silent technical demo or an image sheet is not a completed narrated production.

Keep `BRIEF.md` updated with the current stage, exact run, outputs and next action. A new session should resume from these files without access to previous chats.
