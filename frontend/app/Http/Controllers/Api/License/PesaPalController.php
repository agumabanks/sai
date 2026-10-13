<?php

namespace App\Http\Controllers\Api\License;

use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class PesaPalController
{
    /**
     * PesaPal IPN callback endpoint.
     *
     * TODO: Connect to PesaPal IPN/callback. On successful payment,
     * call LicensePaymentService::recordPayment() which will extend
     * subscription and reactivate tenant automatically.
     */
    public function callback(Request $request): JsonResponse
    {
        return response()->json([
            'status' => 'received',
            'message' => 'PesaPal callback stub — Phase 2 implementation pending.',
        ]);
    }
}
