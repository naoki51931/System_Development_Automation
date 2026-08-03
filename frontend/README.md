# SystemNavigator AI frontend

Next.js 16, TypeScript, React, React Hook Form, Zod, local CSS, Vitest, Testing Library, and Playwright. Start separately from FastAPI:

```bash
npm install
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1 npm run dev
npm test
npm run build
npm run test:e2e
```

Use `/login` only with a development backend. Authentication stays in an HttpOnly cookie, not localStorage. The shared client sends credentials and CSRF, times out requests, disables cache, maps safe API errors, and gives 409 conflicts the required Japanese reload guidance. External UI services and production providers are not used.
