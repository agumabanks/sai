<?php

namespace App\Services\SanaaDoctor;

use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class WhatsAppNotifier
{
    protected string $token;

    protected string $number;

    public function __construct()
    {
        $this->token = env('FONNTE_TOKEN', '');
        $this->number = env('WHATSAPP_ALERT_NUMBER', '0706272481');
    }

    /**
     * Send a critical alert via WhatsApp.
     *
     * @param  array{diagnosis: string, recommended_action: string}  $diagnosis
     * @param  array<int, string>  $flags
     */
    public function sendCriticalAlert(string $app, array $diagnosis, int $score, array $flags): void
    {
        $message = sprintf(
            "🚨 SANAA DOCTOR ALERT\nApp: %s\nScore: %d/100\nStatus: CRITICAL\nIssue: %s\nAction: %s\nTime: %s",
            $app,
            $score,
            $diagnosis['diagnosis'] ?? 'Unknown',
            $diagnosis['recommended_action'] ?? 'Investigate immediately',
            now()->toDateTimeString()
        );

        $this->send($message);
    }

    /**
     * Send the daily health digest via WhatsApp.
     *
     * @param  array<int, array{app: string, name: string, score: int, status: string}>  $summaries
     */
    public function sendDailyDigest(array $summaries): void
    {
        $lines = [];
        $lines[] = '📊 SANAA DAILY HEALTH REPORT — '.now()->format('Y-m-d');
        $lines[] = '';

        $healthy = 0;
        $degraded = 0;
        $critical = 0;

        foreach ($summaries as $summary) {
            $emoji = match ($summary['status']) {
                'healthy' => '✅',
                'degraded' => '⚠️',
                'critical' => '🚨',
                default => '❓',
            };

            $lines[] = sprintf('%s %s: %d/100 — %s', $emoji, $summary['name'], $summary['score'], $summary['status']);

            match ($summary['status']) {
                'healthy' => $healthy++,
                'degraded' => $degraded++,
                'critical' => $critical++,
                default => null,
            };
        }

        $lines[] = '';
        $lines[] = sprintf('%d apps healthy | %d degraded | %d critical', $healthy, $degraded, $critical);
        $lines[] = '';
        $lines[] = 'Powered by SanaaDoctor @ ai.sanaa.co';

        $this->send(implode("\n", $lines));
    }

    /**
     * Send a tenant subscription warning.
     */
    public function sendTenantWarning(\App\Models\SanaaLicenseTenant $tenant, int $daysLeft): void
    {
        $message = sprintf(
            '⚠️ %s — your Sanaa Finance subscription expires in %d days. Please renew to avoid interruption. Contact: 0706272481',
            $tenant->tenant_name,
            $daysLeft
        );

        $this->send($message, $tenant->contact_phone);
    }

    /**
     * Send a tenant suspension notice.
     */
    public function sendTenantSuspended(\App\Models\SanaaLicenseTenant $tenant): void
    {
        $message = sprintf(
            '⚠️ %s — your Sanaa Finance subscription has expired and your account has been suspended. To reactivate, please contact Sanaa on 0706272481',
            $tenant->tenant_name
        );

        $this->send($message, $tenant->contact_phone);
    }

    /**
     * Notify admin that a tenant was suspended.
     */
    public function sendAdminTenantSuspended(\App\Models\SanaaLicenseTenant $tenant): void
    {
        $message = sprintf(
            '🔴 TENANT SUSPENDED: %s | Plan: %s | Expired: %s | Contact: %s',
            $tenant->tenant_name,
            $tenant->plan?->name ?? 'Unknown',
            $tenant->subscription_ends_at?->toDateString() ?? 'N/A',
            $tenant->contact_phone
        );

        $this->send($message);
    }

    /**
     * Send payment confirmation to tenant.
     */
    public function sendPaymentConfirmation(\App\Models\SanaaLicenseTenant $tenant, \App\Models\SanaaLicensePayment $payment): void
    {
        $message = sprintf(
            '✅ %s — your payment of UGX %s has been received. Subscription extended until %s. Thank you for choosing Sanaa Finance.',
            $tenant->tenant_name,
            number_format($payment->amount_ugx),
            $tenant->subscription_ends_at?->toDateString() ?? 'N/A'
        );

        $this->send($message, $tenant->contact_phone);
        $this->send("📥 Payment recorded for {$tenant->tenant_name}: UGX ".number_format($payment->amount_ugx));
    }

    /**
     * Send tenant reactivation notice.
     */
    public function sendTenantReactivated(\App\Models\SanaaLicenseTenant $tenant): void
    {
        $message = sprintf(
            '✅ %s — your Sanaa Finance subscription has been reactivated. Access is restored. Expires: %s. Contact: 0706272481',
            $tenant->tenant_name,
            $tenant->subscription_ends_at?->toDateString() ?? 'N/A'
        );

        $this->send($message, $tenant->contact_phone);
    }

    /**
     * Execute the HTTP POST to Fonnte.
     */
    protected function send(string $message, ?string $overrideNumber = null): void
    {
        $target = $overrideNumber ?? $this->number;

        if (empty($this->token)) {
            Log::warning('WhatsAppNotifier: FONNTE_TOKEN is not set. Message not sent.', ['message' => $message, 'target' => $target]);

            return;
        }

        try {
            $response = Http::withHeaders([
                'Authorization' => $this->token,
            ])
                ->timeout(30)
                ->asForm()
                ->post('https://api.fonnte.com/send', [
                    'target' => $target,
                    'message' => $message,
                ]);

            if (! $response->successful()) {
                Log::warning('WhatsAppNotifier: Fonnte API error', [
                    'status' => $response->status(),
                    'body' => $response->body(),
                ]);
            }
        } catch (\Exception $e) {
            Log::error('WhatsAppNotifier: Exception sending message', ['error' => $e->getMessage()]);
        }
    }
}
