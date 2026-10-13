<?php

namespace App\Services\SanaaLicense;

use App\Models\SanaaLicenseEvent;
use App\Models\SanaaLicensePayment;
use App\Models\SanaaLicenseTenant;
use App\Services\SanaaDoctor\WhatsAppNotifier;
use Carbon\Carbon;

class LicensePaymentService
{
    /**
     * Record a manual or automated payment and extend the tenant's subscription.
     */
    public static function recordPayment(
        SanaaLicenseTenant $tenant,
        int $amountUgx,
        string $paymentMethod,
        ?string $reference,
        ?Carbon $paidAt,
        int $extendsByDays,
        string $recordedBy,
        ?string $notes = null
    ): SanaaLicensePayment {
        $paidAt = $paidAt ?? now();

        // Compute new expiry: start from current expiry if still valid, otherwise from now
        $baseDate = $tenant->subscription_ends_at && $tenant->subscription_ends_at->greaterThan(now())
            ? $tenant->subscription_ends_at->copy()
            : now();

        $newEndsAt = $baseDate->copy()->addDays($extendsByDays);

        $payment = new SanaaLicensePayment;
        $payment->id = (string) \Illuminate\Support\Str::uuid();
        $payment->tenant_id = $tenant->id;
        $payment->amount_ugx = $amountUgx;
        $payment->payment_method = $paymentMethod;
        $payment->reference = $reference;
        $payment->paid_at = $paidAt;
        $payment->extends_subscription_by_days = $extendsByDays;
        $payment->new_subscription_ends_at = $newEndsAt;
        $payment->recorded_by = $recordedBy;
        $payment->notes = $notes;
        $payment->save();

        $tenant->subscription_ends_at = $newEndsAt;
        $tenant->status = 'active';
        $tenant->kill_switch_active = false;
        $tenant->save();

        SanaaLicenseEvent::create([
            'id' => (string) \Illuminate\Support\Str::uuid(),
            'tenant_id' => $tenant->id,
            'event_type' => 'payment_recorded',
            'triggered_by' => 'admin',
            'payload' => [
                'payment_id' => $payment->id,
                'amount_ugx' => $amountUgx,
                'method' => $paymentMethod,
                'new_subscription_ends_at' => $newEndsAt->toIso8601String(),
                'recorded_by' => $recordedBy,
            ],
            'created_at' => now(),
        ]);

        $notifier = app(WhatsAppNotifier::class);
        $notifier->sendPaymentConfirmation($tenant, $payment);

        return $payment;
    }
}
