/**
 * Build-time invite-only switch. Set VITE_REGISTRATION_ENABLED=false for beta.
 * Defaults to enabled so local/prod builds keep public signup.
 */
export const registrationEnabled =
    import.meta.env.VITE_REGISTRATION_ENABLED !== "false";
