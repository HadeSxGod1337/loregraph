// Public Notion pages — no auth, no backend proxying. Read-only reference +
// a feedback form the user (not Loregraph) owns and moderates.
//
// Two URLs per page: the canonical one (for "open in a new tab") and
// Notion's own `/ebd/<page-id>` embed route, which — unlike the canonical
// URL — actually renders inside a third-party iframe. The canonical page
// sends a frame-ancestors CSP that refuses any outside origin; /ebd/ is
// Notion's dedicated embed endpoint and doesn't. Confirmed by loading both
// directly rather than assumed, since the two behave differently and
// getting this backwards silently breaks the embed.
export const PROJECT_HUB_URL =
  "https://cuddly-wound-d01.notion.site/Loregraph-Project-Hub-3beb5f2fa2828174bc40c243a68b66d9";
export const PROJECT_HUB_EMBED_URL =
  "https://cuddly-wound-d01.notion.site/ebd/3beb5f2fa2828174bc40c243a68b66d9";

export const FEEDBACK_FORM_URL =
  "https://cuddly-wound-d01.notion.site/b8ec78b3f20a4acfb51e4c9057226e1b?pvs=105";
export const FEEDBACK_FORM_EMBED_URL =
  "https://cuddly-wound-d01.notion.site/ebd/b8ec78b3f20a4acfb51e4c9057226e1b";
