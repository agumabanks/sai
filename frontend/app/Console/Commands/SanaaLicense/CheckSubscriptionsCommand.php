<?php

namespace App\Console\Commands\SanaaLicense;

use App\Models\SanaaLicenseEvent;
use App\Models\SanaaLicenseTenant;
use App\Services\SanaaDoctor\WhatsAppNotifier;
use Illuminate\Console\Command;

class CheckSubscriptionsCommand extends Command
{
    protected $signature = 'sanaa:license:check';

    protected $description = 'Check all Sanaa License tenants and enforce subscription rules';

    public function handle(): int
    {
        $tenants = SanaaLicenseTenant::with('plan')
            ->where('status', '!=', 'terminated')
            ->get();

        $notifier = app(WhatsAppNotifier::class);

        foreach ($tenants as $tenant) {
            $this->info("Checking {$tenant->tenant_name}...");

            // Trial expired → suspend immediately
            if ($tenant->status === 'trial' && $tenant->trial_ends_at && $tenant->trial_ends_at->isPast()) {
                $tenant->status = 'suspended';
                $tenant->kill_switch_active = true;
                $tenant->save();

                SanaaLicenseEvent::create([
                    'id' => (string) \Illuminate\Support\Str::uuid(),
                    'tenant_id' => $tenant->id,
                    'event_type' => 'killed',
                    'triggered_by' => 'system',
                    'payload' => ['reason' => 'trial_expired'],
                    'created_at' => now(),
                ]);

                $notifier->sendTenantSuspended($tenant);
                $notifier->sendAdminTenantSuspended($tenant);

                continue;
            }

            // Subscription expired, still active → move to grace
            if ($tenant->status === 'active' && $tenant->subscription_ends_at && $tenant->subscription_ends_at->isPast()) {
                $tenant->status = 'grace';
                $tenant->save();

                SanaaLicenseEvent::create([
                    'id' => (string) \Illuminate\Support\Str::uuid(),
                    'tenant_id' => $tenant->id,
                    'event_type' => 'suspended',
                    'triggered_by' => 'system',
                    'payload' => ['reason' => 'subscription_expired', 'grace_days' => $tenant->grace_period_days],
                    'created_at' => now(),
                ]);

                $this->warn("{$tenant->tenant_name} moved to grace.");

                continue;
            }

            // Grace period passed → suspend
            if ($tenant->status === 'grace' && $tenant->isExpired()) {
                $tenant->status = 'suspended';
                $tenant->kill_switch_active = true;
                $tenant->save();

                SanaaLicenseEvent::create([
                    'id' => (string) \Illuminate\Support\Str::uuid(),
                    'tenant_id' => $tenant->id,
                    'event_type' => 'killed',
                    'triggered_by' => 'system',
                    'payload' => ['reason' => 'grace_period_expired'],
                    'created_at' => now(),
                ]);

                $notifier->sendTenantSuspended($tenant);
                $notifier->sendAdminTenantSuspended($tenant);

                continue;
            }

            // Warning: <= 7 days left, active status
            if ($tenant->status === 'active' && $tenant->subscription_ends_at) {
                $daysLeft = $tenant->daysUntilExpiry();
                if ($daysLeft > 0 && $daysLeft <= 7) {
                    $cacheKey = "license_warning_sent:{$tenant->id}:".now()->format('Y-m-d');
                    if (! cache()->has($cacheKey)) {
                        $notifier->sendTenantWarning($tenant, $daysLeft);

                        SanaaLicenseEvent::create([
                            'id' => (string) \Illuminate\Support\Str::uuid(),
                            'tenant_id' => $tenant->id,
                            'event_type' => 'warned',
                            'triggered_by' => 'system',
                            'payload' => ['days_left' => $daysLeft],
                            'created_at' => now(),
                        ]);

                        cache()->put($cacheKey, true, now()->endOfDay());
                    }
                }
            }
        }

        $this->info('Subscription check complete.');

        return self::SUCCESS;
    }
}
