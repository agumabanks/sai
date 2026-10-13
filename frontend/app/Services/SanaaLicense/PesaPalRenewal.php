<?php

namespace App\Services\SanaaLicense;

use App\Models\SanaaLicenseTenant;

class PesaPalRenewal
{
    /**
     * Initiate a PesaPal renewal for a tenant.
     *
     * TODO: Connect to PesaPal IPN/callback. On successful payment,
     * call LicensePaymentService::recordPayment() which will extend
     * subscription and reactivate tenant automatically.
     */
    public function initiateRenewal(SanaaLicenseTenant $tenant): array
    {
        return [
            'status' => 'pending',
            'message' => 'PesaPal integration not yet implemented. Phase 2 pending.',
            'tenant_id' => $tenant->id,
        ];
    }

    /**
     * Handle PesaPal callback payload.
     *
     * TODO: Verify PesaPal signature, extract payment details,
     * then call LicensePaymentService::recordPayment().
     */
    public function handleCallback(array $payload): bool
    {
        return false;
    }
}
