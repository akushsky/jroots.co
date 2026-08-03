import {createContext, useContext} from "react";

/**
 * Opens the tariffs modal. Provided by ChatPage; the default is a no-op
 * so standalone renders (tests, previews) never crash.
 */
export const PaywallContext = createContext<() => void>(() => {});

export function useOpenPaywall(): () => void {
    return useContext(PaywallContext);
}
