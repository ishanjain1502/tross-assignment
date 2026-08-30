┌─────────────────────────────────────────────────────────────────────┐
│                        AUTHENTICATION FLOW                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. GET https://www.linkedin.com/                                   │
│     ↓                                                                │
│     Returns: JSESSIONID cookie (contains CSRF token)                 │
│     Returns: li_at cookie (if previously logged in)                  │
│                                                                      │
│  2. Extract CSRF Token                                               │
│     ↓                                                                │
│     From JSESSIONID cookie value (after the pipe character)          │
│     OR from page meta tag                                            │
│                                                                      │
│  3. POST https://www.linkedin.com/uas/authenticate                  │
│     Headers:                                                         │
│       X-CSRF-Token: {csrf_token}                                     │
│       X-Requested-With: XMLHttpRequest                               │
│     Body: session_key={email}&session_password={password}            │
│            &csrfToken={csrf_token}                                   │
│     ↓                                                                │
│     Returns: li_at cookie (main auth token, ~6 month validity)       │
│              JSESSIONID (refreshed)                                  │
│                                                                      │
│  4. Subsequent API Calls                                             │
│     Headers:                                                         │
│       Cookie: li_at={token}; JSESSIONID={session}                    │
│       X-CSRF-Token: {from JSESSIONID}                                │
│       X-Restli-Protocol-Version: 2.0.0                               │
│       X-Li-Track: {"clientVersion":"3.0.0",...}                      │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘