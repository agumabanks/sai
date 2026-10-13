<?php

namespace App\Filament\Pages;

use App\Services\SanaaEngineService;
use Filament\Notifications\Notification;
use Filament\Pages\Page;

class TenantControl extends Page
{
    protected static ?string $navigationIcon = 'heroicon-o-server-stack';

    protected static ?string $navigationGroup = 'Infrastructure';

    protected static ?int $navigationSort = 5;

    protected static string $view = 'filament.pages.tenant-control';

    protected static ?string $title = 'Tenant Control';

    protected static ?string $navigationLabel = 'Tenant Control';

    // ── Page state ────────────────────────────────────────────────────────────

    /** All registered tenants */
    public array $tenants = [];

    /** Aggregated health data */
    public array $healthData = [];

    /** Per-tenant live health results keyed by tenant id */
    public array $healthByTenantId = [];

    /** Whether data is loading */
    public bool $isLoading = false;

    /** Search query */
    public string $search = '';

    /** Status filter: all | healthy | degraded | down | inactive */
    public string $statusFilter = 'all';

    /** Sort option: name_asc | name_desc | score_high | score_low | checked_recent */
    public string $sortBy = 'name_asc';

    /** Selected tenant IDs for bulk actions */
    public array $selectedTenantIds = [];

    /** Show detail modal */
    public bool $showDetailModal = false;

    /** Tenant being viewed in detail modal */
    public ?array $detailTenant = null;

    /** Recent action log (client-side only) */
    public array $actionLog = [];

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    public function mount(): void
    {
        $this->loadData();
    }

    // ── Data loading ──────────────────────────────────────────────────────────

    public function loadData(): void
    {
        $engine = app(SanaaEngineService::class);
        $this->tenants = $engine->getTenants();
        $this->healthData = $engine->getTenantHealth();
        $this->healthByTenantId = [];

        foreach (($this->healthData['tenants'] ?? []) as $tenantHealth) {
            $tenantId = (int) ($tenantHealth['tenant_id'] ?? $tenantHealth['id'] ?? 0);
            if ($tenantId > 0) {
                $this->healthByTenantId[$tenantId] = $tenantHealth;
            }
        }

        // Clean up selections for tenants that no longer exist
        $existingIds = array_map(fn ($t) => (int) ($t['id'] ?? 0), $this->tenants);
        $this->selectedTenantIds = array_values(array_filter(
            $this->selectedTenantIds,
            fn ($id) => in_array((int) $id, $existingIds, true)
        ));
    }

    public function refreshData(): void
    {
        $this->loadData();
        Notification::make()->title('Tenant data refreshed')->success()->send();
    }

    // ── Filters ───────────────────────────────────────────────────────────────

    public function updatedSearch(): void
    {
        $this->selectedTenantIds = [];
    }

    public function updatedStatusFilter(): void
    {
        $this->selectedTenantIds = [];
    }

    public function updatedSortBy(): void
    {
        // no-op, computed property reacts
    }

    public function clearFilters(): void
    {
        $this->search = '';
        $this->statusFilter = 'all';
        $this->sortBy = 'name_asc';
        $this->selectedTenantIds = [];
    }

    // ── Selection ─────────────────────────────────────────────────────────────

    public function toggleSelection(int $tenantId): void
    {
        $key = array_search($tenantId, $this->selectedTenantIds, true);
        if ($key === false) {
            $this->selectedTenantIds[] = $tenantId;
        } else {
            unset($this->selectedTenantIds[$key]);
            $this->selectedTenantIds = array_values($this->selectedTenantIds);
        }
    }

    public function selectAllVisible(): void
    {
        $filtered = $this->getFilteredTenants();
        $ids = array_map(fn ($t) => (int) ($t['id'] ?? 0), $filtered);
        $this->selectedTenantIds = array_values(array_unique(array_merge($this->selectedTenantIds, $ids)));
    }

    public function deselectAll(): void
    {
        $this->selectedTenantIds = [];
    }

    // ── Actions ───────────────────────────────────────────────────────────────

    public function enableTenant(int $id): void
    {
        $engine = app(SanaaEngineService::class);
        $result = $engine->enableTenant($id);

        if (! empty($result['error'])) {
            Notification::make()
                ->title('Failed to enable tenant')
                ->body((string) ($result['error'] ?? ''))
                ->danger()
                ->send();

            return;
        }

        $name = (string) ($result['name'] ?? "Tenant #{$id}");
        Notification::make()
            ->title("Tenant '{$name}' enabled")
            ->success()
            ->send();

        $this->actionLog[] = ['action' => 'Enable', 'tenant' => $name, 'time' => now()->toDateTimeString()];
        $this->loadData();
    }

    public function disableTenant(int $id): void
    {
        $engine = app(SanaaEngineService::class);
        $result = $engine->disableTenant($id);

        if (! empty($result['error'])) {
            Notification::make()
                ->title('Failed to disable tenant')
                ->body((string) ($result['error'] ?? ''))
                ->danger()
                ->send();

            return;
        }

        $name = (string) ($result['name'] ?? "Tenant #{$id}");
        Notification::make()
            ->title("Tenant '{$name}' disabled")
            ->success()
            ->send();

        $this->actionLog[] = ['action' => 'Disable', 'tenant' => $name, 'time' => now()->toDateTimeString()];
        $this->loadData();
    }

    public function checkTenant(int $id): void
    {
        $engine = app(SanaaEngineService::class);
        $result = $engine->checkTenant($id);

        if (! empty($result['error'])) {
            Notification::make()
                ->title('Health check failed')
                ->body((string) ($result['error'] ?? ''))
                ->danger()
                ->send();

            return;
        }

        $status = (string) ($result['status'] ?? 'unknown');
        $score = $result['health_score'] ?? null;
        $body = "Status: {$status}";
        if ($score !== null) {
            $body .= " | Health: {$score}%";
        }

        Notification::make()
            ->title('Health check complete')
            ->body($body)
            ->success()
            ->send();

        $this->loadData();
    }

    public function checkAllTenants(): void
    {
        $engine = app(SanaaEngineService::class);
        $count = 0;
        $failed = 0;

        foreach ($this->tenants as $tenant) {
            $id = (int) ($tenant['id'] ?? 0);
            if ($id <= 0) {
                continue;
            }
            $result = $engine->checkTenant($id);
            if (! empty($result['error'])) {
                $failed++;
            } else {
                $count++;
            }
        }

        $this->loadData();

        if ($failed > 0) {
            Notification::make()
                ->title("Health checks finished ({$count} ok, {$failed} failed)")
                ->warning()
                ->send();
        } else {
            Notification::make()
                ->title("All {$count} tenants checked")
                ->success()
                ->send();
        }
    }

    public function bulkEnable(): void
    {
        $engine = app(SanaaEngineService::class);
        $count = 0;
        foreach ($this->selectedTenantIds as $id) {
            $result = $engine->enableTenant((int) $id);
            if (empty($result['error'])) {
                $count++;
            }
        }
        $this->selectedTenantIds = [];
        $this->loadData();
        Notification::make()->title("Enabled {$count} tenant(s)")->success()->send();
    }

    public function bulkDisable(): void
    {
        $engine = app(SanaaEngineService::class);
        $count = 0;
        foreach ($this->selectedTenantIds as $id) {
            $result = $engine->disableTenant((int) $id);
            if (empty($result['error'])) {
                $count++;
            }
        }
        $this->selectedTenantIds = [];
        $this->loadData();
        Notification::make()->title("Disabled {$count} tenant(s)")->success()->send();
    }

    public function bulkCheck(): void
    {
        $engine = app(SanaaEngineService::class);
        $count = 0;
        foreach ($this->selectedTenantIds as $id) {
            $result = $engine->checkTenant((int) $id);
            if (empty($result['error'])) {
                $count++;
            }
        }
        $this->selectedTenantIds = [];
        $this->loadData();
        Notification::make()->title("Checked {$count} tenant(s)")->success()->send();
    }

    // ── Detail Modal ──────────────────────────────────────────────────────────

    public function openDetail(int $tenantId): void
    {
        $tenant = null;
        foreach ($this->tenants as $t) {
            if ((int) ($t['id'] ?? 0) === $tenantId) {
                $tenant = $t;
                break;
            }
        }

        if ($tenant === null) {
            return;
        }

        $liveHealth = $this->healthByTenantId[$tenantId] ?? [];
        $tenant['computed_status'] = $this->getTenantHealthStatus($tenant);
        $tenant['live_health'] = $liveHealth;

        $this->detailTenant = $tenant;
        $this->showDetailModal = true;
    }

    public function closeDetail(): void
    {
        $this->showDetailModal = false;
        $this->detailTenant = null;
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    /**
     * Return tenants after applying search, status filter, and sorting.
     */
    public function getFilteredTenants(): array
    {
        $filtered = [];
        foreach ($this->tenants as $tenant) {
            $name = strtolower((string) ($tenant['name'] ?? ''));
            $url = strtolower((string) ($tenant['url'] ?? ''));
            $query = strtolower($this->search);

            if ($query !== '' && strpos($name, $query) === false && strpos($url, $query) === false) {
                continue;
            }

            $healthStatus = $this->getTenantHealthStatus($tenant);
            if ($this->statusFilter !== 'all' && $healthStatus !== $this->statusFilter) {
                continue;
            }

            $filtered[] = $tenant;
        }

        usort($filtered, function ($a, $b) {
            return match ($this->sortBy) {
                'name_asc' => strcasecmp((string) ($a['name'] ?? ''), (string) ($b['name'] ?? '')),
                'name_desc' => strcasecmp((string) ($b['name'] ?? ''), (string) ($a['name'] ?? '')),
                'score_high' => ($b['health_score'] ?? 0) <=> ($a['health_score'] ?? 0),
                'score_low' => ($a['health_score'] ?? 0) <=> ($b['health_score'] ?? 0),
                'checked_recent' => strtotime((string) ($b['last_checked'] ?? '1970-01-01')) <=> strtotime((string) ($a['last_checked'] ?? '1970-01-01')),
                default => 0,
            };
        });

        return $filtered;
    }

    /**
     * Group filtered tenants by their type for display.
     */
    public function getGroupedTenants(): array
    {
        $groups = [];
        foreach ($this->getFilteredTenants() as $tenant) {
            $type = $tenant['type'] ?? 'other';
            $groups[$type][] = $tenant;
        }

        $ordered = [];
        foreach (['finance', 'ecommerce', 'email', 'other'] as $type) {
            if (isset($groups[$type])) {
                $ordered[$type] = $groups[$type];
            }
        }

        return $ordered;
    }

    /**
     * Count filtered tenants by status.
     */
    public function getFilteredTenantCounts(): array
    {
        $counts = ['healthy' => 0, 'degraded' => 0, 'down' => 0, 'inactive' => 0, 'total' => 0];
        foreach ($this->getFilteredTenants() as $tenant) {
            $status = $this->getTenantHealthStatus($tenant);
            $counts[$status] = ($counts[$status] ?? 0) + 1;
            $counts['total']++;
        }

        return $counts;
    }

    /**
     * Get a human-readable label for a tenant type.
     */
    public function getTypeLabel(string $type): string
    {
        return match ($type) {
            'finance' => 'Finance',
            'ecommerce' => 'E-Commerce',
            'email' => 'Email',
            default => ucfirst($type),
        };
    }

    /**
     * Get the icon for a tenant type.
     */
    public function getTypeIcon(string $type): string
    {
        return match ($type) {
            'finance' => 'heroicon-o-banknotes',
            'ecommerce' => 'heroicon-o-shopping-cart',
            'email' => 'heroicon-o-envelope',
            default => 'heroicon-o-server',
        };
    }

    /**
     * Get the gradient CSS for a tenant type.
     */
    public function getTypeGradient(string $type): string
    {
        return match ($type) {
            'finance' => 'from-[#5e5ce6] to-[#7c3aed]',
            'ecommerce' => 'from-[#d97706] to-[#fbbf24]',
            'email' => 'from-[#059669] to-[#34d399]',
            default => 'from-[#6b7280] to-[#9ca3af]',
        };
    }

    /**
     * Get the CSS classes for a status badge.
     */
    public function getStatusBadge(string $status): array
    {
        return match ($status) {
            'healthy', 'active' => [
                'color' => 'text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20',
                'dot' => 'bg-[#30d158]',
                'label' => $status === 'active' ? 'Active' : 'Healthy',
            ],
            'degraded' => [
                'color' => 'text-[#ff9f0a] bg-[#ff9f0a]/10 border-[#ff9f0a]/20',
                'dot' => 'bg-[#ff9f0a]',
                'label' => 'Degraded',
            ],
            'down' => [
                'color' => 'text-[#ff453a] bg-[#ff453a]/10 border-[#ff453a]/20',
                'dot' => 'bg-[#ff453a]',
                'label' => 'Down',
            ],
            'inactive' => [
                'color' => 'text-white/40 bg-white/5 border-white/10',
                'dot' => 'bg-white/40',
                'label' => 'Inactive',
            ],
            default => [
                'color' => 'text-white/40 bg-white/5 border-white/10',
                'dot' => 'bg-white/40',
                'label' => ucfirst($status),
            ],
        };
    }

    /**
     * Resolve the display health status for a tenant.
     */
    public function getTenantHealthStatus(array $tenant): string
    {
        $tenantId = (int) ($tenant['id'] ?? 0);
        $lifecycleStatus = (string) ($tenant['status'] ?? 'inactive');

        if ($lifecycleStatus === 'inactive') {
            return 'inactive';
        }

        $liveStatus = $this->healthByTenantId[$tenantId]['status'] ?? null;
        if (is_string($liveStatus) && $liveStatus !== '') {
            return $liveStatus;
        }

        $persistedHealthStatus = $tenant['health_status'] ?? null;
        if (is_string($persistedHealthStatus) && $persistedHealthStatus !== '') {
            return $persistedHealthStatus;
        }

        return 'unknown';
    }

    /**
     * Get the color class for a health score.
     */
    public function getHealthColor(float $score): string
    {
        if ($score >= 80) {
            return 'text-[#30d158]';
        }
        if ($score >= 60) {
            return 'text-[#ff9f0a]';
        }
        if ($score >= 30) {
            return 'text-[#ff9f0a]';
        }

        return 'text-[#ff453a]';
    }

    /**
     * Get the stroke color for a health score ring.
     */
    public function getHealthStrokeColor(float $score): string
    {
        if ($score >= 80) {
            return '#30d158';
        }
        if ($score >= 60) {
            return '#ff9f0a';
        }
        if ($score >= 30) {
            return '#ff9f0a';
        }

        return '#ff453a';
    }

    /**
     * Get the overall health score.
     */
    public function getOverallScore(): float
    {
        return (float) ($this->healthData['overall_score'] ?? 0);
    }

    /**
     * Get the overall status.
     */
    public function getOverallStatus(): string
    {
        return (string) ($this->healthData['overall_status'] ?? 'unknown');
    }

    /**
     * Count tenants by status (all tenants, not filtered).
     */
    public function getTenantCounts(): array
    {
        $counts = ['healthy' => 0, 'degraded' => 0, 'down' => 0, 'inactive' => 0, 'total' => 0];
        foreach ($this->tenants as $tenant) {
            $status = $this->getTenantHealthStatus($tenant);
            $counts[$status] = ($counts[$status] ?? 0) + 1;
            $counts['total']++;
        }

        return $counts;
    }

    /**
     * Count filtered tenants by status within a specific type group.
     */
    public function getGroupCounts(array $groupTenants): array
    {
        $counts = ['healthy' => 0, 'degraded' => 0, 'down' => 0, 'inactive' => 0, 'unknown' => 0];
        foreach ($groupTenants as $tenant) {
            $status = $this->getTenantHealthStatus($tenant);
            $counts[$status] = ($counts[$status] ?? 0) + 1;
        }

        return $counts;
    }

    /**
     * Format a timestamp for display.
     */
    public function formatLastChecked(?string $timestamp): string
    {
        if (! $timestamp) {
            return 'Never';
        }

        try {
            $dt = new \DateTime($timestamp);
            $now = new \DateTime;
            $diff = $now->diff($dt);

            if ($diff->days > 0) {
                return $diff->days.'d ago';
            }
            if ($diff->h > 0) {
                return $diff->h.'h ago';
            }
            if ($diff->i > 0) {
                return $diff->i.'m ago';
            }

            return 'Just now';
        } catch (\Exception $e) {
            return $timestamp;
        }
    }
}
