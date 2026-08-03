import {Link} from "react-router-dom";
import {XCircle} from "lucide-react";
import {Button} from "@/components/ui/button";
import {Card, CardContent} from "@/components/ui/card";

export default function PaymentCancel() {
    return (
        <div className="flex justify-center px-4" data-testid="payment-cancel">
            <Card className="max-w-md w-full">
                <CardContent className="p-6 space-y-4 text-center">
                    <XCircle className="w-10 h-10 mx-auto text-muted-foreground" />
                    <h1 className="font-display text-2xl font-semibold">Оплата отменена</h1>
                    <p className="text-sm text-muted-foreground">
                        Ничего не списалось — можно вернуться к исследованию и оформить тариф позже.
                    </p>
                    <div>
                        <Button asChild variant="outline">
                            <Link to="/chat">Назад в чат</Link>
                        </Button>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
