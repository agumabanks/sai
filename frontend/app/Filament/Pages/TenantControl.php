<?php

namespace App\Filament\Pages;

use App\Services\SanaaEngineService;
use Filament\Notifications\Notification;
use Filament\Pages\Page;

class TenantControl extends Page
{
    protected static ?string $navigationIcon    = 'heroicon-o-server-stack';
    protected static ?string $navigationGroup   = 'Infrastructure';
    protected static ?int    $navigationSort    = 5;
    protected static string  $view              = 'filament.pages.tenant-control';
    protected static ?string $title             = 'Tenant Control';
    protected static ?string $navigationLabel   = 'Tenant Control';

    // ── Page state ────────────────────────────────────────────────────────────

    /** All registered tenants */
    public array $tenants = [];

    /** Aggregated health data */
    public array $healthData = [];

    /** Whether data is loading */
    public bool $isLoading = false;

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
    }

    public function refreshData(): void
    {
        $this->loadData();
        Notification::make()->title('Tenant data refreshed')->success()->send();
    }

    // ── Actions ───────────────────────────────────────────────────────────────

    public function enableTenant(int $id): void
    {
        $engine = app(SanaaEngineService::class);
        $result = $engine->enableTenant($id);

        if (!empty($result['error'])) {
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

        $this->loadData();
    }

    public function disableTenant(int $id): void
    {
        $engine = app(SanaaEngineService::class);
        $result = $engine->disableTenant($id);

        if (!empty($result['error'])) {
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

        $this->loadData();
    }

    public function checkTenant(int $id): void
    {
        $engine = app(SanaaEngineService::class);
        $result = $engine->checkTenant($id);

        if (!empty($result['error'])) {
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

    // ── Helpers ───────────────────────────────────────────────────────────────

    /**
     * Group tenants by their type for display.
     */
    public function getGroupedTenants(): array
    {
        $groups = [];
        foreach ($this->tenants as $tenant) {
            $type = $tenant['type'] ?? 'other';
            $groups[$type][] = $tenant;
        }

        // Ensure standard ordering: Finance, E-Commerce, Email, Other
        $ordered = [];
        foreach (['finance', 'ecommerce', 'email', 'other'] as $type) {
            if (isset($groups[$type])) {
                $ordered[$type] = $groups[$type];
            }
        }

        return $ordered;
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
            'active' => [
                'color' => 'text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20',
                'dot' => 'bg-[#30d158]',
                'label' => 'Active',
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
     * Get the color class for a health score.
     */
    public function getHealthColor(float $score): string
    {
        if ($score >= 80) return 'text-[#30d158]';
        if ($score >= 60) return 'text-[#ff9f0a]';
        if ($score >= 30) return 'text-[#ff9f0a]';
        return 'text-[#ff453a]';
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
     * Count tenants by status.
     */
    public function getTenantCounts(): array
    {
        $counts = ['active' => 0, 'degraded' => 0, 'down' => 0, 'inactive' => 0, 'total' => 0];
        foreach ($this->tenants as $tenant) {
            $status = $tenant['status'] ?? 'inactive';
            $counts[$status] = ($counts[$status] ?? 0) + 1;
            $counts['total']++;
        }
        return $counts;
    }

    /**
     * Format a timestamp for display.
     */
    public function formatLastChecked(?string $timestamp): string
    {
        if (!$timestamp) {
            return 'Never';
        }

        try {
            $dt = new \DateTime($timestamp);
            $now = new \DateTime();
            $diff = $now->diff($dt);

            if ($diff->days > 0) {
                return $diff->days . 'd ago';
            }
            if ($diff->h > 0) {
                return $diff->h . 'h ago';
            }
            if ($diff->i > 0) {
                return $diff->i . 'm ago';
            }
            return 'Just now';
        } catch (\Exception $e) {
            return $timestamp;
        }
    }
}
