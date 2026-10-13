<?php

namespace App\Filament\Widgets;

use App\Models\SanaaLicenseEvent;
use App\Models\SanaaLicensePayment;
use App\Models\SanaaLicenseTenant;
use Filament\Notifications\Notification;
use Filament\Widgets\Widget;
use Illuminate\Support\Facades\Auth;

class SanaaLicenseOverviewWidget extends Widget
{
    protected static string $view = 'filament.widgets.sanaa-license-overview-widget';

    protected static ?string $pollingInterval = '60s';

    protected static bool $isLazy = false;

    protected int|string|array $columnSpan = 'full';

    public int $totalTenants = 0;

    public int $activeTenants = 0;

    public int $expiringThisWeek = 0;

    public int $suspendedTenants = 0;

    public array $expiringTenants = [];

    public function mount(): void
    {
        $this->refreshData();
    }

    public function refreshData(): void
    {
        $this->totalTenants = SanaaLicenseTenant::count();

        $this->activeTenants = SanaaLicenseTenant::whereIn('status', ['active', 'trial'])
            ->where('kill_switch_active', false)
            ->count();

        $this->expiringThisWeek = SanaaLicenseTenant::where('subscription_ends_at', '<=', now()->addDays(7))
            ->whereIn('status', ['active', 'trial', 'grace'])
            ->count();

        $this->suspendedTenants = SanaaLicenseTenant::whereIn('status', ['suspended', 'terminated'])
            ->count();

        $this->expiringTenants = SanaaLicenseTenant::query()
            ->with('plan')
            ->where('subscription_ends_at', '<=', now()->addDays(7))
            ->whereIn('status', ['active', 'trial', 'grace'])
            ->orderBy('subscription_ends_at')
            ->limit(10)
            ->get()
            ->map(fn (SanaaLicenseTenant $tenant) => [
                'id' => $tenant->id,
                'tenant_name' => $tenant->tenant_name,
                'plan_name' => $tenant->plan?->name ?? '—',
                'subscription_ends_at' => $tenant->subscription_ends_at,
                'days_left' => $tenant->daysUntilExpiry(),
                'status' => $tenant->status,
                'status_color' => $tenant->statusBadgeColor(),
            ])
            ->toArray();
    }

    public function quickRecordPayment(string $tenantId): void
    {
        $tenant = SanaaLicenseTenant::find($tenantId);

        if (! $tenant) {
            Notification::make()
                ->title('Tenant not found')
                ->danger()
                ->send();

            return;
        }

        $plan = $tenant->plan;
        $amount = $plan?->price_ugx ?? 0;
        $days = $plan?->billing_cycle_days ?? 30;

        $newEndsAt = $tenant->subscription_ends_at
            ? $tenant->subscription_ends_at->copy()->addDays($days)
            : now()->addDays($days);

        $payment = SanaaLicensePayment::create([
            'tenant_id' => $tenant->id,
            'amount_ugx' => $amount,
            'payment_method' => 'cash',
            'reference' => 'Quick payment from dashboard',
            'paid_at' => now(),
            'extends_subscription_by_days' => $days,
            'new_subscription_ends_at' => $newEndsAt,
            'recorded_by' => Auth::user()?->name ?? 'Admin',
            'notes' => 'Recorded via License Overview widget',
        ]);

        $tenant->update([
            'subscription_ends_at' => $newEndsAt,
            'status' => 'active',
        ]);

        SanaaLicenseEvent::create([
            'tenant_id' => $tenant->id,
            'event_type' => 'payment_recorded',
            'triggered_by' => 'admin',
            'payload' => [
                'payment_id' => $payment->id,
                'amount_ugx' => $payment->amount_ugx,
                'extends_by_days' => $payment->extends_subscription_by_days,
            ],
            'created_at' => now(),
        ]);

        try {
            app(\App\Services\SanaaDoctor\WhatsAppNotifier::class)->sendPaymentConfirmation($tenant, $payment);
        } catch (\Throwable $e) {
            // Method may not exist; fail silently.
        }

        Notification::make()
            ->title('Payment recorded for '.$tenant->tenant_name)
            ->success()
            ->send();

        $this->refreshData();
    }
}
