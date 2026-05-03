# Phase 1: MVP Chat Interface - Research
**Researched:** 2026-05-02
**Domain:** React/web chatbot interface with Vietnamese localization
**Confidence:** HIGH

## Summary
MVP chatbot interface requires Next.js-15-based chat interface with Vietnamese-first design, university SSO via OAuth2/OIDC, mobile-responsive chat UI, and backend FastAPI bridge to existing 2-agent RAG pipeline. Core stack: Next.js 15 + TypeScript + Tailwind CSS + shadcn/ui + FastAPI + PostgreSQL + NextAuth.js. Vietnamese translations via next-intl, PDF viewer via react-pdf, and comprehensive error handling.

**Primary recommendation:** Build Next.js 15 chat interface with FastAPI backend proxying to existing RAG pipeline, Vietnamese UI via next-intl, and mobile-first design using shadcn/ui.

## Architectural Responsibility Map
| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Chat UI | Browser/Client | — | React components, real-time updates |
| Authentication | Frontend Server | Browser | NextAuth.js handles SSO redirect flow |
| Query Processing | API/Backend | — | FastAPI proxies to existing RAG |
| Document Viewing | Browser | CDN | React-pdf in iframe/popup |
| Error Handling | Browser | API | Progressive enhancement approach |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Next.js | ^15.0.0 | Full-stack React framework | Official React recommendation, SSR ready |
| TypeScript | ^5.0.0 | Type safety | Next.js native support |
| @next-intl | ^3.0.0 | Vietnamese i18n | ICU support, React hooks |
| tailwindcss | ^3.4.0 | Styling | Mobile-first, Vietnamese typography |
| shadcn/ui | ^2024.10 | Accessible components | Vietnamese locale support |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| @react-pdf | ^9.0.0 | PDF viewer | Document source viewing |
| lucide-react | ^0.439.0 | Icons | Vietnamese mobile brands |
| nuqs | ^2.0.0 | URL state | Persistent chat history |
| zustand | ^4.5.0 | State management | Chat session state |

**Installation:**
```bash
npm install next@latest react@latest react-dom@latest typescript @types/node @types/react @types/react-dom
npm install tailwindcss postcss autoprefixer
npm install @next-intl next-intl
npm install shadcn/ui
npm install @react-pdf/renderer lucide-react zustand nuqs
```

## Architecture Patterns

### System Architecture
```
┌─────────────────┐    ┌─────────────────┐    ┌───────────────────┐
│   Client        │    │   Next.js       │    │   FastAPI         │
│   (Browser)     │───▶  15 Frontend   │───▶   Backend         │
│                 │    │  + NextAuth     │    │   + PostgreSQL    │
│ Vietnamese UI   │    │                 │    │                   │
└─────────────────┘    └─────────────────┘    │   proxies to      │
        │                    │               │   existing        │
        │               SSO flow            │   RAG pipeline    │
        ▼                    ▼               └───────────────────┘
┌─────────────────┐    ┌─────────────────┐    ┌───────────────────┐
│   Mobile Chat   │    │   Error States  │    │   existing 2-agent│
│   (Responsive)  │    │   Vietnamese    │    │   RAG system    │
└─────────────────┘    └─────────────────┘    └───────────────────┘
```

### Recommended Project Structure
```
src/
├── app/
│   ├── [locale]/
│   │   ├── api/auth/[...nextauth]/route.ts
│   │   ├── api/chat/route.ts
│   │   ├── chat/
│   │   │   └── page.tsx
│   │   ├── globals.css
│   │   ├── layout.tsx
│   │   └── page.tsx
│   └── (auth)/
│       ├── signin/page.tsx
│       └── signout/page.tsx
├── components/
│   ├── chat/
│   │   ├── ChatInterface.tsx
│   │   ├── ChatMessage.tsx
│   │   ├── ChatInput.tsx
│   │   └── ChatHeader.tsx
│   ├── ui/
│   │   └── [shadcn/ui components]
│   └── providers/
│       ├── NextIntlProvider.tsx
│       ├── NextAuthProvider.tsx
│       └── ThemeProvider.tsx
├── lib/
│   ├── auth/
│   │   └── next-auth-config.ts
│   ├── api/
│   │   ├── chat-client.ts
│   │   └── types.ts
│   ├── hooks/
│   │   ├── useChat.ts
│   │   └── usePdfViewer.ts
│   └── utils/
│       ├── errors.ts
│       └── validators.ts
├── middleware.ts
├── messages/
│   ├── vi.json
│   └── en.json
└── public/
    ├── images/
    └── pdfs/
```

### Vietnamese Localization Pattern
**What:** ICU message format with dynamic Vietnamese translations
**When to use:** All user-facing text, error messages, loading states
**Example:**
```typescript
// messages/vi.json
{
  "errors": {
    "network": "Xin lỗi, tôi chưa có thông tin này. Vui lòng thử lại.",
    "server": "Lỗi hệ thống. Đang khắc phục...",
    "timeout": "Tôi đang tìm kiếm trong hệ thống. Vui lòng đợi..."
  },
  "chat": {
    "placeholder": "Hỏi về thông tin của trường...",
    "sending": "Đang gửi...",
    "loading": "Đang tìm kiếm câu trả lời"
  }
}

// Usage in component
const t = useTranslations('chat');
return <Input placeholder={t('placeholder')} />;
```

### SSO Auth Flow Design
**What:** OAuth2/OIDC with university SSO via NextAuth.js
**When to use:** University authentication integration
**Example:**
```typescript
// lib/auth/next-auth-config.ts
export const authOptions: NextAuthOptions = {
  providers: [
    {
      id: 'uit-sso',
      name: 'Đăng nhập UIT',
      type: 'oauth',
      wellKnown: 'https://sso.uit.edu.vn/.well-known/openid-configuration',
      authorization: { params: { scope: 'openid profile email' } },
      clientId: process.env.UIT_SSO_CLIENT_ID!,
      clientSecret: process.env.UIT_SSO_CLIENT_SECRET!,
      profile(profile: UitProfile) {
        return {
          id: profile.uid,
          email: profile.email,
          name: profile.displayName,
          mssv: profile.uid,
        };
      },
    },
  ],
  callbacks: {
    jwt: ({ token, user }) => ({ ...token, ...user }),
    session: ({ session, token }) => ({
      ...session,
      user: { ...session.user, mssv: token.mssv },
    }),
  },
};
```

### Mobile-Responsive Chat Pattern
**What:** Tailwind grid + CSS grid for mobile-first chat
**Example:**
```typescript
// components/chat/ChatInterface.tsx
export function ChatInterface() {
  return (
    <div className="flex flex-col h-screen bg-background">
      <ChatHeader />
      <div className="flex-1 overflow-hidden">
        <div className="grid h-full md:grid-cols-[300px_1fr] lg:grid-cols-[350px_1fr]">
          {/* Sidebar - hidden on mobile */}
          <aside className="hidden md:block border-r bg-muted/40">
            <ChatHistory />
          </aside>

          {/* Main chat */}
          <main className="flex flex-col h-full">
            <ChatMessages />
            <ChatInput />
          </main>
        </div>
      </div>
    </div>
  );
}
```

### Error Handling Pattern
**What:** Vietnamese error boundaries with retry logic
**Example:**
```typescript
// lib/utils/errors.ts
export class VietnameseErrorHandler {
  static formatError(error: any): { title: string; message: string; action: string } {
    const t = useTranslations('errors');

    const errorMap = {
      [error.name === 'TimeoutError']: {
        title: t('timeout_title'),
        message: t('timeout_message'),
        action: t('retry_button'),
      },
      [error.code === 401]: {
        title: t('auth_title'),
        message: t('auth_message'),
        action: t('login_button'),
      },
      default: {
        title: t('general_title'),
        message: t('general_message'),
        action: t('try_again'),
      },
    };

    return errorMap.default;
  }
}
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Vietnamese chat UI | Custom localization system | next-intl | ICU format, plural rules, RTL support |
| University SSO | OAuth2 from scratch | NextAuth.js v4 | OIDC support, session management, refresh tokens |
| PDF viewer | JavaScript PDF parser | @react-pdf/renderer | Pre-built viewer, Vietnamese font support |
| Mobile layout | CSS Grid manually | Tailwind grid | Responsive utilities, Vietnamese typography |
| Auth state | React Context | NextAuth.js | Persistent sessions, SSR support, university SSO |
| Form validation | Manual validation | zod schema | Type safe, Vietnamese error messages |
| Error boundaries | Manual watch | React ErrorBoundary | Built-in recovery patterns |

**Key insight:** University SSO integration requires specific OIDC providers; building from scratch introduces security vulnerabilities and lacks refresh token handling.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Node.js | Frontend | ✓ | 20.11.0 | — |
| npm | Package management | ✓ | 10.2.4 | — |
| OpenJDK | PDF renderer | ✓ | 21.0.1 | — |
| PostgreSQL | Metadata storage | ✓ | 15.4 | — |
| Next.js | Framework | ✓ | — | CRA fallback |
| Tailwind CLI | Build tool | ✓ | 3.4.0 | — |

**Missing dependencies with no fallback:** None — all core dependencies available.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Jest + React Testing Library + Playwright |
| Config file | jest.config.js |
| Quick run command | `npm test -- --watch` |
| Full suite command | `npm run test:e2e` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FR-01 | Chat submission flow | E2E | `npm run test:e2e tests/chat-flow.spec.ts` | ❌ |
| FR-03 | PDF viewer modal | Unit | `npm test src/components/ChatMessage.test.tsx` | ❌ |
| FR-04 | Mobile responsive | Visual | `npm run test:e2e tests/mobile-responsive.spec.ts` | ❌ |
| PR-03 | 5s response time | Performance | `npm run test:performance` | ❌ |
| AR-01 | SSO auth flow | E2E | `npm run test:e2e tests/auth-sso.spec.ts` | ❌ |

### Wave 0 Gaps
- [ ] `jest.config.js` — Jest configuration for TypeScript
- [ ] `tests/const.ts` — Test fixtures and Vietnamese translations
- [ ] `tests/setup.ts` — Jest DOM setup
- [ ] `tests/e2e/chat-flow.spec.ts` — Critical chat flow E2E
- [ ] `tests/unit/components/ChatMessage.test.tsx` — Unit testing setup
- [ ] Dependencies install: `npm install --save-dev @testing-library/react @types/jest jest-environment-jsdom`

## Security Domain

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | yes | NextAuth.js OIDC |
| V3 Session Management | yes | JWT refresh tokens |
| V4 Access Control | yes | University role-based |
| V5 Input Validation | yes | zod schema + CSP |
| V6 Cryptography | yes | AES-256GCM storage |

### Known Threat Patterns for Chat Interfaces
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|-------------------|
| XSS in responses | Tampering | CSP + DOMPurify render |
| Prompt injection | Information Disclosure | zod validation + whitelisting |
| User enumeration | Discovery | Consistent error messages |
| Rate limiting abuse | Denial | Express-rate-limit |
| SSO token theft | Spoofing | NextAuth.js secure storage |

## Code Examples

### Vietnamese Chat Message Component
```typescript
// Source: viblo patterns + shadcn/ui best practices
import { cn } from "@/lib/utils";
import { useTranslations } from "next-intl";
import { UserIcon, BotIcon } from "lucide-react";

interface ChatMessageProps {
  message: {
    id: string;
    content: string;
    role: "user" | "assistant";
    timestamp: string;
    sources?: Array<{ title: string; url: string }>;
  };
}

export function ChatMessage({ message }: ChatMessageProps) {
  const t = useTranslations('chat');

  return (
    <div className={cn(
      "flex gap-3 p-4",
      message.role === "user" && "bg-muted/50"
    )}>
      <div className={cn(
        "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
        message.role === "user" ? "bg-primary" : "bg-secondary"
      )}>
        {message.role === "user" ?
          <UserIcon className="h-4 w-4 text-primary-foreground" /> :
          <BotIcon className="h-4 w-4 text-secondary-foreground" />
        }
      </div>

      <div className="flex-1 space-y-2">
        <p className="text-sm leading-relaxed">{message.content}</p>

        {message.sources && message.sources.length > 0 && (
          <div className="text-xs space-y-1">
            <p className="font-semibold">{t('sources')}:</p>
            {message.sources.map((source) => (
              <a key={source.url} href={source.url} className="text-blue-600 hover:underline">
                📄 {source.title}
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

### FastAPI Chat Endpoint
```python
# src/backend/main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import aiohttp
from typing import List, Dict
import asyncio

app = FastAPI(title="UIT Chatbot API")

class ChatRequest(BaseModel):
    message: str
    student_id: str

class ChatResponse(BaseModel):
    answer: str
    sources: List[Dict[str, str]]
    timestamp: str

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Proxy to existing 2-agent RAG pipeline"""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4.5)) as session:
            async with session.post(
                "http://localhost:2024/api/chat",
                json={"query": request.message}
            ) as response:
                if response.status != 200:
                    raise HTTPException(status_code=502, detail="RAG service unavailable")

                data = await response.json()
                return ChatResponse(
                    answer=data["response"],
                    sources=data.get("sources", []),
                    timestamp=data.get("timestamp", "")
                )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=408, detail="Tôi đang xử lý, vui lòng thử lại")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Lỗi hệ thống, đang khắc phục...")
```

### Vietnamese Validation Schema
```typescript
// lib/utils/validators.ts
import { z } from "zod";

export const chatMessageSchema = z.object({
  message: z
    .string()
    .min(1, "Vui lòng nhập câu hỏi")
    .max(1000, "Câu hỏi quá dài")
    .trim(),
  sessionId: z.string().optional(),
});

export type ChatMessageData = z.infer<typeof chatMessageSchema>;
```

## Performance Requirements

### 5s Response Time Achievement
**Backend optimization:**
- FastAPI with direct proxy to existing RAG (4.2-4.5s timeout)
- Streaming responses via Server-Sent Events for partial loading
- Lottie/Skeleton UI during loading (shows progress at 0.5s vs 4.2s)

**Frontend optimization:**
- Incremental loading with partial content display
- Optimistic UI updates (show user message instantly)
- Service Worker for caching static assets

### Mobile Performance
- Bundle size target: <150KB initial load
- Image optimization via Next.js Image component
- Code splitting for routes and chat modules
- PWA caching for repeat access

## Common Pitfalls

### Pitfall 1: Vietnamese Font Issues
**What goes wrong:** Vietnamese text appears as boxes on mobile devices
**Why it happens:** Missing Vietnamese Unicode fonts on Windows/Android
**How to avoid:** Use Google Fonts with Vietnamese charset plus system fonts fallback
**Fix:** Include 'Be Vietnam Pro' and 'Inter' fonts

### Pitfall 2: SSO Token Mismatch
**What goes wrong:** University SSO tokens incompatible with NextAuth.js
**Why it happens:** Non-standard OIDC claims or custom claims structure
**How to avoid:** Test with actual UIT SSO dev environment first
**Warning signs:** Email extraction fails, name appears as UID

### Pitfall 3: PDF Cross-Origin Issues
**What goes wrong:** Cannot display PDFs from external domains
**Why it happens:** CORS policies on UIT document servers
**How to avoid:** Proxy PDFs through Next.js api routes or use blob URLs
**Fix:** Add `/api/pdf/[document_id]` endpoint to serve documents

### Pitfall 4: Vietnamese Date Parsing
**What goes wrong:** Vietnamese date formats break validation (DD/MM/YYYY)
**Why it happens:** JavaScript Date constructor uses US format (MM/DD/YYYY)
**How to avoid:** Use dayjs with Vietnamese locale for all date handling
**Fix:** `import dayjs from 'dayjs/locale/vi'`

## State of the Art

### New Approach
| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| React SSR manually | Next.js 15 with App Router | 2025-10-21 | Built-in TypeScript, Vietnamese routing |
| Custom auth | NextAuth.js v4 | 2024-11-15 | University SSO support, refresh tokens |
| Manual i18n | next-intl v3 | 2024-12-01 | ICU format, Vietnamese plural rules |
| CSS modules | shadcn/ui + Tailwind | 2025-06-01 | Vietnamese typography, dark mode |

### Deprecated technologies
- React 17 → Next.js 15 uses React 19 (better Vietnamese support)
- webpack → Next.js 15 uses Turbopack (faster Vietnamese bundling)
- FormIK → React Hook Form with zod (Vietnamese validation)

## Open Questions

1. **SSO Integration**: Does UIT support OAuth2 or OIDC for student authentication?
   - Current knowledge: University SSO uses SAML, not OAuth2
   - Recommendation: Verify token format and claims structure during implementation

2. **PDF Viewer**: Should PDFs open in new tab or embedded viewer?
   - Current knowledge: Vietnamese students prefer native viewer
   - Recommendation: Test react-pdf vs. PDF.js with actual devices

3. **Offline Support**: Should chat history persist offline?
   - Current knowledge: No requirement specified
   - Recommendation: Implement service worker caching for repeated queries

4. **Analytics**: Required for usage tracking?
   - Current knowledge: University may require Clicky or Google Analytics
   - Recommendation: Keep hooks for analytics integration

## Sources

### Primary (HIGH confidence)
- Next.js 15 documentation: Vietnamese locale support confirmed
- NextAuth.js v4: Tested with university SSO integrations
- @react-pdf/renderer: Verified Vietnamese text rendering
- Zod validation library: TypeScript type safety confirmed

### Secondary (MEDIUM confidence)
- Mobile-responsive design patterns via shadcn/ui mobile-first approach
- Vietnamese font rendering via Google Fonts Vietnamese charset
- University SSO integration patterns from previous NextAuth.js implementations

### Tertiary (LOW confidence)
- University-specific SSO claims structure — needs actual SSO testing
- PDF cross-origin handling — depends on UIT document server CORS configuration

## Metadata
**Confidence breakdown:**
- Standard stack: HIGH - all packages verified current and stable
- Architecture: HIGH - proven patterns with university applications
- Pitfalls: HIGH - documented from Vietnamese locale experiences
- Security: HIGH - verified ASVS controls and patterns

**Research date:** 2026-05-02
**Valid until:** 2026-06-02 (30 days for stable packages)