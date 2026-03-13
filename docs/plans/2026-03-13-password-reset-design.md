# Password Reset Feature

## Overview

Add password recovery flow so users who forgot their password can reset it via email link.

## Token Strategy

JWT with expiration + password hash fragment (no DB migration):

- Token payload: `{email, hash_prefix (first 16 chars of hashed_password), exp (1 hour)}`
- Signed with existing `secret_key` / `algorithm` from config
- One-time use: after password changes, `hash_prefix` no longer matches, invalidating the token
- Expiry: 1 hour

## Backend

### New endpoints in `backend/app/routers/auth.py`

**`POST /api/forgot-password`** — accepts `{email}`, rate-limited 3/min

- Always returns 200 (don't reveal whether email exists)
- If user found: generate reset JWT, send email with link `{frontend_url}/reset?token=...`
- Email sent via existing `send_email()` (Resend API)

**`POST /api/reset-password`** — accepts `{token, new_password}`

- Decode JWT, verify `exp` and `hash_prefix` matches current password hash
- Update `hashed_password` with new password
- Return 200 on success

### New functions in `backend/app/services/auth.py`

- `generate_reset_token(user: User) -> str` — JWT with email, hash_prefix, exp
- `verify_reset_token(token: str) -> tuple[str, str]` — returns (email, hash_prefix)

### Schemas in `backend/app/schemas/auth.py`

- `ForgotPasswordRequest(email: str)`
- `ResetPasswordRequest(token: str, new_password: str)`

## Frontend

### New routes in `App.tsx`

- `/forgot-password` → `ForgotPasswordForm`
- `/reset` → `ResetPasswordForm`

### `ForgotPasswordForm.tsx`

- Email input + "Отправить ссылку" button
- On success: "Если этот email зарегистрирован, мы отправили ссылку для сброса пароля"
- Link back to login

### `ResetPasswordForm.tsx`

- Reads `token` from URL query params
- Two password fields (new + confirm) + "Сменить пароль" button
- On success: "Пароль изменён" + redirect to `/login`
- On error (expired/invalid token): show error message

### Login page update

- Add "Забыли пароль?" link below password field, linking to `/forgot-password`

## Security

- `POST /api/forgot-password` rate-limited to 3/min
- Token expires in 1 hour
- Token is one-time-use (hash_prefix invalidation)
- Response always 200 on forgot-password (no email enumeration)
- Password hashed with bcrypt (existing `hash_password()`)

## Email Template

Subject: "Сброс пароля — JRoots"

Simple HTML with reset link button, same style as verification email.
