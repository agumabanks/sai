<?php

namespace App\Filament\Pages;

use App\Services\SanaaEngineService;
use App\Services\TenantProvisioningRunService;
use Filament\Notifications\Notification;
use Filament\Pages\Page;
use Illuminate\Support\Facades\Process;

class TenantProvisioning extends Page
{
    protected static ?string $navigationIcon = 'heroicon-o-server-stack';

    protected static ?string $navigationGroup = 'Infrastructure';

    protected static ?int $navigationSort = 10;

    protected static string $view = 'filament.pages.tenant-provisioning';

    protected static ?string $title = 'Tenant Provisioning';

    protected static ?string $navigationLabel = 'Tenants';

    // ── Form state ────────────────────────────────────────────────────────────

    public string $domain = '';

    public string $appName = '';

    public string $source = '/var/www/finance';

    public string $dbSource = 'finance';

    public bool $wipeTenantData = true;

    public bool $skipCert = false;

    public string $adminPhone = '';

    public string $adminPassword = '';

    // ── Page state ────────────────────────────────────────────────────────────

    public array $tenants = [];

    public array $availableSources = [];

    public string $provisionLog = '';

    public string $statusOutput = '';

    public bool $isRunning = false;

    public ?array $lastResult = null;

    public ?string $currentRunId = null;

    public string $runState = 'idle';

    public bool $runNotified = false;

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    public function mount(): void
    {
        $this->loadTenants();
        $this->detectSources();

        $runId = session('tenant_provisioning_run_id');
        if (is_string($runId) && $runId !== '') {
            $this->currentRunId = $runId;
            $this->refreshProvisionRun();
        }
    }

    // ── Data loading ──────────────────────────────────────────────────────────

    public function loadTenants(): void
    {
        $engine = app(SanaaEngineService::class);
        $result = $engine->runSkill('tenant_provisioning', [
            'action' => 'list',
        ]);

        $this->tenants = $result['data']['tenants'] ?? [];
    }

    /**
     * Auto-detect available source tenants by scanning /var/www for mbalala dirs.
     */
    public function detectSources(): void
    {
        $this->availableSources = [];
        $base = '/var/www';

        // Always include the canonical template first
        if (is_dir("{$base}/finance/mbalala")) {
            $this->availableSources[] = [
                'path' => '/var/www/finance',
                'label' => 'finance (template)',
                'db' => 'finance',
            ];
        }

        // Add active tenants as possible clone sources
        foreach ($this->tenants as $tenant) {
            $path = $tenant['path'] ?? '';
            if ($path && is_dir("{$path}/mbalala") && $path !== '/var/www/finance') {
                $this->availableSources[] = [
                    'path' => $path,
                    'label' => $tenant['domain'] ?? basename($path),
                    'db' => $tenant['app_name'] ?? basename($path),
                ];
            }
        }
    }

    public function refreshData(): void
    {
        $this->loadTenants();
        $this->detectSources();
        $this->statusOutput = '';
        Notification::make()->title('Tenant list refreshed')->success()->send();
    }

    // ── Source selection sync ─────────────────────────────────────────────────

    public function updatedSource(): void
    {
        // Auto-sync DB source when clone source changes
        foreach ($this->availableSources as $src) {
            if ($src['path'] === $this->source) {
                $this->dbSource = $src['db'];
                break;
            }
        }
    }

    // ── Provision a new tenant ────────────────────────────────────────────────

    public function provisionTenant(): void
    {
        if ($this->isRunning) {
            Notification::make()
                ->title('Provisioning already in progress')
                ->body('Wait for the current tenant run to finish.')
                ->warning()
                ->send();

            return;
        }

        $domain = $this->normalizeDomainInput($this->domain);
        $this->domain = $domain;

        if (empty($domain)) {
            Notification::make()
                ->title('Domain is required')
                ->body('Enter a domain like newsite.sanaa.ug')
                ->danger()
                ->send();

            return;
        }

        if (! preg_match('/^[a-z0-9\-]+\.sanaa\.(ug|co)$/', $domain)) {
            Notification::make()
                ->title('Invalid domain format')
                ->body('Must match <name>.sanaa.ug or <name>.sanaa.co')
                ->danger()
                ->send();

            return;
        }

        // Check if already in the tenant list
        foreach ($this->tenants as $t) {
            if (($t['domain'] ?? '') === $domain && ($t['enabled'] ?? false)) {
                Notification::make()
                    ->title('Tenant already exists')
                    ->body("{$domain} is already active.")
                    ->warning()
                    ->send();

                return;
            }
        }

        $this->isRunning = true;
        $this->provisionLog = "Starting provisioning for {$domain}...\n";
        $this->statusOutput = '';
        $this->lastResult = null;
        $this->runState = 'queued';
        $this->runNotified = false;

        $args = [
            'action' => 'provision',
            'domain' => $domain,
            'source' => $this->source,
            'db_source' => $this->dbSource,
            'wipe_tenant_data' => $this->wipeTenantData,
            'skip_cert' => $this->skipCert,
        ];

        if (! empty($this->appName)) {
            $args['app_name'] = strtolower(trim($this->appName));
        }
        if (! empty($this->adminPhone)) {
            $args['admin_phone'] = trim($this->adminPhone);
        }
        if (! empty($this->adminPassword)) {
            $args['admin_password'] = $this->adminPassword;
        }

        $runService = app(TenantProvisioningRunService::class);
        $run = $runService->create($args, [
            'domain' => $domain,
            'url' => "https://{$domain}",
            'app_name' => $args['app_name'] ?? explode('.', $domain)[0] ?? '',
        ]);

        $this->currentRunId = (string) ($run['id'] ?? '');
        $this->hydrateProvisionRun($run);
        session(['tenant_provisioning_run_id' => $this->currentRunId]);

        try {
            Process::path(base_path())->start([
                PHP_BINARY,
                'artisan',
                'tenant:provision-run',
                $this->currentRunId,
            ]);

            Notification::make()
                ->title("Provisioning '{$domain}' started")
                ->body('The run is now continuing in the background. This page will update automatically.')
                ->success()
                ->duration(10000)
                ->send();
        } catch (\Throwable $e) {
            $runService->fail($this->currentRunId, $e->getMessage());
            $this->refreshProvisionRun();

            Notification::make()
                ->title('Failed to start provisioning')
                ->body($e->getMessage())
                ->danger()
                ->duration(10000)
                ->send();
        }
    }

    public function refreshProvisionRun(): void
    {
        if (! $this->currentRunId) {
            return;
        }

        $run = app(TenantProvisioningRunService::class)->get($this->currentRunId);

        if (! $run) {
            $this->currentRunId = null;
            $this->isRunning = false;
            $this->runState = 'missing';
            $this->lastResult = null;
            $this->provisionLog = '';
            session()->forget('tenant_provisioning_run_id');

            return;
        }

        $wasRunning = $this->isRunning;
        $this->hydrateProvisionRun($run);

        if ($this->isRunning || ! $wasRunning || $this->runNotified) {
            return;
        }

        $this->runNotified = true;
        session()->forget('tenant_provisioning_run_id');

        $success = (bool) ($this->lastResult['success'] ?? false);
        $url = (string) ($this->lastResult['data']['url'] ?? ($run['data']['url'] ?? ''));
        $domain = (string) ($run['data']['domain'] ?? '');

        if ($success) {
            $this->domain = '';
            $this->appName = '';
            $this->adminPhone = '';
            $this->adminPassword = '';
            $this->loadTenants();
            $this->detectSources();

            Notification::make()
                ->title($domain !== '' ? "Tenant '{$domain}' is LIVE!" : 'Tenant is LIVE!')
                ->body($url !== '' ? $url : 'Provisioning completed successfully.')
                ->success()
                ->duration(10000)
                ->send();
        } else {
            Notification::make()
                ->title('Provisioning failed')
                ->body((string) ($this->lastResult['error'] ?? 'The run finished with an error.'))
                ->danger()
                ->duration(10000)
                ->send();
        }
    }

    private function normalizeDomainInput(string $value): string
    {
        $value = strtolower(trim($value));

        if ($value === '') {
            return '';
        }

        if (! str_contains($value, '://') && str_contains($value, '/')) {
            $value = 'https://'.ltrim($value, '/');
        }

        if (str_contains($value, '://')) {
            $host = parse_url($value, PHP_URL_HOST);
            if (is_string($host) && $host !== '') {
                $value = strtolower($host);
            }
        }

        $value = trim($value, " \t\n\r\0\x0B./");

        if (str_starts_with($value, 'www.')) {
            $value = substr($value, 4);
        }

        return $value;
    }

    // ── Tenant actions ────────────────────────────────────────────────────────

    public function checkStatus(string $domain): void
    {
        $this->statusOutput = "Checking {$domain}...\n";

        $engine = app(SanaaEngineService::class);
        $result = $engine->runSkill('tenant_provisioning', [
            'action' => 'status',
            'domain' => $domain,
        ]);

        $this->statusOutput = (string) ($result['output'] ?? ($result['error'] ?? 'No data'));

        if ($result['success'] ?? false) {
            Notification::make()->title("{$domain}: All checks passed")->success()->send();
        } else {
            Notification::make()->title("{$domain}: Issues detected")->warning()->send();
        }
    }

    public function disableTenant(string $domain): void
    {
        $engine = app(SanaaEngineService::class);
        $result = $engine->runSkill('tenant_provisioning', [
            'action' => 'disable',
            'domain' => $domain,
        ]);

        if ($result['success'] ?? false) {
            Notification::make()->title("{$domain} disabled")->success()->send();
            $this->loadTenants();
        } else {
            Notification::make()
                ->title("Failed to disable {$domain}")
                ->body((string) ($result['error'] ?? ''))
                ->danger()
                ->send();
        }
    }

    public function enableTenant(string $domain): void
    {
        $engine = app(SanaaEngineService::class);
        $result = $engine->runSkill('tenant_provisioning', [
            'action' => 'enable',
            'domain' => $domain,
        ]);

        if ($result['success'] ?? false) {
            Notification::make()->title("{$domain} re-enabled")->success()->send();
            $this->loadTenants();
        } else {
            Notification::make()
                ->title("Failed to enable {$domain}")
                ->body((string) ($result['error'] ?? ''))
                ->danger()
                ->send();
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    public function getActiveTenants(): array
    {
        return array_values(array_filter($this->tenants, fn ($t) => ($t['enabled'] ?? false)));
    }

    public function getInactiveTenants(): array
    {
        return array_values(array_filter($this->tenants, fn ($t) => ! ($t['enabled'] ?? false)));
    }

    public function getTenantCount(): int
    {
        return count($this->tenants);
    }

    public function getSelectedSourceMeta(): ?array
    {
        foreach ($this->availableSources as $src) {
            if (($src['path'] ?? '') === $this->source) {
                return $src;
            }
        }

        return null;
    }

    public function getProvisionPreview(): array
    {
        $domain = $this->normalizeDomainInput($this->domain);
        $domainValid = $domain !== '' && (bool) preg_match('/^[a-z0-9\-]+\.sanaa\.(ug|co)$/', $domain);
        $appName = strtolower(trim($this->appName));

        if ($appName === '' && $domain !== '') {
            $appName = explode('.', $domain)[0] ?? '';
        }

        $appName = preg_replace('/[^a-z0-9_]/', '_', $appName ?? '') ?? '';
        $sourceMeta = $this->getSelectedSourceMeta();

        return [
            'domain' => $domain,
            'domain_valid' => $domainValid,
            'app_name' => $appName,
            'database' => $appName,
            'url' => $domain !== '' ? "https://{$domain}" : '',
            'source_label' => $sourceMeta['label'] ?? basename($this->source),
            'source_path' => $this->source,
            'source_db' => $this->dbSource,
            'clean_slate' => $this->wipeTenantData,
            'tls_mode' => $this->skipCert ? 'HTTP only' : 'TLS enabled',
        ];
    }

    private function hydrateProvisionRun(array $run): void
    {
        $this->currentRunId = (string) ($run['id'] ?? '');
        $this->runState = (string) ($run['status'] ?? 'idle');
        $this->isRunning = in_array($this->runState, ['queued', 'running'], true);
        $this->provisionLog = (string) ($run['output'] ?? '');

        $success = $this->runState === 'succeeded';
        $this->lastResult = [
            'success' => $success,
            'error' => (string) ($run['error'] ?? ''),
            'output' => (string) ($run['output'] ?? ''),
            'data' => is_array($run['data'] ?? null) ? $run['data'] : [],
        ];
    }
}
