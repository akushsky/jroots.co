export interface ChatErrorDisplay {
    text: string;
    /** Show the «Оформить тариф» button under the error. */
    paywallAction: boolean;
}

/**
 * Map a backend error code (from {detail: {code, message}}) to the chat UI.
 * Returns null for unknown/missing codes — caller falls back to the generic message.
 */
export function chatErrorForCode(code: string | null): ChatErrorDisplay | null {
    switch (code) {
        case "free_sessions_limit":
            return {
                text: "Бесплатные сессии на сегодня закончились. Продолжите завтра или оформите тариф.",
                paywallAction: true,
            };
        case "daily_budget":
            return {
                text: "Бесплатный лимит на сегодня исчерпан.",
                paywallAction: true,
            };
        case "rate_limited":
            return {
                text: "Слишком много запросов. Подождите немного и попробуйте ещё раз.",
                paywallAction: false,
            };
        case "generating":
            return {
                text: "Ответ ещё готовится. Подождите немного и попробуйте ещё раз.",
                paywallAction: false,
            };
        default:
            return null;
    }
}

export const GENERIC_SEND_ERROR = "Не удалось отправить сообщение. Попробуйте ещё раз.";
export const GENERIC_SESSION_ERROR = "Не удалось создать поиск. Попробуйте ещё раз.";
