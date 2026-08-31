# Communication Style & Example Library

This file is KNOWLEDGE, not system instructions. It contains examples that demonstrate the preferred writing style.

## Style fingerprint
The preferred workplace voice is:
- concise and professional;
- technically precise without unnecessary detail;
- calm when something is blocked or incorrect;
- explicit about action, ownership, dependencies, and status;
- natural enough for Teams;
- lighter and outcome-oriented for managers;
- careful not to speak for application owners or other authoritative teams.

## Example patterns

### 1. Ownership boundary
Input intent:
We do not own this application. The application owner probably has the accurate requirements.

Preferred:
“We don’t own this application, so I think the app owner would be better positioned to confirm the application-specific requirements. I can provide the platform-side details if needed.”

Avoid:
“This isn’t our responsibility. Please ask the app team.”

### 2. Submitted vs completed
Preferred:
“I noticed the document shows the AD group request as complete. The request has been submitted, but it doesn’t appear to be completed yet. Could you please double-check the status?”

### 3. Technical uncertainty
Preferred:
“I’m not completely sure what the new server requires. If it was provisioned against the same design as the existing server, I’d expect the configuration to be consistent, but the server/application owner should confirm the requirement.”

### 4. Need a group chat to avoid fragmented communication
Preferred Teams style:
“Could we create a group chat for this? I’m getting separate messages from different people, and I think keeping the discussion in one place will help us stay aligned and avoid conflicting information.”

### 5. Asking for meeting coverage
Preferred Teams style:
“I’ll be away for this meeting. Would you mind joining on my behalf and sharing any feedback or decisions afterward? Thanks again for backing me up on this.”

### 6. Delay that affected someone else
Preferred:
“Sorry for the delay — I realize this held up your work. The update is now complete. Thanks for your patience.”

### 7. Status update
Preferred:
“Quick update on the mobile CI work:
- iOS CI is working with the current build/publishing flow.
- We’ve integrated the existing re-signing workflow as an interim solution.
- Android integration is next.
- The remaining dependency is [X], so I’ll continue with the items that aren’t blocked in the meantime.”

### 8. Recommendation without overclaiming
Preferred:
“My recommendation would be to use the same AD group name across environments unless there’s a specific requirement to separate them. That should keep the access model simpler and more consistent.”

### 9. Request for confirmation
Preferred:
“Could you confirm which requests we need to submit for the new environment? Once we have that confirmed, I can proceed with the platform-side setup.”

### 10. Manager-facing risk
Preferred:
“The CI work is progressing, but the timeline currently depends on access and signing-related dependencies. I’m continuing with the unblocked items in parallel and will flag anything that changes the delivery estimate.”

## Common transformations

### Verbose → concise

Before:
“Just wanted to reach out to see if maybe you had a chance to take a look at this.”

Preferred:
“Just checking whether you’ve had a chance to review this.”

### Too certain → calibrated

Before:
“The new server uses the same configuration.”

Preferred:
“If the new server was provisioned from the same design, I’d expect the configuration to be consistent.”

### Blaming → neutral

Before:
“They marked it complete even though they didn’t finish it.”

Preferred:
“The document shows the item as complete, but the request still appears to be pending.”

### Weak ask → actionable

Before:
“Please advise.”

Preferred:
“Could you confirm which option we should use so I can proceed with the setup?”

### Overly formal Teams → natural

Before:
“Dear Manny, I am writing to request your assistance…”

Preferred:
“Hey Manny — could you help me with…?”