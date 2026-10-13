<?php

namespace App\Filament\Pages;

use App\Services\SanaaEngineService;
use Filament\Notifications\Notification;
use Filament\Pages\Page;

class FinanceCentralCommand extends Page
{
    protected static ?string $navigationIcon = 'heroicon-o-chart-bar-square';

    protected static ?string $navigationGroup = 'Infrastructure';

    protected static ?int $navigationSort = 11;

    protected static string $view = 'filament.pages.finance-central-command';

    protected static ?string $title = 'Finance Central Command';

    protected static ?string $navigationLabel = 'Finance Monitor';

    // ── State ─────────────────────────────────────────────────────────────────

    public array $overview = [];

    public array $alerts = [];

    public int $tenantCount = 0;

    public string $detailOutput = '';

    public string $activeTab = 'overview';

    public bool $isLoading = false;

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    public function mount(): void
    {
        $this->loadOverview();
    }

    // ── Actions ───────────────────────────────────────────────────────────────

    public function loadOverview(): void
    {
        $this->isLoading = true;
        $engine = app(SanaaEngineService::class);
        $result = $engine->runSkill('finance_monitor', ['action' => 'overview'], 'admin:central_command');

        $this->overview = $result['data']['tenants'] ?? [];
        $this->alerts = $result['data']['alerts'] ?? [];
        $this->tenantCount = $result['data']['tenant_count'] ?? 0;
        $this->isLoading = false;
    }

    public function runCheck(string $action, string $tenant = ''): void
    {
        $this->isLoading = true;
        $this->activeTab = $action;

        $args = ['action' => $action];
        if ($tenant) {
            $args['tenant'] = $tenant;
        }

        $engine = app(SanaaEngineService::class);
        $result = $engine->runSkill('finance_monitor', $args, 'admin:central_command');

        $this->detailOutput = (string) ($result['output'] ?? ($result['error'] ?? 'No data'));
        $this->isLoading = false;

        $success = $result['success'] ?? ($result['data']['success'] ?? null);
        if ($success === true) {
            Notification::make()->title(ucfirst(str_replace('_', ' ', $action)).': All clear')->success()->send();
        } elseif ($success === false) {
            Notification::make()->title(ucfirst(str_replace('_', ' ', $action)).': Issues found')->warning()->send();
        }
    }

    public function fixFailedJobs(): void
    {
        $engine = app(SanaaEngineService::class);
        $result = $engine->runSkill('finance_monitor', ['action' => 'fix_failed_jobs'], 'admin:central_command');

        $this->detailOutput = (string) ($result['output'] ?? ($result['error'] ?? 'No data'));

        Notification::make()
            ->title('Failed jobs retry initiated')
            ->body($this->detailOutput)
            ->success()
            ->send();

        // Refresh overview
        $this->loadOverview();
    }

    public function refreshAll(): void
    {
        $this->detailOutput = '';
        $this->activeTab = 'overview';
        $this->loadOverview();
        Notification::make()->title('Dashboard refreshed')->success()->send();
    }

    // ── Computed ──────────────────────────────────────────────────────────────

    public function getTotalClients(): int
    {
        return array_sum(array_map(fn ($t) => (int) ($t['clients'] ?? 0), $this->overview));
    }

    public function getTotalActiveLoans(): int
    {
        return array_sum(array_map(fn ($t) => (int) ($t['active_loans'] ?? 0), $this->overview));
    }

    public function getTotalArrears(): int
    {
        return array_sum(array_map(fn ($t) => (int) ($t['open_arrears'] ?? 0), $this->overview));
    }

    public function getTotalFailedJobs(): int
    {
        return array_sum(array_map(fn ($t) => (int) ($t['failed_jobs'] ?? 0), $this->overview));
    }

    public function hasAlerts(): bool
    {
        return count($this->alerts) > 0;
    }
}
