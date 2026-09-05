# Authentication & Session Management Patterns for AI Browser Agents on Job Portals

**Research Date:** 2026-08-25
**Sources:** BrowserUse docs, WorkOS, Skyvern, BrowserStack, CloakBrowser, Browserless, pyotp, keyring, n8n, BrowserAct, AIHawk, Playwright official docs, community discussions.

---

## 1. Session Persistence Patterns

### Cookie Storage & Reuse (Browser Profiles)

| Pattern | Mechanism | Pros | Cons |
|---------|-----------|------|------|
| **Persistent Context** | `launch_persistent_context(user_data_dir=...)` saves cookies, localStorage, cache, IndexedDB to disk | Survives restarts, no re-login needed, fast startup | Single-thread only, stale locks, sensitive data on disk |
| **Storage State JSON** | `context.storage_state(path='auth.json')` exports/restores cookies + localStorage as JSON | Portable, shareable, version-controllable | No cache/IndexedDB, manual save triggers needed |
| **Cookie Syncing** | Export cookies from real browser → inject into agent browser | Instant auth, works cross-machine | Fragile (cookies expire), security concern if leaked |
| **Profile Cloning** | Copy entire Chrome profile directory | Full state preservation | Large, platform-specific paths, lock conflicts |

**CareerGraph Current State:** Uses `data/browser_profile/` as persistent context dir via `BrowserManager`. Already has stealth injection, lock cleanup, and anti-detection flags.

**Recommendation:**
- Keep persistent context as primary (fast path for repeat applications)
- Add `storage_state` export as backup/transfer mechanism
- Store `auth.json` snapshots with timestamps to detect staleness

### localStorage/sessionStorage Persistence

- **Persistent context** automatically persists both `localStorage` and `sessionStorage` across runs
- **Storage state export** captures `localStorage` but NOT `sessionStorage` (session-scoped by design)
- Some sites store auth tokens in `localStorage` (e.g., JWT-based SPAs) - these survive via persistent context
- Service workers cache API tokens in IndexedDB - only persistent context captures this

**Implementation:**
```python
# Export full state including localStorage
state = context.storage_state(path="data/artifacts/auth_state.json")

# On restore, merge with persistent context
context = playwright.chromium.launch_persistent_context(
    user_data_dir="data/browser_profile",
    storage_state="data/artifacts/auth_state.json"  # overlays localStorage
)
```

### Expired Session Detection

**Pre-flight validation (before starting application):**
```python
async def validate_session(context: BrowserContext) -> bool:
    """Check if session is still authenticated before starting work."""
    page = context.pages[0] if context.pages else await context.new_page()

    # Navigate to a protected resource
    response = await page.goto("https://target-site.com/settings")

    # Check for redirect to login page
    if "login" in page.url or "signin" in page.url:
        return False

    # Check for auth-specific DOM elements
    try:
        await page.wait_for_selector("[data-testid='user-avatar']", timeout=5000)
        return True
    except:
        return False
```

**Key signals of expired sessions:**
1. Redirect to login/SSO page (URL pattern match)
2. HTTP 401/403 responses
3. Missing auth cookies (check `context.cookies()`)
4. DOM indicators: login form visible, user menu absent
5. Token expiry timestamps in localStorage

**Recommendation:** Add a `SessionValidator` class to CareerGraph that:
1. Reads cookie expiry timestamps before each submission
2. Validates auth by hitting a known protected endpoint
3. Returns `AuthState { valid, expired_at, reauth_needed }` enum

### Playwright Persistent Context vs Fresh Context

| Aspect | Persistent Context | Fresh Context |
|--------|-------------------|---------------|
| **Startup time** | Fast (skip login) | Slow (full login flow) |
| **Concurrency** | ❌ Single instance (file lock) | ✅ Parallel-safe |
| **State leakage** | Risk of stale sessions | Clean every time |
| **Anti-detection** | Looks like real user (history, cookies) | Suspicious (no history) |
| **Memory** | Grows over time | Bounded |
| **Failure recovery** | Complex (state corruption risk) | Simple (start fresh) |
| **Best for** | Sequential job applications | High-volume parallel runs |

**CareerGraph Recommendation:** Hybrid approach:
- **Persistent context** for the submission pipeline (sequential, anti-detection matters)
- **Fresh context** for evaluation/scraping (parallel, no auth needed)
- **Fallback chain:** Try persistent → if session expired → fresh context → login → re-persist

---

## 2. Login Flow Handling

### LinkedIn

**Auth flow:** Email/password → 2FA (SMS/TOTP/authenticator) → checkpoint challenges
- **Checkpoint challenges:** LinkedIn detects unusual login attempts and triggers "Is this you?" verification (photo recognition, device confirmation, email code)
- **Rate limiting:** Aggressive bot detection; flags automated login patterns
- **Easy Apply:** Uses LinkedIn session directly; no separate OAuth for applications

**Handling strategy:**
1. Use persistent context to maintain login across runs (LinkedIn sessions last ~30 days)
2. On checkpoint challenge → pause + HITL Telegram approval (photo/device verification is hard to automate)
3. Inject realistic delays (1-5s between steps, random mouse movements)
4. Rotate user agents and viewport sizes to avoid fingerprinting
5. Store `li_at` cookie as primary session token

**Anti-detection specifics:**
- `navigator.webdriver` must be `undefined` (already in CareerGraph stealth script)
- Disable `AutomationControlled` blink feature (already in CareerGraph)
- Add realistic `navigator.plugins` array (already in CareerGraph)
- Rotate screen resolution and WebGL renderer strings

### Indeed

**Auth flow:** Email/password → phone verification (SMS code)
- Indeed enforces phone verification at login and application time
- Non-fixed VoIP numbers are rejected
- Phone verification required per-session on new devices

**Handling strategy:**
1. Persistent context maintains device fingerprint → fewer verification prompts
2. SMS OTP → extract via Gmail API (if forwarded to email) or Telegram relay
3. "Indeed Apply" on employer sites often bypasses Indeed login entirely
4. Consider Indeed's API if available for direct application submission

### Workday

**Auth flow:** Corporate SSO (SAML 2.0 / OAuth 2.0) → identity provider redirect
- Workday is SSO-gated; each employer has their own IdP configuration
- Supports both SP-initiated and IdP-initiated flows
- Common IdPs: Microsoft Entra ID (Azure AD), Okta, PingFederate, CyberArk

**Handling strategy:**
1. **Corporate SSO is the hardest to automate** - each employer has different IdP
2. Pre-authenticate via the corporate IdP and persist the SAML assertion cookies
3. Workday sessions are typically 8-12 hours; persist `wday_vps_cookie`
4. For "Apply" on Workday-hosted career sites, many don't require login (public forms)
5. For authenticated Workday access: use OAuth On-Behalf-Of flow if IdP supports it

**CareerGraph Current:** Has `adapters/workday.py` and `adapters/workday_agentic.py` - likely handles public Workday career site forms.

### Greenhouse / Lever / Ashby

**Auth flow:** Usually NO login required - public application forms
- These ATS platforms host career pages as public portals
- Application submission is unauthenticated (name, email, resume upload)
- Some have "Save for later" via email, but no persistent login needed

**Handling strategy:**
1. No auth handling needed for application submission
2. Focus on form filling accuracy and file upload reliability
3. CareerGraph's `adapters/greenhouse.py`, `adapters/lever.py`, `adapters/ashby.py` already handle this

### "Is This You?" Security Challenges

| Site | Challenge Type | Automation Difficulty | Strategy |
|------|---------------|----------------------|----------|
| LinkedIn | Photo recognition / device confirm | 🔴 Hard | HITL approval via Telegram |
| LinkedIn | Email verification code | 🟡 Medium | Gmail API extraction |
| Indeed | SMS phone code | 🟡 Medium | Telegram relay or email forward |
| Google | Device prompt / security key | 🔴 Hard | Avoid; use pre-authenticated session |
| Workday | IdP MFA prompt | 🔴 Hard | Pre-authenticate, persist SAML cookie |
| Generic ATS | Email confirmation link | 🟢 Easy | Gmail API click-through |

---

## 3. 2FA/MFA Strategies

### TOTP Automation (pyotp)

**How it works:** Store the TOTP shared secret (base32-encoded) → generate codes programmatically

```python
import pyotp

class TOTPAutomator:
    """Generate TOTP codes for automated 2FA."""

    def __init__(self, secrets: Dict[str, str]):
        """
        Args:
            secrets: Map of service_name -> base32_secret
                     e.g., {"linkedin": "JBSWY3DPEHPK3PXP"}
        """
        self.totps = {
            name: pyotp.TOTP(secret) for name, secret in secrets.items()
        }

    def get_code(self, service: str) -> str:
        """Generate current 6-digit TOTP code for service."""
        if service not in self.totps:
            raise ValueError(f"No TOTP secret configured for {service}")
        return self.totps[service].now()

    def get_provisioning_uri(self, service: str) -> str:
        """Get otpauth:// URI for QR code generation (initial setup)."""
        return self.totps[service].provisioning_uri(
            name=f"careergraph-{service}",
            issuer_name="CareerGraph"
        )
```

**Setup flow:**
1. During initial manual login, capture the TOTP secret from the authenticator app's `otpauth://` URI
2. Store the base32 secret in the encrypted credential vault (keyring)
3. On subsequent automated logins, generate codes with `pyotp.TOTP(secret).now()`
4. Handle clock skew: `pyotp.TOTP(secret, interval=30, digits=6)` - default matches Google Authenticator

**Security consideration:** The TOTP secret is equivalent to having the authenticator app. Store in OS keyring, NOT in plaintext env vars.

### SMS Relay (Telegram Bot Forwarding)

**Architecture:**
```
Target Site sends SMS → Phone receives SMS → SMS forwarding app →
Telegram Bot API → CareerGraph receives code → Injects into browser
```

**Implementation options:**
1. **Android SMS Forwarding App** → Telegram Bot (e.g., "SMS to Telegram" apps on Play Store)
2. **Twilio/Vonage virtual number** → webhook → extract OTP → forward to agent
3. **Physical phone + ADB** → `adb shell content query --uri content://sms/inbox` → parse

**Telegram relay pattern:**
```python
# On the phone: SMS forwarding app sends to Telegram bot
# In CareerGraph: Poll for OTP messages
class SMSRelayReceiver:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot = Bot(token=bot_token)
        self.chat_id = chat_id

    async def wait_for_otp(self, timeout: int = 120) -> str:
        """Wait for SMS OTP forwarded via Telegram."""
        start = time.time()
        while time.time() - start < timeout:
            updates = await self.bot.get_updates(offset=self._last_offset)
            for update in updates:
                text = update.message.text
                # Extract 6-digit code from message
                match = re.search(r'\b(\d{6})\b', text)
                if match:
                    return match.group(1)
            await asyncio.sleep(2)
        raise TimeoutError("SMS OTP not received within timeout")
```

### Email OTP Extraction (Gmail API)

**Pattern:**
```python
from googleapiclient.discovery import build
import base64, re

class GmailOTPExtractor:
    def __init__(self, credentials):
        self.service = build('gmail', 'v1', credentials=credentials)

    async def extract_otp(self, sender_filter: str, subject_contains: str,
                          timeout: int = 60) -> str:
        """Poll Gmail for OTP email and extract code."""
        start = time.time()
        query = f"from:{sender_filter} subject:{subject_contains} is:unread"

        while time.time() - start < timeout:
            results = self.service.users().messages().list(
                userId='me', q=query, maxResults=1
            ).execute()

            if results.get('messages'):
                msg = self.service.users().messages().get(
                    userId='me', id=results['messages'][0]['id']
                ).execute()
                body = self._decode_body(msg)
                # Extract 4-8 digit code
                match = re.search(r'\b(\d{4,8})\b', body)
                if match:
                    # Mark as read to avoid re-extraction
                    self.service.users().messages().modify(
                        userId='me', id=msg['id'],
                        body={'removeLabelIds': ['UNREAD']}
                    ).execute()
                    return match.group(1)

            await asyncio.sleep(5)  # Poll interval
        raise TimeoutError("OTP email not found")
```

**Note:** Gmail API may not surface all third-party verification emails (some are filtered). IMAP fallback is more reliable for this use case.

### Backup Codes Storage

- Most services provide 8-10 single-use backup codes during 2FA setup
- Store encrypted in keyring: `keyring.set_password("backup-codes", "linkedin", json.dumps(codes))`
- Use as last resort when TOTP generator and SMS relay both fail
- Track which codes have been consumed

### HITL (Human-in-the-Loop) Approval

**When to escalate to human:**
- Photo/device recognition challenges (LinkedIn checkpoint)
- Unrecognized login location warnings
- CAPTCHA that can't be solved programmatically
- Any "Is this you?" prompt with visual verification
- First-time login on a new device/browser profile

**CareerGraph already has Telegram integration** (`TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` in config).

**HITL flow:**
```python
class HITLApproval:
    """Pause automation and wait for human approval via Telegram."""

    async def request_approval(self, challenge_type: str, context: dict) -> bool:
        """Send challenge details to Telegram and await human response."""
        message = (
            f"🔐 Auth Challenge: {challenge_type}\n"
            f"Site: {context.get('site')}\n"
            f"Action: {context.get('action')}\n"
            f"Screenshot: {context.get('screenshot_path', 'N/A')}\n\n"
            f"Reply 'approve' to continue or 'deny' to abort."
        )
        await self.telegram_bot.send_message(self.chat_id, message)

        # Wait for human response (with timeout)
        response = await self._wait_for_telegram_reply(timeout=300)
        return response.lower() in ('approve', 'yes', 'continue')
```

**CareerGraph HITL Recommendation:**
- Use existing Telegram bot integration for auth challenge escalation
- Include screenshot of the challenge page
- Provide inline buttons: [Approve] [Deny] [View Screenshot]
- Auto-abort after 5 minutes if no response

---

## 4. OAuth/SSO Complexity

### "Apply with LinkedIn" Button Handling

**How it works:**
1. Employer career page embeds LinkedIn's OAuth widget
2. User clicks "Apply with LinkedIn" → redirected to `linkedin.com/oauth/v2/authorize`
3. LinkedIn checks for existing session → if logged in, shows consent screen
4. User approves → LinkedIn redirects back to employer ATS with auth code
5. ATS exchanges code for profile data (name, email, experience)

**Automation strategy:**
- If LinkedIn session is active in persistent context → button click triggers OAuth redirect → auto-approve consent screen
- Consent screen detection: look for "Allow" / "Authorize" button on LinkedIn OAuth page
- The `sdsc` cookie from LinkedIn controls whether sign-in button appears on career pages

**Risks:** LinkedIn actively monitors for automated "Easy Apply" patterns. Rate limit to ~20-30 applications/hour with randomized delays.

### Google SSO for Job Applications

**Pattern:** Some ATS platforms support "Sign in with Google"
- Similar OAuth2 flow: redirect to `accounts.google.com/o/oauth2/v2/auth`
- Google checks for existing session → consent screen → redirect back
- Persistent Google session in browser profile enables auto-login

**Automation:** If Google account is logged in persistent context, SSO just works. Maintain a separate Google login in the browser profile.

### Corporate SSO (Workday, ADP)

**Key insight:** Corporate SSO is employer-specific and cannot be generically automated.

**Strategies:**
1. **For public career sites:** Most Workday/ADP career portals don't require login to apply
2. **For internal employee portals:** Requires pre-authentication with corporate credentials
3. **SAML assertion caching:** Pre-authenticate via IdP, cache the SAML response cookie
4. **OAuth OBO flow:** If the IdP supports OAuth On-Behalf-Of, use service credentials

**Recommendation for CareerGraph:**
- Focus on public career site applications (no auth needed)
- For authenticated portals: HITL approval + pre-authenticated browser session
- Store SSO session cookies per-employer in the credential vault

### OAuth Consent Flow Automation

```python
async def handle_oauth_consent(page: Page, provider: str) -> bool:
    """Auto-approve OAuth consent screens for known providers."""
    consent_patterns = {
        "linkedin": {"url": "linkedin.com/oauth", "button": "Allow"},
        "google": {"url": "accounts.google.com", "button": "Continue"},
        "microsoft": {"url": "login.microsoftonline.com", "button": "Accept"},
    }

    pattern = consent_patterns.get(provider)
    if not pattern:
        return False

    if pattern["url"] in page.url:
        try:
            await page.click(f"button:has-text('{pattern['button']}')", timeout=5000)
            return True
        except:
            return False
    return False
```

---

## 5. Credential Management

### Secure Storage Options

| Method | Platform Support | Security Level | Complexity |
|--------|-----------------|----------------|------------|
| **Python `keyring`** | Win/macOS/Linux (OS native) | 🔒 High | Low |
| **HashiCorp Vault** | Cross-platform | 🔒🔒 Very High | High |
| **`.env` + encryption** | Any | 🟡 Medium | Low |
| **Environment variables** | Any | 🟡 Medium (visible in process list) | Low |
| **SQLite + AES** | Any | 🔒 High | Medium |
| **`data/browser_profile/`** | CareerGraph current | 🟡 Low (plaintext on disk) | Already built |

### Recommended: Python `keyring` + Per-Site Mapping

```python
import keyring
from dataclasses import dataclass

SERVICE_PREFIX = "careergraph"

@dataclass
class SiteCredential:
    site: str           # e.g., "linkedin", "indeed", "workday-acme"
    username: str
    password: str
    totp_secret: Optional[str] = None
    backup_codes: Optional[List[str]] = None
    last_verified: Optional[float] = None

class CredentialVault:
    """Per-site credential storage using OS keyring."""

    def store(self, cred: SiteCredential) -> None:
        service = f"{SERVICE_PREFIX}:{cred.site}"
        keyring.set_password(service, "username", cred.username)
        keyring.set_password(service, "password", cred.password)
        if cred.totp_secret:
            keyring.set_password(service, "totp_secret", cred.totp_secret)
        if cred.backup_codes:
            keyring.set_password(service, "backup_codes", json.dumps(cred.backup_codes))

    def retrieve(self, site: str) -> Optional[SiteCredential]:
        service = f"{SERVICE_PREFIX}:{site}"
        username = keyring.get_password(service, "username")
        if not username:
            return None
        return SiteCredential(
            site=site,
            username=username,
            password=keyring.get_password(service, "password") or "",
            totp_secret=keyring.get_password(service, "totp_secret"),
            backup_codes=json.loads(keyring.get_password(service, "backup_codes") or "[]"),
        )

    def list_sites(self) -> List[str]:
        """List all configured credential sites."""
        # keyring doesn't support listing; maintain a registry
        registry = keyring.get_password(SERVICE_PREFIX, "_registry")
        return json.loads(registry) if registry else []
```

### Session Sharing Across Automation Runs

- **Persistent context directory** (`data/browser_profile/`) is the session sharing mechanism
- Store a `session_metadata.json` alongside the profile:
```json
{
  "linkedin": {
    "last_login": "2026-08-25T10:30:00Z",
    "cookie_expiry": "2026-09-25T10:30:00Z",
    "session_valid": true
  },
  "indeed": {
    "last_login": "2026-08-24T15:00:00Z",
    "cookie_expiry": "2026-08-31T15:00:00Z",
    "session_valid": true
  }
}
```

---

## 6. How Existing Tools Handle Auth

### AIHawk

- **Approach:** Cookie-based session reuse via persistent browser profile
- **Mechanism:** User logs into LinkedIn manually once → AIHawk reuses the browser session
- **2FA handling:** Relies on existing session; no active 2FA automation
- **Risk:** Session expiry mid-run causes silent failures
- **Source:** [GitHub - Jobs_Applier_AI_Agent_AIHawk](https://github.com/feder-cr/jobs_applier_ai_agent_aihawk)

### Browser Use

- **Approach:** Multi-layered auth support with profile sync + credential injection + 2FA automation
- **Mechanism:**
  1. `Browser.from_system_chrome()` inherits existing browser sessions
  2. `export_storage_state('auth.json')` saves cookies + localStorage
  3. `sensitive_data` parameter injects credentials without exposing to vision model
  4. TOTP via `SECRET_KEY` suffix in sensitive_data dictionary
- **2FA:** `Agent(task='...', sensitive_data={'x_bu_2fa_code': 'TOTP_SECRET'})` auto-generates TOTP
- **HITL:** Cloud-hosted profiles with approval gates for sensitive actions
- **Source:** [BrowserUse Authentication Docs](https://docs.browser-use.com/open-source/customize/browser/authentication)

### CareerGraph Current

- **Approach:** Persistent Playwright context via `BrowserManager`
- **Mechanism:** `data/browser_profile/` directory with Chromium user data
- **Stealth:** Custom init script + `playwright-stealth` library
- **Anti-detection:** `--disable-blink-features=AutomationControlled`, fake plugins/languages
- **Missing:** No session validation, no 2FA automation, no credential vault, no HITL escalation
- **Source:** `src/pipeline/4_submission/browser_manager.py`

### Comparison Matrix

| Feature | AIHawk | Browser Use | CareerGraph |
|---------|--------|-------------|-------------|
| Session persistence | ✅ Cookie reuse | ✅ Profile + storage state | ✅ Persistent context |
| Credential vault | ❌ Env vars only | ✅ Sensitive data injection | ❌ Not implemented |
| TOTP automation | ❌ | ✅ pyotp built-in | ❌ Not implemented |
| HITL escalation | ❌ | ✅ Cloud approval gates | 🟡 Telegram exists, not wired to auth |
| Session validation | ❌ | ✅ Pre-flight checks | ❌ Not implemented |
| Anti-detection | 🟡 Basic | ✅ Stealth profiles | ✅ Good (stealth script) |
| OAuth handling | 🟡 LinkedIn only | 🟡 Consent auto-approve | ❌ Not implemented |
| Failure recovery | ❌ Abort on failure | ✅ Checkpoint + resume | 🟡 Circuit breakers exist |

---

## 7. Failure Recovery

### Session Expires Mid-Application

**Detection:**
```python
async def detect_auth_redirect(page: Page) -> bool:
    """Detect if we've been redirected to a login page."""
    login_indicators = ["login", "signin", "auth", "sso", "challenge"]
    current_url = page.url.lower()
    return any(indicator in current_url for indicator in login_indicators)
```

**Response protocol:**
1. **Pause** current application step
2. **Screenshot** the current page (for diagnostics and HITL)
3. **Classify** the failure: session expired vs. checkpoint challenge vs. CAPTCHA
4. **Attempt auto-recovery** if TOTP credentials available
5. **Escalate to HITL** if challenge is visual/complex
6. **Checkpoint** progress (which step, which form fields completed)

### Checkpoint and Resume Strategy

**CareerGraph already has LangGraph checkpointing** - leverage this for auth failures.

**Recommended pattern:**
```python
# After each major step, save state
checkpoint = {
    "job_id": job_id,
    "site": "greenhouse",
    "step": "resume_upload",  # semantic milestone, not DOM state
    "completed_fields": {"name": True, "email": True, "resume": False},
    "auth_state": "valid",
    "page_url": page.url,
    "timestamp": datetime.utcnow().isoformat(),
}
# Store in LangGraph state or SQLite recall memory

# On resume after auth failure:
# 1. Re-authenticate (fresh login or restore session)
# 2. Navigate to checkpoint page_url
# 3. Re-fill completed fields (from checkpoint data)
# 4. Continue from checkpoint.step
```

**Key insight from BrowserUse docs:** Don't checkpoint raw DOM interactions - checkpoint *semantic goals* (e.g., "resume uploaded", "cover letter filled"). DOM structures change between sessions, but business-level milestones are stable.

### Alerting on Auth Failures

```python
class AuthFailureAlert:
    """Escalation chain for authentication failures."""

    async def alert(self, failure: AuthFailure) -> None:
        if failure.severity == "critical":
            # Immediate Telegram alert
            await self.telegram.send(
                f"🚨 AUTH FAILURE: {failure.site}\n"
                f"Error: {failure.message}\n"
                f"Job: {failure.job_id}\n"
                f"Action required: Manual login needed"
            )
        elif failure.severity == "warning":
            # Log + batch notification
            logger.warning("Auth degradation: %s on %s", failure.message, failure.site)
            await self.telegram.send(
                f"⚠️ Auth warning: {failure.site} - {failure.message}"
            )

        # Always record in recall memory
        self.recall.record_auth_event(failure)
```

**Alert triggers:**
- Session expired (cookie age > expected lifetime)
- Login redirect detected mid-flow
- 2FA challenge not resolvable automatically
- 3 consecutive failed login attempts
- CAPTCHA that can't be solved after 2 retries

---

## Implementation Recommendations for CareerGraph

### Priority 1: Session Validation Layer
Add `SessionValidator` to `BrowserManager` that checks auth state before each submission:
- Cookie expiry timestamp check
- Protected endpoint probe
- Session metadata tracking in `data/browser_profile/session_metadata.json`

### Priority 2: Credential Vault
Implement `CredentialVault` using Python `keyring`:
- Per-site credential isolation
- TOTP secret storage for automated 2FA
- Integration point for existing Telegram HITL

### Priority 3: Auth Failure Recovery
Wire LangGraph checkpoint to auth state:
- On auth failure: save semantic checkpoint → attempt re-auth → resume
- On unrecoverable challenge: HITL escalation via existing Telegram bot
- Circuit breaker integration: 3 auth failures = abort pipeline, alert operator

### Priority 4: 2FA Automation Stack
Layer the 2FA strategies by priority:
1. **TOTP** (pyotp) - fastest, most reliable, for services that support it
2. **Email OTP** (Gmail API) - for services that email codes
3. **SMS Relay** (Telegram forwarding) - for SMS-only services
4. **HITL** (Telegram approval) - fallback for visual challenges

### Priority 5: OAuth Consent Automation
Handle "Apply with LinkedIn" and similar OAuth flows:
- Auto-detect OAuth redirect pages
- Auto-approve consent for whitelisted providers
- Track OAuth token lifetimes per employer

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                  CareerGraph Pipeline                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ Stage 4  │───▶│ Auth Gateway │───▶│ Browser      │  │
│  │ Submitter│    │              │    │ Manager      │  │
│  └──────────┘    └──────┬───────┘    └──────────────┘  │
│                         │                               │
│              ┌──────────┼──────────┐                    │
│              ▼          ▼          ▼                    │
│  ┌──────────────┐ ┌──────────┐ ┌──────────────┐       │
│  │ Session      │ │Credential│ │ 2FA          │       │
│  │ Validator    │ │ Vault    │ │ Automator    │       │
│  │ (pre-flight) │ │(keyring) │ │(pyotp/gmail) │       │
│  └──────┬───────┘ └──────────┘ └──────┬───────┘       │
│         │                              │                │
│         ▼                              ▼                │
│  ┌──────────────┐              ┌──────────────┐        │
│  │ Checkpoint   │              │ HITL         │        │
│  │ & Resume     │◀─────────────│ Escalation   │        │
│  │ (LangGraph)  │              │ (Telegram)   │        │
│  └──────────────┘              └──────────────┘        │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## Sources

- [BrowserUse Authentication](https://browser-use.com/posts/web-agent-authentication)
- [BrowserUse Docs - Browser Authentication](https://docs.browser-use.com/open-source/customize/browser/authentication)
- [WorkOS - Logging AI Agents into Web Apps](https://workos.com/blog/logging-ai-agents-into-web-apps)
- [Skyvern - Browser Automation Session Management 2026](https://www.skyvern.com/blog/browser-automation-session-management/)
- [Skyvern - Error Handling in Browser Automation](https://www.skyvern.com/blog/error-handling-in-browser-automation/)
- [Skyvern - Browser Automation Security Best Practices](https://www.skyvern.com/blog/browser-automation-security-best-practices/)
- [BrowserStack - Playwright Persistent Context](https://www.browserstack.com/guide/playwright-persistent-context)
- [Playwright Official - Authentication](https://playwright.dev/docs/auth)
- [Playwright Official - BrowserContext](https://playwright.dev/docs/api/class-browsercontext)
- [CloakBrowser - Browser Automation in Production](https://cloakbrowser.dev/blog/browser-automation-in-production)
- [Browserless - Session Management](https://www.browserless.io/blog/session-management)
- [GitHub Discussion - Session Persistence in Long-Running Agents](https://github.com/browser-use/browser-use/discussions/4226)
- [pyotp Documentation](https://pyauth.github.io/pyotp/)
- [Keyring Documentation](https://keyring.readthedocs.io/)
- [BrowserAct - LinkedIn 2FA Setup](https://www.browseract.com/blog/how-to-set-up-linkedin-two-factor-authentication-in-browseract)
- [n8n Community - MFA Input in Browser Agent](https://community.n8n.io/t/browser-agent-automation-with-mfa-input-is-it-possible-to-continue-actions-after-user-enters-otp/145905)
- [Reddit - OTP/2FA for AI Agents](https://www.reddit.com/r/AI_Agents/comments/1rb0ilb/otp_2fa_for_ai_agents/)
- [AIHawk GitHub](https://github.com/feder-cr/jobs_applier_ai_agent_aihawk)
- [Gmail API OTP Extraction Guide](https://medium.com/@surozb/seamless-email-based-otp-verification-using-gmail-api-e2f2cf9124a8)
- [Workday SSO Tutorial - Microsoft Entra ID](https://learn.microsoft.com/en-us/entra/identity/saas-apps/workday-tutorial)
- [Indeed Phone Verification](https://www.indeed.com/help/job-seekers/articles/34540805299085-phone-verification-issues-basic-troubleshooting)
