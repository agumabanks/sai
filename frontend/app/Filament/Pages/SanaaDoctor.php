<?php

namespace App\Filament\Pages;

use App\Models\SanaaHealthLog;
use Filament\Notifications\Notification;
use Filament\Pages\Page;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\DB;

class SanaaDoctor extends Page
{
    protected static ?string $navigationIcon = 'heroicon-o-heart';

    protected static ?string $navigationGroup = 'System';

    protected static ?string $title = 'SanaaDoctor';

    protected static ?int $navigationSort = 2;

    protected static string $view = 'filament.pages.sanaa-doctor-monitor';

    public array $summary = [];

    public array $apps = [];

    public ?array $selectedLog = null;

    public bool $showDetailModal = false;

    public string $selectedTenant = 'all';

    public string $search = '';

    public string $statusFilter = 'all';

    public string $sortBy = 'name_asc';

    public bool $isPolling = false;

    public function mount(): void
    {
        $this->refreshData();
    }

    public function getTenantsProperty(): array
    {
        $apps = config('sanaa_apps.apps', []);
        $tenants = collect($apps)
            ->pluck('tenant')
            ->filter()
            ->unique()
            ->values()
            ->toArray();

        return array_merge(['all' => 'All Tenants'], array_combine($tenants, $tenants));
    }

    public function refreshData(): void
    {
        // Properly fetch latest log per app using subquery to avoid timestamp collisions
        $subquery = SanaaHealthLog::query()
            ->select('app', DB::raw('MAX(created_at) as max_created_at'))
            ->groupBy('app');

        if ($this->selectedTenant !== 'all') {
            $subquery->where('tenant', $this->selectedTenant);
        }

        $logs = SanaaHealthLog::query()
            ->from('sanaa_health_log as main')
            ->joinSub($subquery, 'latest', function ($join) {
                $join->on('main.app', '=', 'latest.app')
                    ->on('main.created_at', '=', 'latest.max_created_at');
            })
            ->select('main.*')
            ->orderBy('main.app')
            ->get()
            ->keyBy('app')
            ->toArray();

        // Merge with configured apps so we always show the full registry
        $configured = config('sanaa_apps.apps', []);
        $merged = [];
        foreach ($configured as $key => $appConfig) {
            if ($this->selectedTenant !== 'all' && ($appConfig['tenant'] ?? null) !== $this->selectedTenant) {
                continue;
            }

            if (isset($logs[$key])) {
                $merged[$key] = array_merge($appConfig, $logs[$key]);
                $merged[$key]['has_log'] = true;
            } else {
                $merged[$key] = array_merge($appConfig, [
                    'score' => null,
                    'status' => 'unknown',
                    'created_at' => null,
                    'updated_at' => null,
                    'has_log' => false,
                ]);
            }
        }

        // Apply search
        if ($this->search !== '') {
            $query = strtolower($this->search);
            $merged = array_filter($merged, fn ($app) => str_contains(strtolower($app['name'] ?? ''), $query) ||
                str_contains(strtolower($app['key'] ?? ''), $query) ||
                str_contains(strtolower($app['health_url'] ?? ''), $query)
            );
        }

        // Apply status filter
        if ($this->statusFilter !== 'all') {
            $merged = array_filter($merged, fn ($app) => ($app['status'] ?? 'unknown') === $this->statusFilter);
        }

        // Sort
        uasort($merged, function ($a, $b) {
            return match ($this->sortBy) {
                'name_asc' => strcasecmp((string) ($a['name'] ?? ''), (string) ($b['name'] ?? '')),
                'name_desc' => strcasecmp((string) ($b['name'] ?? ''), (string) ($a['name'] ?? '')),
                'score_high' => ($b['score'] ?? -1) <=> ($a['score'] ?? -1),
                'score_low' => ($a['score'] ?? -1) <=> ($b['score'] ?? -1),
                'checked_recent' => strtotime((string) ($b['created_at'] ?? '1970-01-01')) <=> strtotime((string) ($a['created_at'] ?? '1970-01-01')),
                default => 0,
            };
        });

        $this->apps = array_values($merged);

        $healthy = count(array_filter($merged, fn ($l) => ($l['status'] ?? '') === 'healthy'));
        $degraded = count(array_filter($merged, fn ($l) => ($l['status'] ?? '') === 'degraded'));
        $critical = count(array_filter($merged, fn ($l) => ($l['status'] ?? '') === 'critical'));
        $unknown = count(array_filter($merged, fn ($l) => ($l['status'] ?? '') === 'unknown'));

        $this->summary = [
            'total' => count($merged),
            'healthy' => $healthy,
            'degraded' => $degraded,
            'critical' => $critical,
            'unknown' => $unknown,
        ];
    }

    public function updatedSelectedTenant(): void
    {
        $this->refreshData();
    }

    public function updatedSearch(): void
    {
        $this->refreshData();
    }

    public function updatedStatusFilter(): void
    {
        $this->refreshData();
    }

    public function updatedSortBy(): void
    {
        $this->refreshData();
    }

    public function clearFilters(): void
    {
        $this->search = '';
        $this->statusFilter = 'all';
        $this->sortBy = 'name_asc';
        $this->refreshData();
    }

    public function pollNow(): void
    {
        $this->isPolling = true;
        try {
            $tenantOption = $this->selectedTenant !== 'all' ? ['--tenant' => $this->selectedTenant] : [];
            Artisan::call('sanaa:doctor:poll', $tenantOption);
            $output = Artisan::output();

            Notification::make()
                ->title('Poll Complete')
                ->body($output ?: 'Health check finished.')
                ->success()
                ->send();
        } catch (\Exception $e) {
            Notification::make()
                ->title('Poll Failed')
                ->body($e->getMessage())
                ->danger()
                ->send();
        }
        $this->isPolling = false;

        $this->refreshData();
    }

    public function openDetail(string $id): void
    {
        $log = SanaaHealthLog::find($id);
        $this->selectedLog = $log?->toArray();
        $this->showDetailModal = true;
    }

    public function closeDetail(): void
    {
        $this->showDetailModal = false;
        $this->selectedLog = null;
    }

    // ── UI Helpers ────────────────────────────────────────────────────────────

    public function getAppTypeIcon(string $type): string
    {
        return match ($type) {
            'ecommerce' => 'heroicon-o-shopping-cart',
            'finance' => 'heroicon-o-banknotes',
            'logistics' => 'heroicon-o-truck',
            'platform' => 'heroicon-o-server-stack',
            'support' => 'heroicon-o-ticket',
            'education' => 'heroicon-o-academic-cap',
            default => 'heroicon-o-globe-alt',
        };
    }

    public function getAppTypeGradient(string $type): string
    {
        return match ($type) {
            'ecommerce' => 'from-[#d97706] to-[#fbbf24]',
            'finance' => 'from-[#059669] to-[#34d399]',
            'logistics' => 'from-[#2563eb] to-[#60a5fa]',
            'platform' => 'from-[#5e5ce6] to-[#a855f7]',
            'support' => 'from-[#db2777] to-[#f472b6]',
            'education' => 'from-[#0891b2] to-[#22d3ee]',
            default => 'from-[#6b7280] to-[#9ca3af]',
        };
    }

    public function getStatusBadge(string $status): array
    {
        return match ($status) {
            'healthy' => [
                'color' => 'text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20',
                'dot' => 'bg-[#30d158]',
                'label' => 'Healthy',
                'pulse' => false,
            ],
            'degraded' => [
                'color' => 'text-[#ff9f0a] bg-[#ff9f0a]/10 border-[#ff9f0a]/20',
                'dot' => 'bg-[#ff9f0a]',
                'label' => 'Degraded',
                'pulse' => true,
            ],
            'critical' => [
                'color' => 'text-[#ff453a] bg-[#ff453a]/10 border-[#ff453a]/20',
                'dot' => 'bg-[#ff453a]',
                'label' => 'Critical',
                'pulse' => true,
            ],
            default => [
                'color' => 'text-white/40 bg-white/5 border-white/10',
                'dot' => 'bg-white/40',
                'label' => 'Not Polled',
                'pulse' => false,
            ],
        };
    }

    public function getHealthStrokeColor(?int $score): string
    {
        if ($score === null) {
            return '#6b7280';
        }
        if ($score >= 80) {
            return '#30d158';
        }
        if ($score >= 50) {
            return '#ff9f0a';
        }

        return '#ff453a';
    }

    public function getHealthTextColor(?int $score): string
    {
        if ($score === null) {
            return 'text-white/30';
        }
        if ($score >= 80) {
            return 'text-[#30d158]';
        }
        if ($score >= 50) {
            return 'text-[#ff9f0a]';
        }

        return 'text-[#ff453a]';
    }

    public function getGroupedApps(): array
    {
        $groups = [];
        foreach ($this->apps as $app) {
            $type = $app['type'] ?? 'other';
            $groups[$type][] = $app;
        }

        // Order by importance
        $ordered = [];
        foreach (['ecommerce', 'logistics', 'finance', 'platform', 'support', 'education', 'other'] as $type) {
            if (isset($groups[$type])) {
                $ordered[$type] = $groups[$type];
            }
        }

        return $ordered;
    }

    public function getGroupCounts(array $groupApps): array
    {
        $counts = ['healthy' => 0, 'degraded' => 0, 'critical' => 0, 'unknown' => 0];
        foreach ($groupApps as $app) {
            $status = $app['status'] ?? 'unknown';
            $counts[$status] = ($counts[$status] ?? 0) + 1;
        }

        return $counts;
    }

    public function getTypeLabel(string $type): string
    {
        return match ($type) {
            'ecommerce' => 'E-Commerce',
            'finance' => 'Finance',
            'logistics' => 'Logistics',
            'platform' => 'Platform',
            'support' => 'Support',
            'education' => 'Education',
            default => ucfirst($type),
        };
    }

    public function formatLastChecked(?string $timestamp): string
    {
        if (! $timestamp) {
            return 'Never';
        }

        try {
            return \Carbon\Carbon::parse($timestamp)->diffForHumans();
        } catch (\Exception $e) {
            return $timestamp;
        }
    }
}
