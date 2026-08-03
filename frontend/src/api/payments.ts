import {apiClient} from "@/api/api";

export type PaymentTariff = "delo" | "researcher" | "scans_pack" | "ppr";

export type PaymentProvider = "polar" | "nowpayments" | "yukassa";

export interface CheckoutResponse {
    checkout_url: string;
}

export const createCheckout = async (
    tariff: PaymentTariff,
    provider: PaymentProvider = "polar",
): Promise<CheckoutResponse> =>
    (await apiClient.post("/payments/checkout", {tariff, provider})).data;
