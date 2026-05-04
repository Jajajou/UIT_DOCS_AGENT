# PLAN-auth-pages

**Goal**: Create premium, "Perfect Pixel" Login and Signup pages that match the new "Future Tech" design system.

## Context
- **Current State**: No auth pages; `App.tsx` has only Dashboard routes.
- **Design System**: Glassmorphism, `Outfit` font, Tailwind v4, specific color palette (`index.css`).
- **Tech Stack**: React 19, React Router, Lucide Icons, Framer Motion.

## 1. Architecture & Layout
Create a dedicated `AuthLayout` to avoid showing the Sidebar/Header on auth pages.

-   **New Layout**: `src/components/layout/AuthLayout.tsx`
    -   Full-screen dynamic background (gradient/animated).
    -   Centered "Glass" card container.
    -   `Outlet` for switching between Login/Signup.

## 2. Components (Premium UI)
Implement reusable form components with validation states.

-   **Input Component**: Floating labels or clean specific borders with focus rings.
-   **Button Component**: Primary (Brand Gradient) and Secondary (Social Login).
-   **Social Auth**: Google/GitHub buttons (visual only for now).

## 3. Pages
### `src/pages/auth/Login.tsx`
-   Email & Password fields.
-   "Remember me" & "Forgot Password?" links.
-   Link to Signup.

### `src/pages/auth/Signup.tsx`
-   Name, Email, Password, Confirm Password.
-   "Terms of Service" checkbox.
-   Link to Login.

## 4. Routing
Update `App.tsx` to include the new layout and routes.

```tsx
<Route element={<AuthLayout />}>
    <Route path="/login" element={<Login />} />
    <Route path="/signup" element={<Signup />} />
</Route>
```

## 5. Agent Assignments
-   **Designer**: Ensure pure glassmorphism consistency.
-   **Developer**: Implement `AuthLayout`, Pages, and Route configuration.

## 6. Verification
-   [ ] Verify `/login` renders without Sidebar.
-   [ ] Verify `/signup` renders.
-   [ ] Test navigation between Login/Signup.
-   [ ] Check responsive behavior on mobile.
