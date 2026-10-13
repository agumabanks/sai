<?php

namespace App\Filament\Pages;

use App\Services\SanaaEngineService;
use Filament\Notifications\Notification;
use Filament\Pages\Page;

class PlatformCommandCenter extends Page
{
    protected static ?string $navigationIcon = 'heroicon-o-server-stack';

    protected static ?string $navigationGroup = 'Infrastructure';

    protected static ?int $navigationSort = 10;

    protected static string $view = 'filament.pages.platform-command-center';

    protected static ?string $title = 'Platform Command Center';

    protected static ?string $navigationLabel = 'Platform Monitor';

    // ── State ─────────────────────────────────────────────────────────────────

    public array $serverData = [];

    public array $alerts = [];

    public string $detailOutput = '';

    public string $activePanel = 'overview';

    public bool $isLoading = false;

    public string $serviceTarget = '';

    public string $serviceManager = '';

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
        $result = $engine->runSkill('server_monitor', ['action' => 'overview'], 'admin:platform_command');

        $this->serverData = $result['data'] ?? [];
        $this->alerts = $result['data']['alerts'] ?? [];
        $this->detailOutput = (string) ($result['output'] ?? '');
        $this->isLoading = false;
    }

    public function runMonitor(string $action, string $app = ''): void
    {
        $this->isLoading = true;
        $this->activePanel = $action;

        $args = ['action' => $action];
        if ($app) {
            $args['app'] = $app;
        }

        $engine = app(SanaaEngineService::class);
        $result = $engine->runSkill('server_monitor', $args, 'admin:platform_command');

        $this->detailOutput = (string) ($result['output'] ?? ($result['error'] ?? 'No data'));
        $this->isLoading = false;

        $success = $result['success'] ?? null;
        if ($success === true) {
            Notification::make()->title(ucfirst(str_replace('_', ' ', $action)).': OK')->success()->send();
        } elseif ($success === false) {
            Notification::make()->title(ucfirst(str_replace('_', ' ', $action)).': Issues found')->warning()->send();
        }
    }

    public function manageService(string $action, string $target, string $manager = ''): void
    {
        $this->isLoading = true;

        $args = ['action' => $action, 'target' => $target];
        if ($manager) {
            $args['manager'] = $manager;
        }

        $engine = app(SanaaEngineService::class);
        $result = $engine->runSkill('service_manager', $args, 'admin:platform_command');

        $this->detailOutput = (string) ($result['output'] ?? ($result['error'] ?? 'No data'));
        $this->activePanel = 'service_action';
        $this->isLoading = false;

        $success = $result['success'] ?? null;
        Notification::make()
            ->title(ucfirst($action).': '.$target)
            ->body($success ? 'Completed successfully' : 'Action completed with issues')
            ->{$success ? 'success' : 'warning'}()
            ->send();
    }

    public function renewSSL(string $domain = 'all'): void
    {
        $this->isLoading = true;
        $engine = app(SanaaEngineService::class);
        $result = $engine->runSkill('service_manager', [
            'action' => 'renew_ssl',
            'target' => $domain,
        ], 'admin:platform_command');

        $this->detailOutput = (string) ($result['output'] ?? ($result['error'] ?? 'No data'));
        $this->activePanel = 'ssl_renewal';
        $this->isLoading = false;

        Notification::make()->title('SSL renewal: '.$domain)->success()->send();
    }

    public function clearCache(string $domain): void
    {
        $this->manageService('clear_cache', $domain, 'laravel');
    }

    public function refreshAll(): void
    {
        $this->detailOutput = '';
        $this->activePanel = 'overview';
        $this->loadOverview();
        Notification::make()->title('Platform data refreshed')->success()->send();
    }

    // ── Computed ──────────────────────────────────────────────────────────────

    public function getTotalSites(): int
    {
        return (int) ($this->serverData['enabled_sites'] ?? 0);
    }

    public function getDockerCount(): int
    {
        return (int) ($this->serverData['docker_running'] ?? 0);
    }

    public function getAlertCount(): int
    {
        return count($this->alerts);
    }

    public function getDatabases(): array
    {
        return $this->serverData['databases'] ?? [];
    }

    public function getAppTypes(): array
    {
        return $this->serverData['app_types'] ?? [];
    }

    public function hasAlerts(): bool
    {
        return count($this->alerts) > 0;
    }
}
