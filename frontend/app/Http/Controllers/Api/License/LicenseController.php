<?php

namespace App\Http\Controllers\Api\License;

use App\Models\SanaaLicenseEvent;
use App\Models\SanaaLicenseTenant;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\RateLimiter;

class LicenseController
{
    public function check(Request $request): JsonResponse
    {
        if ($this->rateLimitExceeded($request)) {
            return $this->genericError(429);
        }

        $validated = $request->validate([
            'tenant_key' => 'required|string',
            'license_token' => 'required|string',
        ]);

        $tenant = SanaaLicenseTenant::with('plan')
            ->where('tenant_key', $validated['tenant_key'])
            ->first();

        if (! $tenant || ! $tenant->verifyLicenseToken($validated['license_token'])) {
            return $this->genericError(401);
        }

        $tenant->last_checked_at = now();
        $tenant->save();

        SanaaLicenseEvent::create([
            'id' => (string) \Illuminate\Support\Str::uuid(),
            'tenant_id' => $tenant->id,
            'event_type' => 'checked',
            'triggered_by' => 'api',
            'payload' => ['endpoint' => 'check'],
            'created_at' => now(),
        ]);

        $daysUntilExpiry = $tenant->daysUntilExpiry();
        $allowed = $tenant->isAccessAllowed();
        $warning = null;
        $message = null;

        if ($tenant->kill_switch_active) {
            $allowed = false;
            $message = 'Account suspended. Contact 0706272481';
        } elseif ($tenant->isExpired()) {
            $allowed = false;
            $message = 'Your subscription has expired. Please contact support on 0706272481';
        } elseif ($tenant->isInGrace()) {
            $graceDays = (int) now()->diffInDays($tenant->subscription_ends_at->copy()->addDays($tenant->grace_period_days), false);
            $warning = "Your subscription has expired. Grace period: {$graceDays} days remaining. Contact 0706272481 to renew.";
        } elseif ($daysUntilExpiry > 0 && $daysUntilExpiry <= 7) {
            $warning = "Your subscription expires in {$daysUntilExpiry} days. Contact Sanaa Finance to renew.";
        }

        return response()->json([
            'allowed' => $allowed,
            'status' => $tenant->status,
            'tenant_name' => $tenant->tenant_name,
            'plan' => $tenant->plan ? [
                'name' => $tenant->plan->name,
                'features' => $tenant->plan->features ?? [],
                'max_members' => $tenant->plan->max_members,
                'max_tellers' => $tenant->plan->max_tellers,
                'max_loans_active' => $tenant->plan->max_loans_active,
            ] : null,
            'subscription_ends_at' => $tenant->subscription_ends_at?->toIso8601String(),
            'days_until_expiry' => $daysUntilExpiry,
            'warning' => $warning,
            'kill_switch_active' => $tenant->kill_switch_active,
            'message' => $message,
        ]);
    }

    public function ping(Request $request): JsonResponse
    {
        if ($this->rateLimitExceeded($request)) {
            return $this->genericError(429);
        }

        $validated = $request->validate([
            'tenant_key' => 'required|string',
            'license_token' => 'required|string',
        ]);

        $tenant = SanaaLicenseTenant::where('tenant_key', $validated['tenant_key'])->first();

        if (! $tenant || ! $tenant->verifyLicenseToken($validated['license_token'])) {
            return $this->genericError(401);
        }

        $tenant->last_checked_at = now();
        $tenant->save();

        return response()->json([
            'alive' => $tenant->isAccessAllowed(),
        ]);
    }

    protected function rateLimitExceeded(Request $request): bool
    {
        $key = 'license-api:'.$request->ip();

        return RateLimiter::tooManyAttempts($key, 60);
    }

    protected function genericError(int $status): JsonResponse
    {
        return response()->json([
            'error' => 'Invalid credentials or request.',
        ], $status);
    }
}
