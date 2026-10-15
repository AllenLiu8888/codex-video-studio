---
name: storyboard-director
description: Map a narration script to an executable shot plan, choose appropriate visual methods, and prepare a voice-rhythm handoff before branded video production.
---

# Storyboard Director

Read the episode brief, locked narration, frozen brand and production settings. Use [method routing](../../../docs/method-routing.md), the domain-appropriate section of [domain packs](../../../docs/domains.md), and runtime templates for machine-readable fields.

## Plan meaning before assets

1. Divide the script into complete expressions. Label claims, explanations, stories and metaphors where confusing them could mislead. Give each expression a concrete viewer takeaway.
2. Assign shots that cover the full narration in order. Each shot has one main task. Describe the actual subject, state/action, framing, lighting, visual relationship and caption breathing room.
3. Select a method because it expresses that relationship. Static generated illustration is the normal starting point; evidence photographs, labeled science diagrams, comparisons or authorized clips enter when useful. No minimum count or even distribution across methods applies. Motion needs a specific expressive reason and a viable static fallback.
4. Write executable task prompts, reference roles, sources to retrieve, output specifications and fallback for each shot. Keep source, presentation method, palette and camera/editing separate. A generated image of a historical object is an illustration, not historical evidence.
5. Save `visual-plan.json` as the shot-list authority; [storyboard brief](../../../templates/storyboard-brief.md) is its readable rationale. Run the available design validation, then send the original script, plan and task files to a read-only reviewer. Preserve its actual response and fix blocking issues.

## Rhythm handoff

Use [voice direction](../../../docs/providers.md#voice-direction) and [voice-direction brief](../../../templates/voice-direction-brief.md). A voice reviewer checks semantic breath groups, names, numbers and supported provider syntax against the clean original. The final request text and parameter hashes must match what is synthesized.

Estimated durations guide planning only. After narration exists, replace estimates with measured timings in the run's timing plan. Inspect long holds, rushed facts and subtitle reading time before expensive motion or final rendering.

## Completion

Every narrated phrase is covered; methods have a reason; tasks are executable; source-dependent claims have an evidence route; actual composition leaves a readable caption region; unresolved risks have a concrete fallback. Review evidence must bind to the final plan and tasks. A changed plan requires a new relevant review, not an edited old conclusion.
