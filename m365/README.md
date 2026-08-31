# M365 Copilot Workplace Communication Agent — Setup & Usage Guide

## What this package is
This package is designed for a Microsoft 365 Copilot declarative agent / Agent Builder agent that drafts and improves Outlook emails and Teams messages in your established workplace voice.

The agent is separated into:
- Instructions
- Knowledge / examples
- Starter Prompts

The main `agent-instructions.md` file is the behavioral instruction set.

The `communication-style-examples.md` file is optional knowledge/example material.

## Recommended setup

1. Open Microsoft 365 Copilot.
2. Choose New agent.
3. Choose Skip to configure if available.
4. Name the agent:

Workplace Communication Copilot

5. Description:

Drafts and optimizes concise, professional Outlook emails and Teams messages for technical, project, and cross-team communication in a senior Platform/DevOps engineering voice.

6. Copy `agent-instructions.md` into Instructions.

7. Add `communication-style-examples.md` as Knowledge if supported.

8. Add Starter Prompts.

9. Test the agent before using it for real communications.

## Suggested Starter Prompts

### Optimize Teams message
Make this Teams message concise, natural, and professional. Preserve the meaning and technical details:

[paste message]

### Draft technical email
Draft a concise technical email from these points. Make the action, ownership, and dependencies clear:

[paste points]

### Manager update
Turn this into a manager-friendly status update. Focus on outcome, risk, dependencies, and next steps:

[paste update]

### Clarify ownership
Rewrite this so I clearly explain that our team does not own the application without sounding defensive:

[paste message]

### Follow up
Draft a polite but direct follow-up. Make the requested action clear:

[paste context]

### Make it more concise
Shorten this while keeping the senior/professional tone and all important facts:

[paste message]

### Review before sending
Review this message for unclear ownership, unsupported assumptions, accidental commitments, tone, and unnecessary wording:

[paste message]

### Reply to colleague
Write a natural Teams reply to this message. Keep it friendly and concise:

[paste conversation]

## Daily usage

### Quick Teams message

Teams: Ask Manny to join the meeting while I'm away, give feedback, and update me afterward.

### Technical ownership

Email: We don't own this app. Someone is asking us to confirm the server requirements. Explain that the app owner should confirm application requirements, but we can provide platform details.

### Status update

Manager update: iOS CI completed; re-signing workflow integrated as interim solution; Android next; waiting for access dependency.

### Improve my draft

Optimize this. Keep my meaning, don't add new commitments, and make it sound natural for Teams:

[paste message]

### Tone overrides

You can add:

- more technical
- more concise
- executive-friendly
- slightly more casual
- firmer but still professional
- less formal

## Recommended workflow

Use the agent as an editor rather than an autonomous sender.

1. Give it the actual context.
2. Tell it Teams or Email.
3. Tell it the audience when relevant.
4. Include facts, ownership, deadlines, and dependencies.
5. Let it generate the draft.
6. Check technical facts and commitments.
7. Send after review.

## Continuous improvement

For 2–4 weeks, collect cases where:

- you significantly changed the generated wording;
- the agent sounded too formal;
- the agent sounded too soft;
- the agent was too verbose;
- it misunderstood ownership;
- it removed important technical detail;
- it created an unsupported commitment;
- the generated message was especially good.

Record:

Context
→ Agent Draft
→ Final Version Sent
→ Why I Changed It

When the same correction occurs at least three times, consider turning it into an instruction.

## Example

If Copilot repeatedly writes:

“We need the application team to confirm this.”

But you repeatedly change it to:

“I think the app owner would be better positioned to confirm this.”

Add or strengthen an instruction about collaborative ownership language.

## Example library

Continue expanding `communication-style-examples.md` with examples for:

- Manager updates
- Technical clarification
- Access requests
- Follow-ups
- Blockers
- Dependencies
- Ownership boundaries
- Disagreement/correction
- Apologies
- Meeting coverage
- Thank-you messages
- Casual colleague replies

## Versioning

Recommended:

v1.0
Initial communication profile.

v1.1
Tone and wording improvements.

v1.2
Ownership and dependency improvements.

v2.0
Major workflow, audience-profile, or knowledge changes.

Maintain a simple changelog:

Date | Version | Problem Observed | Change | Result

## Security

Do not store:
- passwords;
- tokens;
- private keys;
- production secrets;
- customer information;
- confidential information that is unnecessary for teaching communication style.

Anonymize internal examples when the exact names, server names, ticket IDs, or other identifiers are not needed.