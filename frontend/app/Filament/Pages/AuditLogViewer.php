<?php

namespace App\Filament\Pages;

use App\Services\SanaaEngineService;
use Filament\Notifications\Notification;
use Filament\Pages\Page;

class AuditLogViewer extends Page
{
    protected static ?string $navigationIcon = 'heroicon-o-clipboard-document-list';

    protected static ?string $navigationGroup = 'System';

    protected static ?int $navigationSort = 20;

    protected static string $view = 'filament.pages.audit-log-viewer';

    protected static ?string $title = 'Audit Log';

    protected static ?string $navigationLabel = 'Audit Log';

    protected static ?string $slug = 'audit-log';

    // ── Page state ────────────────────────────────────────────────────────

    /** Paginated audit log response */
    public array $auditData = [];

    /** Currently selected entry for detail view */
    public ?array $selectedEntry = null;

    // ── Filters ───────────────────────────────────────────────────────────

    public string $filterDateFrom = '';

    public string $filterDateTo = '';

    public string $filterAction = '';

    public string $filterActor = '';

    public string $filterPath = '';

    public ?bool $filterSuccess = null;

    // ── Pagination ────────────────────────────────────────────────────────

    public int $currentPage = 1;

    public int $perPage = 50;

    // ── Sort ──────────────────────────────────────────────────────────────

    public string $sortField = 'timestamp';

    public string $sortDirection = 'desc';

    // ── Lifecycle ─────────────────────────────────────────────────────────

    public function mount(): void
    {
        $this->loadData();
    }

    // ── Data loading ──────────────────────────────────────────────────────

    public function loadData(): void
    {
        $engine = app(SanaaEngineService::class);

        $filters = [];

        if ($this->filterDateFrom) {
            $filters['date_from'] = $this->filterDateFrom;
        }
        if ($this->filterDateTo) {
            $filters['date_to'] = $this->filterDateTo;
        }
        if ($this->filterAction) {
            $filters['action'] = $this->filterAction;
        }
        if ($this->filterActor) {
            $filters['actor'] = $this->filterActor;
        }
        if ($this->filterPath) {
            $filters['path'] = $this->filterPath;
        }
        if ($this->filterSuccess !== null) {
            $filters['success'] = $this->filterSuccess;
        }

        $this->auditData = $engine->getAuditLogs($filters, $this->currentPage, $this->perPage);
    }

    // ── Actions ───────────────────────────────────────────────────────────

    public function applyFilters(): void
    {
        $this->currentPage = 1;
        $this->loadData();
    }

    public function clearFilters(): void
    {
        $this->filterDateFrom = '';
        $this->filterDateTo = '';
        $this->filterAction = '';
        $this->filterActor = '';
        $this->filterPath = '';
        $this->filterSuccess = null;
        $this->currentPage = 1;
        $this->loadData();
    }

    public function goToPage(int $page): void
    {
        $this->currentPage = max(1, $page);
        $this->loadData();
    }

    public function previousPage(): void
    {
        if ($this->currentPage > 1) {
            $this->currentPage--;
            $this->loadData();
        }
    }

    public function nextPage(): void
    {
        $totalPages = $this->getTotalPages();
        if ($this->currentPage < $totalPages) {
            $this->currentPage++;
            $this->loadData();
        }
    }

    public function viewEntry(int $id): void
    {
        $engine = app(SanaaEngineService::class);
        $this->selectedEntry = $engine->getAuditLogEntry($id);
    }

    public function closeDetail(): void
    {
        $this->selectedEntry = null;
    }

    public function refreshData(): void
    {
        $this->loadData();
        Notification::make()->title('Audit log refreshed')->success()->send();
    }

    // ── Helpers ───────────────────────────────────────────────────────────

    /**
     * Get the list of audit log entries.
     */
    public function getEntries(): array
    {
        return $this->auditData['items'] ?? [];
    }

    /**
     * Get total number of entries.
     */
    public function getTotal(): int
    {
        return (int) ($this->auditData['total'] ?? 0);
    }

    /**
     * Get total number of pages.
     */
    public function getTotalPages(): int
    {
        return (int) ($this->auditData['pages'] ?? 0);
    }

    /**
     * Format a timestamp for display.
     */
    public function formatTimestamp(?string $timestamp): string
    {
        if (! $timestamp) {
            return '—';
        }
        try {
            $dt = new \DateTime($timestamp);

            return $dt->format('M j, Y H:i:s');
        } catch (\Exception $e) {
            return $timestamp;
        }
    }

    /**
     * Get the HTTP method from an action string (e.g. "GET /api/health" → "GET").
     */
    public function getMethod(?string $action): string
    {
        if (! $action) {
            return '—';
        }
        $parts = explode(' ', $action, 2);

        return $parts[0] ?? $action;
    }

    /**
     * Get the path from an action string (e.g. "GET /api/health" → "/api/health").
     */
    public function getPath(?string $action): string
    {
        if (! $action) {
            return '—';
        }
        $parts = explode(' ', $action, 2);

        return $parts[1] ?? $action;
    }

    /**
     * Get CSS classes for an HTTP method badge.
     */
    public function getMethodBadge(string $method): string
    {
        return match (strtoupper($method)) {
            'GET' => 'text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20',
            'POST' => 'text-[#0a84ff] bg-[#0a84ff]/10 border-[#0a84ff]/20',
            'PUT' => 'text-[#ff9f0a] bg-[#ff9f0a]/10 border-[#ff9f0a]/20',
            'PATCH' => 'text-[#ff9f0a] bg-[#ff9f0a]/10 border-[#ff9f0a]/20',
            'DELETE' => 'text-[#ff453a] bg-[#ff453a]/10 border-[#ff453a]/20',
            default => 'text-white/40 bg-white/5 border-white/10',
        };
    }

    /**
     * Get CSS classes for a success/failure badge.
     */
    public function getSuccessBadge(bool $success): array
    {
        return $success
            ? ['color' => 'text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20', 'label' => 'Success']
            : ['color' => 'text-[#ff453a] bg-[#ff453a]/10 border-[#ff453a]/20', 'label' => 'Failed'];
    }
}
